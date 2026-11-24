import re
import json
import logging
from decimal import Decimal
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Set, Tuple
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from apps.companies.models import Company
from apps.accounting.models import Voucher, VoucherItem
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService
from apps.gst.models import (
    GSTR2BImport, GSTR2BRecord, GSTRegistration, GSTR2BIngestionLock,
    resolve_document_financial_effect, DocumentFinancialEffect
)
from apps.gst.services.period_service import GSTPeriodService, PeriodInfo

logger = logging.getLogger('apps.gst.itc_reconciliation_service')


def quantize_amount(val: Any) -> Decimal:
    try:
        return Decimal(str(val or '0.00')).quantize(Decimal('0.01'))
    except Exception:
        return Decimal('0.00')


class ITCReconciliationService:
    """
    Vendor ITC Risk Shield - Ingestion and Reconciliation Engine.
    Provides idempotent GSTR-2B ingestion, period-isolated reconciliation,
    cross-period eligibility tracking, and multi-GSTIN tenant isolation.
    """

    TOLERANCE = Decimal('2.00')  # ₹2.00 threshold for rounding differences

    @staticmethod
    def normalize_invoice_number(inum: str) -> str:
        """
        Normalizes an invoice number for matching across systems.
        E.g.: 'INV/2026-27/0081' -> '2026270081'
        Strips non-alphanumerics and standard 'INV' prefixes.
        """
        if not inum:
            return ""
        cleaned = re.sub(r'[^A-Z0-9]', '', str(inum).strip().upper())
        if cleaned.startswith('INV') and len(cleaned) > 3:
            cleaned = cleaned[3:]
        return cleaned

    @classmethod
    def parse_date(cls, dt_str: Any) -> Optional[date]:
        """
        Parses various date formats from GST Portal (DD-MM-YYYY, YYYY-MM-DD, DD/MM/YYYY)
        and Excel serial date floats/ints.
        Never fabricates dates. Returns None on unparseable, malformed, or impossible dates.
        """
        if not dt_str:
            return None
        if isinstance(dt_str, (date, datetime)):
            d = dt_str.date() if isinstance(dt_str, datetime) else dt_str
            if 2000 <= d.year <= 2100:
                return d
            return None

        # Excel serial number (days since 1899-12-30)
        if isinstance(dt_str, (int, float)):
            try:
                d = date(1899, 12, 30) + timedelta(days=int(dt_str))
                if 2000 <= d.year <= 2100:
                    return d
                return None
            except Exception:
                return None

        s = str(dt_str).strip()
        if not s:
            return None

        # If string is a numeric float or int representing Excel serial
        if re.match(r'^\d+(\.\d+)?$', s):
            try:
                num = float(s)
                if 30000 <= num <= 70000:  # approx years 1982 to 2091
                    d = date(1899, 12, 30) + timedelta(days=int(num))
                    if 2000 <= d.year <= 2100:
                        return d
            except Exception:
                pass

        for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%d-%b-%Y', '%Y/%m/%d', '%d.%m.%Y'):
            try:
                d = datetime.strptime(s, fmt).date()
                if 2000 <= d.year <= 2100:
                    return d
                return None
            except ValueError:
                continue
        return None

    @classmethod
    def _acquire_ingestion_lock(
        cls,
        company: Company,
        registration: Optional[Any],
        return_period: str
    ) -> GSTR2BIngestionLock:
        """
        Concurrency-safe lock acquisition for GSTR-2B ingestion in PostgreSQL.
        Guarantees no IntegrityError race on first lock creation across parallel workers.
        Uses a savepoint sub-transaction to create if absent, then acquires an exclusive row lock.
        """
        filter_kwargs = {
            'company': company,
            'gst_registration': registration,
            'return_period': return_period,
        }
        try:
            with transaction.atomic():
                GSTR2BIngestionLock.objects.create(**filter_kwargs)
        except IntegrityError:
            # Row already exists or was concurrently created
            pass

        return GSTR2BIngestionLock.objects.select_for_update().get(**filter_kwargs)

    @classmethod
    @transaction.atomic
    def ingest_gstr2b_json(
        cls,
        company: Company,
        json_data: Any,
        user=None,
        file_name: str = '',
        return_period: Optional[str] = None,
        registration: Optional[Any] = None,
        source_info: str = 'JSON_UPLOAD'
    ) -> GSTR2BImport:
        """
        Idempotently ingests official GSTR-2B JSON (from GST Portal or Sandbox API).
        Parses B2B (Table 3), B2BA (Amendments), CDNR (Credit/Debit Notes), and CDNRA.
        Preserves manual review history and avoids duplicate logical invoices.
        Concurrency-safe via GSTR2BIngestionLock.
        """
        if isinstance(json_data, (str, bytes)):
            json_data = json.loads(json_data)

        # 1. Canonical return period resolution
        raw_fp = return_period or json_data.get('fp') or json_data.get('data', {}).get('fp')
        period_info = GSTPeriodService.parse_return_period(raw_fp)
        fp = period_info.normalized_period
        fy = period_info.financial_year

        # 2. Strict GST registration resolution and tenant isolation
        if registration is not None:
            if isinstance(registration, GSTRegistration):
                if registration.company_id != company.id:
                    raise ValidationError("GST Registration does not belong to this company.")
                if registration.status != 'ACTIVE':
                    raise ValidationError(f"GST Registration {registration.gstin} is inactive.")
            else:
                reg = GSTRegistration.objects.filter(id=registration, company=company).first()
                if not reg:
                    raise ValidationError(f"GST Registration '{registration}' not found for this company.")
                if reg.status != 'ACTIVE':
                    raise ValidationError(f"GST Registration {reg.gstin} is inactive.")
                registration = reg
        else:
            target_gstin = str(json_data.get('gstin') or json_data.get('data', {}).get('gstin') or '').strip().upper()
            if target_gstin:
                reg = GSTRegistration.objects.filter(company=company, gstin=target_gstin).first()
                if not reg:
                    raise ValidationError(f"GSTIN '{target_gstin}' in GSTR-2B data does not match any registered GSTIN for {company.name}.")
                if reg.status != 'ACTIVE':
                    raise ValidationError(f"GST Registration for {target_gstin} is inactive.")
                registration = reg
            else:
                registration = (
                    GSTRegistration.objects.filter(company=company, is_primary=True, status='ACTIVE').first()
                    or GSTRegistration.objects.filter(company=company, status='ACTIVE').first()
                )

        # 3. Concurrency Lock: Synchronize concurrent ingestion for this company, registration, and return period
        lock_obj = cls._acquire_ingestion_lock(
            company=company,
            registration=registration,
            return_period=fp
        )

        # 4. Create Import Batch Audit Entry
        import_batch = GSTR2BImport.objects.create(
            company=company,
            gst_registration=registration,
            return_period=fp,
            financial_year=fy,
            file_format='JSON',
            file_name=file_name or f"gstr2b_{fp}.json",
            uploaded_by=user,
            status='PROCESSING',
            source_info=source_info
        )

        # 5. Fetch existing records for this return period to support idempotent upsert
        rec_filter = {'company': company, 'return_period': fp}
        if registration:
            rec_filter['gst_registration'] = registration
        else:
            rec_filter['gst_registration__isnull'] = True

        initial_rec_count = GSTR2BRecord.objects.filter(**rec_filter).count()

        existing_by_key = {
            (
                r.supplier_gstin.upper(),
                r.normalized_invoice_number,
                r.document_type,
                r.original_document_number or ''
            ): r
            for r in GSTR2BRecord.objects.filter(**rec_filter).select_for_update()
        }

        records_to_create = []
        records_to_update = []
        records_created_count = 0
        records_updated_count = 0
        records_unchanged_count = 0
        provider_records_count = 0

        total_taxable = Decimal('0.00')
        total_itc = Decimal('0.00')

        # 6. Extract tables: B2B, B2BA, CDNR, CDNRA (supporting both direct and nested docdata payload structures)
        data_root = json_data.get('data', json_data)
        doc_root = data_root.get('docdata', data_root) if isinstance(data_root, dict) else json_data
        b2b_list = doc_root.get('b2b') or (data_root.get('b2b') if isinstance(data_root, dict) else []) or []
        b2ba_list = doc_root.get('b2ba') or (data_root.get('b2ba') if isinstance(data_root, dict) else []) or []
        cdnr_list = doc_root.get('cdnr') or (data_root.get('cdnr') if isinstance(data_root, dict) else []) or []
        cdnra_list = doc_root.get('cdnra') or (data_root.get('cdnra') if isinstance(data_root, dict) else []) or []

        # Process B2B and B2BA
        for doc_type, supplier_entry in [('B2B', s) for s in b2b_list] + [('B2BA', s) for s in b2ba_list]:
            ctin = str(supplier_entry.get('ctin', '')).strip().upper()
            trdnm = str(supplier_entry.get('trdnm') or supplier_entry.get('lgl_name') or '').strip()
            invoices = supplier_entry.get('inv', [])
            is_amend = (doc_type == 'B2BA')

            for inv in invoices:
                provider_records_count += 1
                inum = str(inv.get('inum', '')).strip()
                if not inum:
                    continue
                norm_num = cls.normalize_invoice_number(inum)
                raw_dt = inv.get('dt')
                dt = cls.parse_date(raw_dt)
                val = quantize_amount(inv.get('val', '0'))
                pos = str(inv.get('pos', '')).strip()
                rev = str(inv.get('rev', 'N')).strip().upper()
                itcavl = str(inv.get('itcavl', 'Y')).strip().upper() == 'Y'
                rsn = str(inv.get('rsn', '')).strip()
                inv_typ = str(inv.get('inv_typ', 'R')).strip()
                orig_num = str(inv.get('oinum', '')).strip()
                orig_dt = cls.parse_date(inv.get('oidt'))

                # Line item sums
                items = inv.get('items', [])
                inv_txval = Decimal('0.00')
                inv_iamt = Decimal('0.00')
                inv_camt = Decimal('0.00')
                inv_samt = Decimal('0.00')
                inv_csamt = Decimal('0.00')
                for itm in items:
                    det = itm.get('itmdet', itm)
                    inv_txval += quantize_amount(det.get('txval', '0'))
                    inv_iamt += quantize_amount(det.get('iamt', '0'))
                    inv_camt += quantize_amount(det.get('camt', '0'))
                    inv_samt += quantize_amount(det.get('samt', '0'))
                    inv_csamt += quantize_amount(det.get('csamt', '0'))

                if inv_txval == Decimal('0.00') and val > Decimal('0.00'):
                    inv_txval = val

                rec_itc = (inv_iamt + inv_camt + inv_samt + inv_csamt) if itcavl else Decimal('0.00')
                total_taxable += inv_txval
                total_itc += rec_itc

                doc_key = (ctin, norm_num, doc_type, orig_num)
                existing = existing_by_key.get(doc_key)
                init_match_status = 'REVIEW_REQUIRED' if dt is None else 'MISSING_IN_BOOKS'

                if existing:
                    has_changes = (
                        existing.taxable_value != inv_txval
                        or existing.invoice_value != val
                        or existing.igst_amount != inv_iamt
                        or existing.cgst_amount != inv_camt
                        or existing.sgst_amount != inv_samt
                        or existing.cess_amount != inv_csamt
                        or existing.itc_available != itcavl
                        or existing.invoice_date != dt
                    )
                    if has_changes:
                        existing.taxable_value = inv_txval
                        existing.invoice_value = val
                        existing.igst_amount = inv_iamt
                        existing.cgst_amount = inv_camt
                        existing.sgst_amount = inv_samt
                        existing.cess_amount = inv_csamt
                        existing.place_of_supply = pos
                        existing.reverse_charge = rev
                        existing.itc_available = itcavl
                        existing.itc_ineligible_reason = rsn
                        existing.invoice_date = dt
                        existing.raw_invoice_date = str(raw_dt or '')
                        existing.import_batch = import_batch
                        if dt is None:
                            existing.match_status = 'REVIEW_REQUIRED'
                        records_to_update.append(existing)
                        records_updated_count += 1
                    else:
                        records_unchanged_count += 1
                else:
                    new_rec = GSTR2BRecord(
                        import_batch=import_batch,
                        company=company,
                        gst_registration=registration,
                        return_period=fp,
                        document_type=doc_type,
                        original_document_number=orig_num,
                        original_document_date=orig_dt,
                        supplier_gstin=ctin,
                        supplier_name=trdnm,
                        invoice_number=inum,
                        normalized_invoice_number=norm_num,
                        invoice_type=inv_typ,
                        invoice_date=dt,
                        raw_invoice_date=str(raw_dt or ''),
                        invoice_value=val,
                        taxable_value=inv_txval,
                        igst_amount=inv_iamt,
                        cgst_amount=inv_camt,
                        sgst_amount=inv_samt,
                        cess_amount=inv_csamt,
                        place_of_supply=pos,
                        reverse_charge=rev,
                        itc_available=itcavl,
                        itc_ineligible_reason=rsn,
                        match_status=init_match_status,
                        is_amendment=is_amend,
                        amendment_return_period=fp if is_amend else ''
                    )
                    records_to_create.append(new_rec)
                    existing_by_key[doc_key] = new_rec
                    records_created_count += 1

        # Process CDNR and CDNRA
        for doc_type, supplier_entry in [('CDNR', s) for s in cdnr_list] + [('CDNRA', s) for s in cdnra_list]:
            ctin = str(supplier_entry.get('ctin', '')).strip().upper()
            trdnm = str(supplier_entry.get('trdnm') or supplier_entry.get('lgl_name') or '').strip()
            notes = supplier_entry.get('nt', [])
            is_amend = (doc_type == 'CDNRA')

            for nt in notes:
                provider_records_count += 1
                nt_num = str(nt.get('nt_num', '')).strip()
                if not nt_num:
                    continue
                norm_num = cls.normalize_invoice_number(nt_num)
                raw_dt = nt.get('nt_dt')
                dt = cls.parse_date(raw_dt)
                val = quantize_amount(nt.get('val', '0'))
                raw_ntty = str(nt.get('ntty', '')).strip().upper()
                eff = resolve_document_financial_effect({'document_type': doc_type, 'note_type': raw_ntty})
                nt_typ = 'C' if eff.is_credit_note else ('D' if eff.is_debit_note else raw_ntty)
                itcavl = str(nt.get('itcavl', 'Y')).strip().upper() == 'Y'
                orig_num = str(nt.get('ont_num', nt.get('oinum', ''))).strip()
                orig_dt = cls.parse_date(nt.get('ont_dt', nt.get('oidt')))

                items = nt.get('items', [])
                nt_txval = Decimal('0.00')
                nt_iamt = Decimal('0.00')
                nt_camt = Decimal('0.00')
                nt_samt = Decimal('0.00')
                nt_csamt = Decimal('0.00')
                for itm in items:
                    det = itm.get('itmdet', itm)
                    nt_txval += quantize_amount(det.get('txval', '0'))
                    nt_iamt += quantize_amount(det.get('iamt', '0'))
                    nt_camt += quantize_amount(det.get('camt', '0'))
                    nt_samt += quantize_amount(det.get('samt', '0'))
                    nt_csamt += quantize_amount(det.get('csamt', '0'))

                if nt_txval == Decimal('0.00') and val > Decimal('0.00'):
                    nt_txval = val

                rec_itc = (nt_iamt + nt_camt + nt_samt + nt_csamt) if itcavl else Decimal('0.00')

                # Mathematical accounting semantics using canonical resolver:
                # Credit Note ('C') reduces buyer's taxable amount and net ITC (sign: -1).
                # Debit Note ('D') increases buyer's taxable amount and net ITC (sign: +1).
                # Unknown note type (sign: 0) requires human review and does not alter balances.
                total_taxable += (nt_txval * eff.financial_sign)
                total_itc += (rec_itc * eff.financial_sign)

                doc_key = (ctin, norm_num, doc_type, orig_num)
                existing = existing_by_key.get(doc_key)
                init_match_status = 'REVIEW_REQUIRED' if (dt is None or eff.is_review_required) else 'MISSING_IN_BOOKS'

                if existing:
                    has_changes = (
                        existing.taxable_value != nt_txval
                        or existing.invoice_value != val
                        or existing.igst_amount != nt_iamt
                        or existing.cgst_amount != nt_camt
                        or existing.sgst_amount != nt_samt
                        or existing.cess_amount != nt_csamt
                        or existing.itc_available != itcavl
                        or existing.invoice_date != dt
                    )
                    if has_changes:
                        existing.taxable_value = nt_txval
                        existing.invoice_value = val
                        existing.igst_amount = nt_iamt
                        existing.cgst_amount = nt_camt
                        existing.sgst_amount = nt_samt
                        existing.cess_amount = nt_csamt
                        existing.itc_available = itcavl
                        existing.invoice_date = dt
                        existing.raw_invoice_date = str(raw_dt or '')
                        existing.note_type = nt_typ
                        existing.import_batch = import_batch
                        if dt is None:
                            existing.match_status = 'REVIEW_REQUIRED'
                        records_to_update.append(existing)
                        records_updated_count += 1
                    else:
                        records_unchanged_count += 1
                else:
                    new_rec = GSTR2BRecord(
                        import_batch=import_batch,
                        company=company,
                        gst_registration=registration,
                        return_period=fp,
                        document_type=doc_type,
                        original_document_number=orig_num,
                        original_document_date=orig_dt,
                        supplier_gstin=ctin,
                        supplier_name=trdnm,
                        invoice_number=nt_num,
                        normalized_invoice_number=norm_num,
                        invoice_type=f"{doc_type}_{nt_typ}",
                        note_type=nt_typ,
                        invoice_date=dt,
                        raw_invoice_date=str(raw_dt or ''),
                        invoice_value=val,
                        taxable_value=nt_txval,
                        igst_amount=nt_iamt,
                        cgst_amount=nt_camt,
                        sgst_amount=nt_samt,
                        cess_amount=nt_csamt,
                        itc_available=itcavl,
                        match_status=init_match_status,
                        is_amendment=is_amend,
                        amendment_return_period=fp if is_amend else ''
                    )
                    records_to_create.append(new_rec)
                    existing_by_key[doc_key] = new_rec
                    records_created_count += 1

        # 7. Bulk write changes with database uniqueness conflict resolution
        if records_to_create:
            GSTR2BRecord.objects.bulk_create(records_to_create, batch_size=500, ignore_conflicts=True)
        if records_to_update:
            GSTR2BRecord.objects.bulk_update(
                records_to_update,
                fields=[
                    'import_batch', 'taxable_value', 'invoice_value', 'igst_amount',
                    'cgst_amount', 'sgst_amount', 'cess_amount', 'invoice_date',
                    'raw_invoice_date', 'place_of_supply', 'reverse_charge',
                    'itc_available', 'itc_ineligible_reason', 'note_type', 'match_status'
                ],
                batch_size=500
            )

        # 8. Update batch statistics reflecting true current batch operations (DEF-06 & DEF-03)
        final_rec_count = GSTR2BRecord.objects.filter(**rec_filter).count()
        actual_created_count = len(records_to_create)
        actual_updated_count = len(records_to_update)
        actual_unchanged_count = records_unchanged_count
        actual_rejected_count = 0
        batch_invoices_count = actual_created_count + actual_updated_count + actual_unchanged_count

        is_empty = (provider_records_count == 0)
        batch_status = 'EMPTY_PROCESSED' if is_empty else 'PROCESSED'

        import_batch.provider_records_count = provider_records_count
        import_batch.total_invoices_count = batch_invoices_count
        import_batch.period_records_count = final_rec_count
        import_batch.records_created = actual_created_count
        import_batch.records_updated = actual_updated_count
        import_batch.records_unchanged = actual_unchanged_count
        import_batch.records_rejected = actual_rejected_count
        import_batch.is_empty_statement = is_empty
        import_batch.total_taxable_amount = total_taxable
        import_batch.total_itc_available = total_itc
        import_batch.status = batch_status
        import_batch.save(update_fields=[
            'provider_records_count', 'total_invoices_count', 'period_records_count',
            'records_created', 'records_updated', 'records_unchanged', 'records_rejected',
            'is_empty_statement', 'total_taxable_amount', 'total_itc_available', 'status'
        ])

        # 9. Run period-isolated reconciliation for this period
        cls.reconcile_period(company, return_period=fp, registration=registration)

        return import_batch

    @classmethod
    @transaction.atomic
    def ingest_gstr2b_excel(
        cls,
        company: Company,
        file_obj,
        user=None,
        file_name: str = '',
        return_period: Optional[str] = None,
        registration: Optional[Any] = None
    ) -> GSTR2BImport:
        """
        Idempotently ingests official GSTR-2B Excel spreadsheet.
        Supports B2B and CDNR sheets. Requires explicit return period or sheet detection.
        No silent previous-month fallback.
        """
        import openpyxl
        from apps.accounting.services.upload_security import UploadValidationError

        wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
        try:
            # 1. Normalize return period without silent fallback
            fp = ''
            if return_period:
                p_info = GSTPeriodService.parse_return_period(return_period)
                fp = p_info.normalized_period
                fy = p_info.financial_year
            else:
                # Check for return period in sheet name or filename
                match = re.search(r'(\d{6})', file_name or '')
                if match:
                    p_info = GSTPeriodService.parse_return_period(match.group(1))
                    fp = p_info.normalized_period
                    fy = p_info.financial_year
                else:
                    raise UploadValidationError(
                        "Return period could not be determined from the file name. "
                        "Please specify an explicit return period (MMYYYY format) to ingest GSTR-2B Excel."
                    )

            # 2. Strict registration resolution
            if registration is not None:
                if isinstance(registration, GSTRegistration):
                    if registration.company_id != company.id:
                        raise ValidationError("GST Registration does not belong to this company.")
                    if registration.status != 'ACTIVE':
                        raise ValidationError(f"GST Registration {registration.gstin} is inactive.")
                else:
                    reg = GSTRegistration.objects.filter(id=registration, company=company).first()
                    if not reg:
                        raise ValidationError(f"GST Registration '{registration}' not found for this company.")
                    if reg.status != 'ACTIVE':
                        raise ValidationError(f"GST Registration {reg.gstin} is inactive.")
                    registration = reg
            else:
                registration = (
                    GSTRegistration.objects.filter(company=company, is_primary=True, status='ACTIVE').first()
                    or GSTRegistration.objects.filter(company=company, status='ACTIVE').first()
                )

            # 3. Concurrency Lock: Synchronize concurrent ingestion for this company, registration, and return period
            lock_obj = cls._acquire_ingestion_lock(
                company=company,
                registration=registration,
                return_period=fp
            )

            import_batch = GSTR2BImport.objects.create(
                company=company,
                gst_registration=registration,
                return_period=fp,
                financial_year=fy,
                file_format='EXCEL',
                file_name=file_name or f"gstr2b_{fp}.xlsx",
                uploaded_by=user,
                status='PROCESSING',
                source_info='EXCEL_UPLOAD'
            )

            rec_filter = {'company': company, 'return_period': fp}
            if registration:
                rec_filter['gst_registration'] = registration
            else:
                rec_filter['gst_registration__isnull'] = True

            initial_rec_count = GSTR2BRecord.objects.filter(**rec_filter).count()

            existing_by_key = {
                (
                    r.supplier_gstin.upper(),
                    r.normalized_invoice_number,
                    r.document_type,
                    r.original_document_number or ''
                ): r
                for r in GSTR2BRecord.objects.filter(**rec_filter).select_for_update()
            }

            records_to_create = []
            records_to_update = []
            records_created_count = 0
            records_updated_count = 0
            records_unchanged_count = 0
            provider_records_count = 0

            total_taxable = Decimal('0.00')
            total_itc = Decimal('0.00')

            # Identify B2B sheet
            b2b_sheet = None
            cdnr_sheet = None
            for sname in wb.sheetnames:
                clean_name = sname.lower().replace(' ', '').replace('_', '').replace('-', '')
                if 'b2b' in clean_name and 'cdn' not in clean_name and not b2b_sheet:
                    b2b_sheet = wb[sname]
                elif ('cdnr' in clean_name or 'credit' in clean_name) and not cdnr_sheet:
                    cdnr_sheet = wb[sname]

            if not b2b_sheet:
                b2b_sheet = wb.active

            def parse_sheet_rows(sheet, is_cdnr=False):
                nonlocal provider_records_count, records_created_count, records_updated_count
                nonlocal records_unchanged_count, total_taxable, total_itc

                row_iter = sheet.iter_rows(values_only=True)
                header_row = None
                for row in row_iter:
                    row_str = " ".join([str(c or '').lower() for c in row])
                    if 'gstin' in row_str and ('invoice' in row_str or 'taxable' in row_str or 'doc' in row_str or 'note' in row_str):
                        header_row = [str(c or '').strip().lower() for c in row]
                        break

                if not header_row:
                    return

                def get_col(candidates):
                    for cand in candidates:
                        for idx, h in enumerate(header_row):
                            if cand in h:
                                return idx
                    return None

                def cell_at(row_tuple, idx):
                    if idx is None or idx >= len(row_tuple):
                        return None
                    return row_tuple[idx]

                c_gstin = get_col(['gstin of supplier', 'supplier gstin', 'gstin'])
                c_name = get_col(['trade name', 'legal name', 'supplier name', 'name'])
                c_inum = get_col(['invoice number', 'inv no', 'note number', 'nt num', 'document number'])
                c_date = get_col(['invoice date', 'inv dt', 'note date', 'nt dt', 'document date'])
                c_val = get_col(['invoice value', 'inv val', 'note value', 'document value'])
                c_pos = get_col(['place of supply', 'pos'])
                c_rev = get_col(['reverse charge', 'rev chg', 'rev'])
                c_txval = get_col(['taxable value', 'taxable'])
                c_iamt = get_col(['integrated tax', 'igst'])
                c_camt = get_col(['central tax', 'cgst'])
                c_samt = get_col(['state/ut tax', 'sgst', 'state tax'])
                c_csamt = get_col(['cess'])
                c_itc = get_col(['itc availability', 'itc available', 'itc'])
                c_ntty = get_col(['note type', 'document type', 'type'])

                doc_type = 'CDNR' if is_cdnr else 'B2B'

                for row_tuple in row_iter:
                    raw_gstin = cell_at(row_tuple, c_gstin) or ''
                    if not raw_gstin:
                        continue
                    gstin = str(raw_gstin).strip().upper()
                    if len(gstin) < 10:
                        continue

                    inum = str(cell_at(row_tuple, c_inum) or '').strip()
                    if not inum:
                        continue
                    norm_num = cls.normalize_invoice_number(inum)

                    provider_records_count += 1
                    name = str(cell_at(row_tuple, c_name) or '').strip()
                    raw_dt = cell_at(row_tuple, c_date)
                    dt = cls.parse_date(raw_dt)

                    val = quantize_amount(cell_at(row_tuple, c_val))
                    txval = quantize_amount(cell_at(row_tuple, c_txval))
                    iamt = quantize_amount(cell_at(row_tuple, c_iamt))
                    camt = quantize_amount(cell_at(row_tuple, c_camt))
                    samt = quantize_amount(cell_at(row_tuple, c_samt))
                    csamt = quantize_amount(cell_at(row_tuple, c_csamt))

                    pos = str(cell_at(row_tuple, c_pos) or '').strip()
                    rev = str(cell_at(row_tuple, c_rev) or 'N').strip().upper()
                    itc_val = str(cell_at(row_tuple, c_itc) or 'Y').strip().upper()
                    itcavl = itc_val in ['Y', 'YES', 'AVAILABLE', 'TRUE']

                    eff = resolve_document_financial_effect({'document_type': doc_type, 'note_type': str(cell_at(row_tuple, c_ntty) or '').strip() if (is_cdnr and c_ntty is not None) else ''})
                    nt_typ = 'C' if eff.is_credit_note else ('D' if eff.is_debit_note else '')

                    if txval == Decimal('0.00') and val > Decimal('0.00'):
                        txval = val

                    rec_itc = (iamt + camt + samt + csamt) if itcavl else Decimal('0.00')

                    total_taxable += (txval * eff.financial_sign)
                    total_itc += (rec_itc * eff.financial_sign)

                    doc_key = (gstin, norm_num, doc_type, '')
                    existing = existing_by_key.get(doc_key)
                    init_match_status = 'REVIEW_REQUIRED' if (dt is None or eff.is_review_required) else 'MISSING_IN_BOOKS'

                    if existing:
                        has_changes = (
                            existing.taxable_value != txval
                            or existing.invoice_value != val
                            or existing.igst_amount != iamt
                            or existing.cgst_amount != camt
                            or existing.sgst_amount != samt
                            or existing.cess_amount != csamt
                            or existing.itc_available != itcavl
                            or existing.invoice_date != dt
                        )
                        if has_changes:
                            existing.taxable_value = txval
                            existing.invoice_value = val
                            existing.igst_amount = iamt
                            existing.cgst_amount = camt
                            existing.sgst_amount = samt
                            existing.cess_amount = csamt
                            existing.place_of_supply = pos
                            existing.reverse_charge = rev
                            existing.itc_available = itcavl
                            existing.invoice_date = dt
                            existing.raw_invoice_date = str(raw_dt or '')
                            existing.import_batch = import_batch
                            if dt is None:
                                existing.match_status = 'REVIEW_REQUIRED'
                            records_to_update.append(existing)
                            records_updated_count += 1
                        else:
                            records_unchanged_count += 1
                    else:
                        new_rec = GSTR2BRecord(
                            import_batch=import_batch,
                            company=company,
                            gst_registration=registration,
                            return_period=fp,
                            document_type=doc_type,
                            original_document_number='',
                            supplier_gstin=gstin,
                            supplier_name=name,
                            invoice_number=inum,
                            normalized_invoice_number=norm_num,
                            invoice_type='R' if not is_cdnr else f"CDNR_{nt_typ}",
                            note_type=nt_typ if is_cdnr else '',
                            invoice_date=dt,
                            raw_invoice_date=str(raw_dt or ''),
                            invoice_value=val,
                            taxable_value=txval,
                            igst_amount=iamt,
                            cgst_amount=camt,
                            sgst_amount=samt,
                            cess_amount=csamt,
                            place_of_supply=pos,
                            reverse_charge=rev,
                            itc_available=itcavl,
                            match_status=init_match_status
                        )
                        records_to_create.append(new_rec)
                        existing_by_key[doc_key] = new_rec
                        records_created_count += 1

            parse_sheet_rows(b2b_sheet, is_cdnr=False)
            if cdnr_sheet:
                parse_sheet_rows(cdnr_sheet, is_cdnr=True)

            if records_to_create:
                GSTR2BRecord.objects.bulk_create(records_to_create, batch_size=500, ignore_conflicts=True)
            if records_to_update:
                GSTR2BRecord.objects.bulk_update(
                    records_to_update,
                    fields=[
                        'import_batch', 'taxable_value', 'invoice_value', 'igst_amount',
                        'cgst_amount', 'sgst_amount', 'cess_amount', 'invoice_date',
                        'raw_invoice_date', 'place_of_supply', 'reverse_charge',
                        'itc_available', 'note_type', 'match_status'
                    ],
                    batch_size=500
                )

            # 8. Update batch statistics reflecting true current batch operations (DEF-06 & DEF-03)
            final_rec_count = GSTR2BRecord.objects.filter(**rec_filter).count()
            actual_created_count = len(records_to_create)
            actual_updated_count = len(records_to_update)
            actual_unchanged_count = records_unchanged_count
            actual_rejected_count = 0
            batch_invoices_count = actual_created_count + actual_updated_count + actual_unchanged_count

            is_empty = (provider_records_count == 0)
            batch_status = 'EMPTY_PROCESSED' if is_empty else 'PROCESSED'

            import_batch.provider_records_count = provider_records_count
            import_batch.total_invoices_count = batch_invoices_count
            import_batch.period_records_count = final_rec_count
            import_batch.records_created = actual_created_count
            import_batch.records_updated = actual_updated_count
            import_batch.records_unchanged = actual_unchanged_count
            import_batch.records_rejected = actual_rejected_count
            import_batch.is_empty_statement = is_empty
            import_batch.total_taxable_amount = total_taxable
            import_batch.total_itc_available = total_itc
            import_batch.status = batch_status
            import_batch.save(update_fields=[
                'provider_records_count', 'total_invoices_count', 'period_records_count',
                'records_created', 'records_updated', 'records_unchanged', 'records_rejected',
                'is_empty_statement', 'total_taxable_amount', 'total_itc_available', 'status'
            ])

            cls.reconcile_period(company, return_period=fp, registration=registration)
            return import_batch
        finally:
            wb.close()

    @classmethod
    @transaction.atomic
    def reconcile_period(
        cls,
        company: Company,
        return_period: Optional[str] = None,
        registration: Optional[Any] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        periods: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Executes period-isolated multi-way reconciliation between:
        1. Buyer's Purchase Register vouchers
        2. Ingested GSTR-2B Records

        INVARIANTS:
        - Never marks vouchers from unrelated or future return periods as MISSING_IN_2B.
        - Classifies invoices reported in later return periods as LATER_PERIOD_MATCH.
        - Classifies invoices within the active filing window as NOT_YET_REFLECTED.
        - Classifies date-malformed documents as REVIEW_REQUIRED.
        - Enforces strict GSTIN isolation: never leaks unassigned records into single-GSTIN queries.
        """
        target_periods = []
        period_start_date = start_date
        period_end_date = end_date

        if return_period and return_period != 'ALL':
            p_info = GSTPeriodService.parse_return_period(return_period)
            target_periods = [p_info.normalized_period]
            period_start_date = p_info.start_date
            period_end_date = p_info.end_date
        elif periods:
            resolved_p_infos = GSTPeriodService.resolve_period_range(periods=periods)
            target_periods = [p.normalized_period for p in resolved_p_infos]
            if resolved_p_infos:
                period_start_date = resolved_p_infos[0].start_date
                period_end_date = resolved_p_infos[-1].end_date

        # 1. Fetch relevant GSTR-2B records
        rec_qs = GSTR2BRecord.objects.filter(company=company)
        if target_periods:
            rec_qs = rec_qs.filter(return_period__in=target_periods)
        if registration:
            rec_qs = rec_qs.filter(gst_registration=registration)

        gstr2b_records = list(rec_qs.select_related('import_batch'))

        # Build lookup indices for GSTR-2B records
        records_by_key: Dict[Tuple[str, str], GSTR2BRecord] = {}
        records_by_supplier_suffix: Dict[Tuple[str, str], List[GSTR2BRecord]] = {}

        for rec in gstr2b_records:
            gstin = rec.supplier_gstin.upper()
            norm_no = rec.normalized_invoice_number
            records_by_key[(gstin, norm_no)] = rec

            num_match = re.search(r'(\d+)$', norm_no)
            if num_match:
                suffix = num_match.group(1).lstrip('0') or '0'
                records_by_supplier_suffix.setdefault((gstin, suffix), []).append(rec)

        # 2. Determine eligible vouchers
        voucher_qs = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE'],
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).select_related('party_ledger').prefetch_related('items').defer('attachment_data', 'attachment_mime')

        # Multi-GSTIN strict isolation on vouchers (DEF-04):
        # When registration is provided, strictly isolate buyer_gstin to prevent leakage.
        if registration and registration.gstin:
            voucher_qs = voucher_qs.filter(buyer_gstin=registration.gstin)

        if period_end_date:
            voucher_qs = voucher_qs.filter(voucher_date__lte=period_end_date)

        vouchers = list(voucher_qs.order_by('voucher_date', 'voucher_number'))

        # Track return periods that actually have processed GSTR-2B statement data (DEF-03)
        stmt_qs = GSTR2BImport.objects.filter(company=company, status__in=['PROCESSED', 'EMPTY_PROCESSED'])
        if registration:
            stmt_qs = stmt_qs.filter(gst_registration=registration)
        processed_periods = set(stmt_qs.values_list('return_period', flat=True).distinct())

        matched_record_ids: Set[Any] = set()
        matched_voucher_ids: Set[Any] = set()
        vouchers_to_update = []
        records_to_update = []

        # 3. Match candidate vouchers against GSTR-2B records
        for v in vouchers:
            supp_gstin = (v.party_ledger.gstin if v.party_ledger and v.party_ledger.gstin else (v.buyer_gstin or '')).strip().upper()
            bill_num = (v.external_invoice_number or v.reference_number or v.voucher_number or '').strip()
            norm_bill_num = cls.normalize_invoice_number(bill_num)

            book_taxable = Decimal('0.00')
            book_cgst = Decimal('0.00')
            book_sgst = Decimal('0.00')
            book_igst = Decimal('0.00')
            book_cess = Decimal('0.00')

            for item in v.items.all():
                book_taxable += quantize_amount(item.taxable_amount)
                book_cgst += quantize_amount(item.cgst_amount)
                book_sgst += quantize_amount(item.sgst_amount)
                book_igst += quantize_amount(item.igst_amount)
                book_cess += quantize_amount(getattr(item, 'cess_amount', 0))

            book_total_tax = book_cgst + book_sgst + book_igst + book_cess

            # Attempt 1: Exact Key Match
            target_rec = records_by_key.get((supp_gstin, norm_bill_num))

            # Attempt 2: Trailing numeric suffix match if not matched
            if not target_rec and supp_gstin:
                num_match = re.search(r'(\d+)$', norm_bill_num)
                if num_match:
                    suffix = num_match.group(1).lstrip('0') or '0'
                    candidates = records_by_supplier_suffix.get((supp_gstin, suffix), [])
                    for cand in candidates:
                        if cand.id not in matched_record_ids:
                            target_rec = cand
                            break

            if target_rec:
                matched_record_ids.add(target_rec.id)
                matched_voucher_ids.add(v.id)
                target_rec.matched_voucher = v

                rec_total_tax = target_rec.cgst_amount + target_rec.sgst_amount + target_rec.igst_amount + target_rec.cess_amount
                taxable_diff = abs(book_taxable - target_rec.taxable_value)
                tax_diff = abs(book_total_tax - rec_total_tax)

                mismatches = []
                if taxable_diff > cls.TOLERANCE:
                    mismatches.append(f"Taxable value mismatch: Books ₹{book_taxable:,.2f} vs 2B ₹{target_rec.taxable_value:,.2f} (Diff ₹{taxable_diff:,.2f})")
                if tax_diff > cls.TOLERANCE:
                    mismatches.append(f"Tax amount mismatch: Books ₹{book_total_tax:,.2f} vs 2B ₹{rec_total_tax:,.2f} (Diff ₹{tax_diff:,.2f})")
                if (book_igst > Decimal('0.00') and target_rec.cgst_amount > Decimal('0.00')) or (book_cgst > Decimal('0.00') and target_rec.igst_amount > Decimal('0.00')):
                    mismatches.append("Tax head mismatch (Inter-state IGST vs Intra-state CGST/SGST)")

                # Cross-period matching distinction
                is_later_period = False
                if v.voucher_date and target_rec.return_period:
                    v_p_str = f"{str(v.voucher_date.month).zfill(2)}{v.voucher_date.year}"
                    if target_rec.return_period != v_p_str:
                        # Check if statement period is later than invoice date period
                        p_stmt = GSTPeriodService.parse_return_period(target_rec.return_period)
                        p_v = GSTPeriodService.parse_return_period(v_p_str)
                        if p_stmt.start_date > p_v.start_date:
                            is_later_period = True

                if target_rec.invoice_date is None:
                    target_rec.match_status = 'REVIEW_REQUIRED'
                    v.itc_match_status = 'REVIEW_REQUIRED'
                    v.itc_notes = f"Matched 2B record {target_rec.invoice_number} has an invalid or missing invoice date. Review required."
                elif mismatches:
                    target_rec.match_status = 'MISMATCHED'
                    target_rec.mismatch_details = {
                        'issues': mismatches,
                        'taxable_diff': float(taxable_diff),
                        'tax_diff': float(tax_diff),
                        'books_taxable': float(book_taxable),
                        'gstr2b_taxable': float(target_rec.taxable_value),
                        'books_tax': float(book_total_tax),
                        'gstr2b_tax': float(rec_total_tax)
                    }
                    v.itc_match_status = 'MISMATCHED'
                    v.itc_notes = " | ".join(mismatches)
                elif target_rec.is_amendment:
                    target_rec.match_status = 'AMENDED'
                    target_rec.mismatch_details = {}
                    v.itc_match_status = 'AMENDED'
                    v.itc_notes = f"Matched against amended GSTR-2B record ({target_rec.document_type} in {target_rec.return_period})."
                    if v.itc_held_amount > Decimal('0.00') and not (v.itc_notes or '').startswith('MANUAL_HOLD'):
                        v.itc_held_amount = Decimal('0.00')
                elif is_later_period:
                    target_rec.match_status = 'LATER_PERIOD_MATCH'
                    target_rec.mismatch_details = {}
                    v.itc_match_status = 'LATER_PERIOD_MATCH'
                    v.itc_notes = f"Reconciled in later GSTR-2B statement ({target_rec.return_period}). Supplier filed GSTR-1 after invoice period."
                    if v.itc_held_amount > Decimal('0.00') and not (v.itc_notes or '').startswith('MANUAL_HOLD'):
                        v.itc_held_amount = Decimal('0.00')
                else:
                    target_rec.match_status = 'MATCHED'
                    target_rec.mismatch_details = {}
                    v.itc_match_status = 'MATCHED'
                    v.itc_notes = f"Reconciled successfully with GSTR-2B ({target_rec.return_period})."
                    if v.itc_held_amount > Decimal('0.00') and not (v.itc_notes or '').startswith('MANUAL_HOLD'):
                        v.itc_held_amount = Decimal('0.00')

                records_to_update.append(target_rec)
                vouchers_to_update.append(v)
            else:
                # Voucher did not match any 2B record in target periods.
                # PERIOD ISOLATION GUARD:
                # Do NOT mark vouchers from outside the reconciled period as missing.
                # Do NOT overwrite a voucher that was ALREADY MATCHED in another return period.
                in_period_window = True
                if period_start_date and v.voucher_date and v.voucher_date < period_start_date:
                    in_period_window = False
                if period_end_date and v.voucher_date and v.voucher_date > period_end_date:
                    in_period_window = False

                if in_period_window and v.itc_match_status not in ['MATCHED', 'LATER_PERIOD_MATCH', 'AMENDED']:
                    stmt_res = GSTPeriodService.resolve_gstr2b_statement_period(
                        invoice_date=v.voucher_date,
                        recipient_registration=registration,
                        statement_metadata=processed_periods
                    )
                    expected_stmt_period = stmt_res.expected_statement_period
                    stmt_available = (expected_stmt_period in processed_periods) if expected_stmt_period else False

                    # Check active filing window: supplier has until the 14th of the succeeding month to file GSTR-1
                    today = timezone.now().date()
                    is_within_filing_window = False
                    if v.voucher_date:
                        # Auto-draft cutoff is typically 14th of following month
                        next_m_y = v.voucher_date.year if v.voucher_date.month < 12 else v.voucher_date.year + 1
                        next_m = v.voucher_date.month + 1 if v.voucher_date.month < 12 else 1
                        filing_cutoff = date(next_m_y, next_m, 14)
                        if today <= filing_cutoff:
                            is_within_filing_window = True

                    if not stmt_available:
                        # Never infer missing invoice without an imported, processed statement for that period (DEF-03 & DEF-02)
                        v.itc_match_status = 'DATA_UNAVAILABLE'
                        v.itc_notes = f"GSTR-2B statement for return period {expected_stmt_period} has not been imported. Data unavailable."
                    elif is_within_filing_window:
                        v.itc_match_status = 'NOT_YET_REFLECTED'
                        v.itc_notes = f"Invoice dated {v.voucher_date} is within supplier GSTR-1 filing window. Pending auto-draft in next GSTR-2B."
                    else:
                        v.itc_match_status = 'MISSING_IN_2B'
                        period_desc = f" ({return_period})" if return_period else ""
                        v.itc_notes = f"Invoice not found in GSTR-2B{period_desc}. Vendor has not filed GSTR-1."
                        if (v.itc_held_amount is None or v.itc_held_amount == Decimal('0.00')) and book_total_tax > Decimal('0.00'):
                            v.itc_held_amount = book_total_tax
                    vouchers_to_update.append(v)

        # 4. Mark unmatched GSTR-2B records
        for rec in gstr2b_records:
            if rec.id not in matched_record_ids:
                if rec.invoice_date is None:
                    if rec.match_status != 'REVIEW_REQUIRED':
                        rec.match_status = 'REVIEW_REQUIRED'
                        rec.matched_voucher = None
                        records_to_update.append(rec)
                elif rec.match_status != 'MISSING_IN_BOOKS' or rec.matched_voucher is not None:
                    rec.match_status = 'MISSING_IN_BOOKS'
                    rec.matched_voucher = None
                    records_to_update.append(rec)

        # 5. Bulk update changes
        if vouchers_to_update:
            Voucher.objects.bulk_update(vouchers_to_update, ['itc_match_status', 'itc_held_amount', 'itc_notes'], batch_size=200)

        if records_to_update:
            GSTR2BRecord.objects.bulk_update(records_to_update, ['match_status', 'matched_voucher', 'mismatch_details'], batch_size=200)

        return cls.get_summary_stats(company, return_period=return_period, registration=registration)

    @classmethod
    def get_scoped_reconciliation_data(
        cls,
        company: Company,
        return_period: Optional[str] = None,
        registration: Optional[Any] = None,
        status_filter: str = 'ALL',
        search_query: str = ''
    ) -> Dict[str, Any]:
        """
        Single authoritative query and filtering engine for both list view and summary stats.
        Guarantees 100% mathematical consistency across:
        - ITCReconciliationListView
        - ITCSummaryView
        - Dashboard metrics cards
        """
        filter_status = (status_filter or 'ALL').upper()
        norm_period = None
        period_start = None
        period_end = None

        if return_period and return_period != 'ALL':
            p_info = GSTPeriodService.parse_return_period(return_period)
            norm_period = p_info.normalized_period
            period_start = p_info.start_date
            period_end = p_info.end_date

        # 1. Base Vouchers Query
        voucher_qs = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE'],
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).select_related('party_ledger').prefetch_related('items', 'gstr2b_matches').defer('attachment_data', 'attachment_mime')

        # Strict Multi-GSTIN isolation (DEF-04):
        if registration and registration.gstin:
            voucher_qs = voucher_qs.filter(buyer_gstin=registration.gstin)

        if norm_period:
            voucher_qs = voucher_qs.filter(voucher_date__year=p_info.year_int, voucher_date__month=p_info.month_int)

        # Track return periods that actually have processed GSTR-2B statement data (DEF-03)
        stmt_qs = GSTR2BImport.objects.filter(company=company, status__in=['PROCESSED', 'EMPTY_PROCESSED'])
        if registration:
            stmt_qs = stmt_qs.filter(gst_registration=registration)
        processed_periods = set(stmt_qs.values_list('return_period', flat=True).distinct())

        company_gstins = set(
            GSTRegistration.objects.filter(company=company, status='ACTIVE').values_list('gstin', flat=True)
        )

        today = timezone.now().date()
        current_fy_start_year = today.year if today.month >= 4 else today.year - 1
        prev_fy_start = date(current_fy_start_year - 1, 4, 1)
        prev_fy_end = date(current_fy_start_year, 3, 31)

        voucher_items = []
        for v in voucher_qs:
            matched_rec = v.gstr2b_matches.first()
            raw_status = v.itc_match_status or 'UNCHECKED'

            stmt_res = GSTPeriodService.resolve_gstr2b_statement_period(
                invoice_date=v.voucher_date,
                recipient_registration=registration,
                statement_metadata=processed_periods
            )
            expected_stmt_period = stmt_res.expected_statement_period
            stmt_imported = (expected_stmt_period in processed_periods) if expected_stmt_period else False

            # Check for unmapped GSTIN (DEF-04)
            is_unmapped_gstin = False
            v_buyer = (v.buyer_gstin or '').strip().upper()
            if not v_buyer or v_buyer not in company_gstins:
                is_unmapped_gstin = True

            if matched_rec:
                eff_status = v.itc_match_status if v.itc_match_status in ['MATCHED', 'MISMATCHED', 'LATER_PERIOD_MATCH', 'AMENDED', 'REVIEW_REQUIRED'] else 'MATCHED'
            elif is_unmapped_gstin:
                eff_status = 'UNMAPPED_GSTIN'
            elif not stmt_imported:
                # Never infer missing invoice without an imported, processed statement for that return period
                eff_status = 'DATA_UNAVAILABLE' if raw_status in ['UNCHECKED', 'DATA_UNAVAILABLE'] else raw_status
            else:
                eff_status = raw_status if raw_status != 'UNCHECKED' else 'MISSING_IN_2B'

            b_taxable = sum(quantize_amount(i.taxable_amount) for i in v.items.all())
            b_cgst = sum(quantize_amount(i.cgst_amount) for i in v.items.all())
            b_sgst = sum(quantize_amount(i.sgst_amount) for i in v.items.all())
            b_igst = sum(quantize_amount(i.igst_amount) for i in v.items.all())
            b_cess = sum(quantize_amount(getattr(i, 'cess_amount', 0)) for i in v.items.all())
            b_total_tax = b_cgst + b_sgst + b_igst + b_cess

            supplier_name = v.party_ledger.name if v.party_ledger else (v.buyer_name or 'Unknown')
            supplier_gstin = (v.party_ledger.gstin if v.party_ledger and v.party_ledger.gstin else (v.buyer_gstin or '')).upper()
            inv_no = v.external_invoice_number or v.reference_number or v.voucher_number or ''

            g2b_data = None
            if matched_rec:
                g2b_data = {
                    'invoice_number': matched_rec.invoice_number,
                    'invoice_date': matched_rec.invoice_date.isoformat() if matched_rec.invoice_date else '',
                    'taxable_value': float(matched_rec.taxable_value),
                    'total_tax': float(matched_rec.cgst_amount + matched_rec.sgst_amount + matched_rec.igst_amount + matched_rec.cess_amount),
                    'cgst': float(matched_rec.cgst_amount),
                    'sgst': float(matched_rec.sgst_amount),
                    'igst': float(matched_rec.igst_amount),
                    'mismatch_details': matched_rec.mismatch_details
                }

            is_prev_fy = bool(v.voucher_date and prev_fy_start <= v.voucher_date <= prev_fy_end)

            voucher_items.append({
                'voucher': v,
                'source': 'BOOKS',
                'voucher_id': str(v.id),
                'voucher_number': v.voucher_number,
                'invoice_number': inv_no,
                'invoice_date': v.voucher_date.isoformat() if v.voucher_date else '',
                'supplier_name': supplier_name,
                'supplier_gstin': supplier_gstin,
                'books_taxable': float(b_taxable),
                'books_tax': float(b_total_tax),
                'books_total': float(v.total_amount),
                'itc_match_status': eff_status,
                'itc_held_amount': float(v.itc_held_amount or 0),
                'itc_notes': v.itc_notes,
                'gstr2b_record': g2b_data,
                'is_prev_fy': is_prev_fy,
                'b_taxable_dec': b_taxable,
                'b_total_tax_dec': b_total_tax,
                'b_held_dec': quantize_amount(v.itc_held_amount or 0)
            })

        # 2. Base 2B Query
        rec_qs = GSTR2BRecord.objects.filter(company=company)
        if norm_period:
            rec_qs = rec_qs.filter(return_period=norm_period)
        if registration:
            rec_qs = rec_qs.filter(gst_registration=registration)

        record_items = []
        for rec in rec_qs.select_related('import_batch'):
            rec_total_tax = rec.cgst_amount + rec.sgst_amount + rec.igst_amount + rec.cess_amount
            record_items.append({
                'record': rec,
                'source': 'GSTR2B',
                'voucher_id': None,
                'record_id': str(rec.id),
                'invoice_number': rec.invoice_number,
                'invoice_date': rec.invoice_date.isoformat() if rec.invoice_date else '',
                'supplier_name': rec.supplier_name or 'Unmapped Vendor',
                'supplier_gstin': rec.supplier_gstin,
                'books_taxable': 0.0,
                'books_tax': 0.0,
                'books_total': 0.0,
                'itc_match_status': rec.match_status,
                'itc_held_amount': 0.0,
                'itc_notes': 'Reflecting in GSTR-2B but missing in your Purchase Register. You may be missing out on this ITC!' if rec.match_status == 'MISSING_IN_BOOKS' else 'Date malformed or review required.',
                'gstr2b_record': {
                    'invoice_number': rec.invoice_number,
                    'invoice_date': rec.invoice_date.isoformat() if rec.invoice_date else '',
                    'taxable_value': float(rec.taxable_value),
                    'total_tax': float(rec_total_tax),
                    'cgst': float(rec.cgst_amount),
                    'sgst': float(rec.sgst_amount),
                    'igst': float(rec.igst_amount),
                    'mismatch_details': rec.mismatch_details or {}
                },
                'is_prev_fy': False,
                'b_taxable_dec': Decimal('0.00'),
                'b_total_tax_dec': Decimal('0.00'),
                'b_held_dec': Decimal('0.00'),
                'rec_taxable_dec': quantize_amount(rec.taxable_value),
                'rec_tax_dec': quantize_amount(rec_total_tax),
                'note_type': rec.note_type,
                'document_type': rec.document_type
            })

        # Calculate Canonical Summary Stats
        itc_safe = Decimal('0.00')
        itc_at_risk = Decimal('0.00')
        itc_held_total = Decimal('0.00')
        matched_count = 0
        mismatched_count = 0
        missing_in_2b_count = 0
        review_required_count = 0
        later_period_count = 0
        amended_count = 0
        not_yet_reflected_count = 0
        data_unavailable_count = 0
        unmapped_gstin_count = 0
        unchecked_count = 0

        verified_missing_itc = Decimal('0.00')
        mismatch_exposure = Decimal('0.00')
        data_unavailable_itc = Decimal('0.00')
        unmapped_gstin_itc = Decimal('0.00')
        review_required_itc = Decimal('0.00')

        for vi in voucher_items:
            st = vi['itc_match_status']
            t = vi['b_total_tax_dec']
            itc_held_total += vi['b_held_dec']

            if st in ['MATCHED', 'LATER_PERIOD_MATCH', 'AMENDED']:
                matched_count += 1
                itc_safe += t
                if st == 'LATER_PERIOD_MATCH':
                    later_period_count += 1
                elif st == 'AMENDED':
                    amended_count += 1
            elif st == 'MISMATCHED':
                mismatched_count += 1
                mismatch_exposure += t
            elif st == 'MISSING_IN_2B':
                missing_in_2b_count += 1
                verified_missing_itc += t
            elif st == 'REVIEW_REQUIRED':
                review_required_count += 1
                review_required_itc += t
            elif st == 'NOT_YET_REFLECTED':
                not_yet_reflected_count += 1
            elif st == 'DATA_UNAVAILABLE':
                data_unavailable_count += 1
                data_unavailable_itc += t
            elif st == 'UNMAPPED_GSTIN':
                unmapped_gstin_count += 1
                unmapped_gstin_itc += t
            elif st == 'UNCHECKED':
                unchecked_count += 1

        # DEF-08: ITC at Risk strictly contains verified missing ITC and mismatch exposure
        # DATA_UNAVAILABLE and UNMAPPED_GSTIN are reported as separate informational metrics
        itc_at_risk = verified_missing_itc + mismatch_exposure

        missing_in_books_count = sum(1 for ri in record_items if ri['itc_match_status'] == 'MISSING_IN_BOOKS')
        # Signed CDNR Accounting (DEF-01): Credit notes reduce net missing ITC, debit notes increase it
        missing_in_books_gross = sum(
            ri['rec_tax_dec'] for ri in record_items
            if ri['itc_match_status'] == 'MISSING_IN_BOOKS'
            and not (ri['note_type'] == 'C' or ri['document_type'] in ['CDNR', 'CDNRA'] and ri['note_type'] != 'D')
            and not (ri['note_type'] == 'D')
        )
        missing_in_books_credit = sum(
            ri['rec_tax_dec'] for ri in record_items
            if ri['itc_match_status'] == 'MISSING_IN_BOOKS'
            and (ri['note_type'] == 'C' or ri['document_type'] in ['CDNR', 'CDNRA'] and ri['note_type'] != 'D')
        )
        missing_in_books_debit = sum(
            ri['rec_tax_dec'] for ri in record_items
            if ri['itc_match_status'] == 'MISSING_IN_BOOKS'
            and (ri['note_type'] == 'D')
        )
        missing_in_books_itc = missing_in_books_gross + missing_in_books_debit - missing_in_books_credit

        # CDNR breakdown on GSTR-2B side
        gross_invoices_count = sum(1 for ri in record_items if ri['document_type'] in ['B2B', 'B2BA'])
        credit_notes_count = sum(1 for ri in record_items if ri['note_type'] == 'C' or ri['document_type'] in ['CDNR', 'CDNRA'] and ri['note_type'] != 'D')
        debit_notes_count = sum(1 for ri in record_items if ri['note_type'] == 'D')

        summary = {
            'itc_at_risk': float(itc_at_risk),
            'itc_safe': float(itc_safe),
            'itc_held_total': float(itc_held_total),
            'verified_missing_itc': float(verified_missing_itc),
            'mismatch_exposure': float(mismatch_exposure),
            'data_unavailable_itc': float(data_unavailable_itc),
            'unmapped_gstin_itc': float(unmapped_gstin_itc),
            'review_required_itc': float(review_required_itc),
            'matched_count': matched_count,
            'mismatched_count': mismatched_count,
            'missing_in_2b_count': missing_in_2b_count,
            'missing_in_books_count': missing_in_books_count,
            'missing_in_books_itc': float(missing_in_books_itc),
            'missing_in_books_gross_itc': float(missing_in_books_gross),
            'missing_in_books_credit_itc': float(missing_in_books_credit),
            'missing_in_books_debit_itc': float(missing_in_books_debit),
            'review_required_count': review_required_count,
            'later_period_count': later_period_count,
            'amended_count': amended_count,
            'not_yet_reflected_count': not_yet_reflected_count,
            'data_unavailable_count': data_unavailable_count,
            'unmapped_gstin_count': unmapped_gstin_count,
            'unchecked_count': unchecked_count,
            'gross_invoices_count': gross_invoices_count,
            'credit_notes_count': credit_notes_count,
            'debit_notes_count': debit_notes_count,
            'return_period': return_period or 'ALL'
        }

        # Filter items for List View
        filtered_results = []
        q = (search_query or '').lower()

        # Books side items
        for vi in voucher_items:
            st = vi['itc_match_status']
            if filter_status == 'EXPIRING_SEC16_4':
                if not (vi['is_prev_fy'] and st in ['MISSING_IN_2B', 'MISMATCHED', 'REVIEW_REQUIRED']):
                    continue
            elif filter_status == 'MISSING_IN_BOOKS':
                continue
            elif filter_status not in ['ALL', 'EXPIRING_SEC16_4']:
                if st != filter_status:
                    continue

            if q:
                if q not in vi['supplier_name'].lower() and q not in vi['supplier_gstin'].lower() and q not in vi['invoice_number'].lower():
                    continue

            # Strip non-serializable dec helper keys
            clean_item = {k: v for k, v in vi.items() if not k.endswith('_dec') and k not in ['voucher', 'is_prev_fy']}
            filtered_results.append(clean_item)

        # 2B side items (Missing in books or Review required)
        if filter_status in ['ALL', 'MISSING_IN_BOOKS', 'REVIEW_REQUIRED']:
            for ri in record_items:
                st = ri['itc_match_status']
                if filter_status == 'MISSING_IN_BOOKS' and st != 'MISSING_IN_BOOKS':
                    continue
                if filter_status == 'REVIEW_REQUIRED' and st != 'REVIEW_REQUIRED':
                    continue
                if filter_status == 'ALL' and st not in ['MISSING_IN_BOOKS', 'REVIEW_REQUIRED']:
                    continue

                if q:
                    if q not in ri['supplier_name'].lower() and q not in ri['supplier_gstin'].lower() and q not in ri['invoice_number'].lower():
                        continue

                clean_item = {k: v for k, v in ri.items() if not k.endswith('_dec') and k not in ['record', 'is_prev_fy', 'note_type', 'document_type']}
                filtered_results.append(clean_item)

        return {
            'summary': summary,
            'results': filtered_results,
            'count': len(filtered_results)
        }

    @classmethod
    def get_summary_stats(
        cls,
        company: Company,
        return_period: Optional[str] = None,
        registration: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Aggregates live compliance metrics for the ITC Risk Shield dashboard.
        Delegates directly to get_scoped_reconciliation_data for 100% mathematical consistency.
        """
        scoped = cls.get_scoped_reconciliation_data(
            company=company,
            return_period=return_period,
            registration=registration
        )
        return scoped['summary']

    @classmethod
    def get_sec16_4_expiry_radar(cls, company: Company, registration: Optional[Any] = None) -> Dict[str, Any]:
        """
        Section 16(4) Radar: Invoices of FY (T-1) must be claimed by 30th November of FY (T).
        Detects un-reconciled purchase invoices that are approaching this hard legal deadline.
        Excludes records with missing, invalid, or fabricated invoice dates.
        """
        today = timezone.now().date()
        current_fy_start_year = today.year if today.month >= 4 else today.year - 1
        deadline = date(current_fy_start_year, 11, 30)

        days_remaining = (deadline - today).days

        prev_fy_start = date(current_fy_start_year - 1, 4, 1)
        prev_fy_end = date(current_fy_start_year, 3, 31)

        voucher_qs = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE'],
            voucher_date__gte=prev_fy_start,
            voucher_date__lte=prev_fy_end,
            voucher_date__isnull=False,
            itc_match_status__in=['MISSING_IN_2B', 'MISMATCHED', 'REVIEW_REQUIRED'],
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).select_related('party_ledger').prefetch_related('items').defer('attachment_data', 'attachment_mime')

        # Multi-GSTIN strict isolation (DEF-04):
        if registration and registration.gstin:
            voucher_qs = voucher_qs.filter(buyer_gstin=registration.gstin)

        expiring_list = []
        total_expiring_itc = Decimal('0.00')

        for v in voucher_qs:
            # Exclude records without valid dates
            if not v.voucher_date:
                continue

            tax = sum(quantize_amount(i.cgst_amount + i.sgst_amount + i.igst_amount + getattr(i, 'cess_amount', 0)) for i in v.items.all())
            total_expiring_itc += tax
            expiring_list.append({
                'voucher_id': str(v.id),
                'voucher_number': v.voucher_number,
                'invoice_number': v.external_invoice_number or v.reference_number or v.voucher_number,
                'supplier_name': v.party_ledger.name if v.party_ledger else (v.buyer_name or 'Unknown'),
                'voucher_date': v.voucher_date.isoformat(),
                'tax_amount': float(tax),
                'match_status': v.itc_match_status
            })

        return {
            'deadline': deadline.isoformat(),
            'days_remaining': max(0, days_remaining),
            'is_critical': 0 <= days_remaining <= 60,
            'total_expiring_itc': float(total_expiring_itc),
            'expiring_count': len(expiring_list),
            'items': expiring_list
        }
