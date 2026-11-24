import re
import json
import logging
from decimal import Decimal
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Set
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from apps.companies.models import Company
from apps.accounting.models import Voucher, VoucherItem
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService
from apps.gst.models import GSTR2BImport, GSTR2BRecord, GSTRegistration
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
    and multi-GSTIN tenant isolation.
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
        Parses various date formats from GST Portal (DD-MM-YYYY, YYYY-MM-DD, DD/MM/YYYY).
        """
        if not dt_str:
            return None
        if isinstance(dt_str, (date, datetime)):
            return dt_str.date() if isinstance(dt_str, datetime) else dt_str

        dt_str = str(dt_str).strip()
        for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%d-%b-%Y', '%Y/%m/%d'):
            try:
                return datetime.strptime(dt_str, fmt).date()
            except ValueError:
                continue
        return None

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
        """
        if isinstance(json_data, (str, bytes)):
            json_data = json.loads(json_data)

        # 1. Canonical return period resolution
        raw_fp = return_period or json_data.get('fp') or json_data.get('data', {}).get('fp')
        period_info = GSTPeriodService.parse_return_period(raw_fp)
        fp = period_info.normalized_period
        fy = period_info.financial_year

        # 2. Resolve and validate GST registration
        if registration is not None and isinstance(registration, GSTRegistration):
            if registration.company_id != company.id:
                raise ValidationError("GST Registration does not belong to this company.")
        else:
            target_gstin = str(json_data.get('gstin') or json_data.get('data', {}).get('gstin') or '').strip().upper()
            if target_gstin:
                registration = GSTRegistration.objects.filter(company=company, gstin=target_gstin).first()
            if not registration:
                registration = (
                    GSTRegistration.objects.filter(company=company, is_primary=True, status='ACTIVE').first()
                    or GSTRegistration.objects.filter(company=company, status='ACTIVE').first()
                )

        # 3. Create Import Batch Audit Entry
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

        # 4. Fetch existing records for this return period to support idempotent upsert
        rec_filter = {'company': company, 'return_period': fp}
        if registration:
            rec_filter['gst_registration'] = registration
        else:
            rec_filter['gst_registration__isnull'] = True

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

        # 5. Extract tables: B2B, B2BA, CDNR, CDNRA
        data_root = json_data.get('data', json_data)
        b2b_list = data_root.get('b2b', [])
        b2ba_list = data_root.get('b2ba', [])
        cdnr_list = data_root.get('cdnr', [])
        cdnra_list = data_root.get('cdnra', [])

        # Process B2B and B2BA
        for doc_type, supplier_entry in [('B2B', s) for s in b2b_list] + [('B2BA', s) for s in b2ba_list]:
            ctin = str(supplier_entry.get('ctin', '')).strip().upper()
            trdnm = str(supplier_entry.get('trdnm') or supplier_entry.get('lgl_name') or '').strip()
            invoices = supplier_entry.get('inv', [])
            for inv in invoices:
                provider_records_count += 1
                inum = str(inv.get('inum', '')).strip()
                if not inum:
                    continue
                norm_num = cls.normalize_invoice_number(inum)
                dt = cls.parse_date(inv.get('dt')) or period_info.end_date
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
                        existing.import_batch = import_batch
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
                        match_status='MISSING_IN_BOOKS'
                    )
                    records_to_create.append(new_rec)
                    existing_by_key[doc_key] = new_rec
                    records_created_count += 1

        # Process CDNR and CDNRA
        for doc_type, supplier_entry in [('CDNR', s) for s in cdnr_list] + [('CDNRA', s) for s in cdnra_list]:
            ctin = str(supplier_entry.get('ctin', '')).strip().upper()
            trdnm = str(supplier_entry.get('trdnm') or supplier_entry.get('lgl_name') or '').strip()
            notes = supplier_entry.get('nt', [])
            for nt in notes:
                provider_records_count += 1
                nt_num = str(nt.get('nt_num', '')).strip()
                if not nt_num:
                    continue
                norm_num = cls.normalize_invoice_number(nt_num)
                dt = cls.parse_date(nt.get('nt_dt')) or period_info.end_date
                val = quantize_amount(nt.get('val', '0'))
                nt_typ = str(nt.get('ntty', 'C')).strip()
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
                total_taxable += nt_txval
                total_itc += rec_itc

                doc_key = (ctin, norm_num, doc_type, orig_num)
                existing = existing_by_key.get(doc_key)
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
                        existing.import_batch = import_batch
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
                        invoice_date=dt,
                        invoice_value=val,
                        taxable_value=nt_txval,
                        igst_amount=nt_iamt,
                        cgst_amount=nt_camt,
                        sgst_amount=nt_samt,
                        cess_amount=nt_csamt,
                        itc_available=itcavl,
                        match_status='MISSING_IN_BOOKS'
                    )
                    records_to_create.append(new_rec)
                    existing_by_key[doc_key] = new_rec
                    records_created_count += 1

        # 6. Bulk write changes
        if records_to_create:
            GSTR2BRecord.objects.bulk_create(records_to_create, batch_size=500)
        if records_to_update:
            GSTR2BRecord.objects.bulk_update(
                records_to_update,
                fields=[
                    'import_batch', 'taxable_value', 'invoice_value', 'igst_amount',
                    'cgst_amount', 'sgst_amount', 'cess_amount', 'invoice_date',
                    'place_of_supply', 'reverse_charge', 'itc_available', 'itc_ineligible_reason'
                ],
                batch_size=500
            )

        # 7. Update batch statistics
        import_batch.provider_records_count = provider_records_count
        import_batch.total_invoices_count = records_created_count + records_updated_count + records_unchanged_count
        import_batch.records_created = records_created_count
        import_batch.records_updated = records_updated_count
        import_batch.records_unchanged = records_unchanged_count
        import_batch.total_taxable_amount = total_taxable
        import_batch.total_itc_available = total_itc
        import_batch.status = 'PROCESSED'
        import_batch.save(update_fields=[
            'provider_records_count', 'total_invoices_count', 'records_created',
            'records_updated', 'records_unchanged', 'total_taxable_amount',
            'total_itc_available', 'status'
        ])

        # 8. Run period-isolated reconciliation for this period
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
        """
        import openpyxl
        from apps.accounting.services.upload_security import UploadValidationError

        wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
        try:
            # 1. Normalize return period
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
                    now = timezone.now()
                    prev_m = now.month - 1 if now.month > 1 else 12
                    prev_y = now.year if now.month > 1 else now.year - 1
                    p_info = GSTPeriodService.parse_return_period(f"{str(prev_m).zfill(2)}{prev_y}")
                    fp = p_info.normalized_period
                    fy = p_info.financial_year

            # 2. Resolve registration
            if registration is not None and isinstance(registration, GSTRegistration):
                if registration.company_id != company.id:
                    raise ValidationError("GST Registration does not belong to this company.")
            else:
                registration = (
                    GSTRegistration.objects.filter(company=company, is_primary=True, status='ACTIVE').first()
                    or GSTRegistration.objects.filter(company=company, status='ACTIVE').first()
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

            b2b_sheet = None
            for sname in wb.sheetnames:
                clean_name = sname.lower().replace(' ', '').replace('_', '').replace('-', '')
                if 'b2b' in clean_name and 'cdn' not in clean_name:
                    b2b_sheet = wb[sname]
                    break
            if not b2b_sheet:
                b2b_sheet = wb.active

            row_iter = b2b_sheet.iter_rows(values_only=True)
            header_row = None
            for row in row_iter:
                row_str = " ".join([str(c or '').lower() for c in row])
                if 'gstin' in row_str and ('invoice' in row_str or 'taxable' in row_str or 'doc' in row_str):
                    header_row = [str(c or '').strip().lower() for c in row]
                    break

            if not header_row:
                raise UploadValidationError("Could not detect valid GSTR-2B column headers in Excel sheet.")

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

            c_gstin = get_col(['gstin of supplier', 'gstin'])
            c_name = get_col(['legal name', 'trade name', 'supplier name', 'name'])
            c_inum = get_col(['invoice number', 'inv no', 'document number', 'note number'])
            c_date = get_col(['invoice date', 'inv dt', 'document date', 'note date'])
            c_val = get_col(['invoice value', 'inv val', 'document value', 'note value'])
            c_pos = get_col(['place of supply', 'pos'])
            c_rev = get_col(['reverse charge', 'rev chg'])
            c_txval = get_col(['taxable value', 'taxable'])
            c_iamt = get_col(['integrated tax', 'igst'])
            c_camt = get_col(['central tax', 'cgst'])
            c_samt = get_col(['state/ut tax', 'sgst', 'state tax'])
            c_csamt = get_col(['cess'])
            c_itc = get_col(['itc availability', 'itc available', 'itc'])

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
                dt = cls.parse_date(raw_dt) or p_info.end_date

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

                if txval == Decimal('0.00') and val > Decimal('0.00'):
                    txval = val

                rec_itc = (iamt + camt + samt + csamt) if itcavl else Decimal('0.00')
                total_taxable += txval
                total_itc += rec_itc

                doc_key = (gstin, norm_num, 'B2B', '')
                existing = existing_by_key.get(doc_key)
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
                        existing.import_batch = import_batch
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
                        document_type='B2B',
                        original_document_number='',
                        supplier_gstin=gstin,
                        supplier_name=name,
                        invoice_number=inum,
                        normalized_invoice_number=norm_num,
                        invoice_type='R',
                        invoice_date=dt,
                        invoice_value=val,
                        taxable_value=txval,
                        igst_amount=iamt,
                        cgst_amount=camt,
                        sgst_amount=samt,
                        cess_amount=csamt,
                        place_of_supply=pos,
                        reverse_charge=rev,
                        itc_available=itcavl,
                        match_status='MISSING_IN_BOOKS'
                    )
                    records_to_create.append(new_rec)
                    existing_by_key[doc_key] = new_rec
                    records_created_count += 1

            if records_to_create:
                GSTR2BRecord.objects.bulk_create(records_to_create, batch_size=500)
            if records_to_update:
                GSTR2BRecord.objects.bulk_update(
                    records_to_update,
                    fields=[
                        'import_batch', 'taxable_value', 'invoice_value', 'igst_amount',
                        'cgst_amount', 'sgst_amount', 'cess_amount', 'invoice_date',
                        'place_of_supply', 'reverse_charge', 'itc_available'
                    ],
                    batch_size=500
                )

            import_batch.provider_records_count = provider_records_count
            import_batch.total_invoices_count = records_created_count + records_updated_count + records_unchanged_count
            import_batch.records_created = records_created_count
            import_batch.records_updated = records_updated_count
            import_batch.records_unchanged = records_unchanged_count
            import_batch.total_taxable_amount = total_taxable
            import_batch.total_itc_available = total_itc
            import_batch.status = 'PROCESSED'
            import_batch.save(update_fields=[
                'provider_records_count', 'total_invoices_count', 'records_created',
                'records_updated', 'records_unchanged', 'total_taxable_amount',
                'total_itc_available', 'status'
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

        INVARIANT: Never marks vouchers from unrelated/future return periods as MISSING_IN_2B.
        Preserves existing clean matches across other return periods.
        """
        # Resolve target return periods and date boundaries
        target_periods = []
        period_start_date = start_date
        period_end_date = end_date

        if return_period:
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
            rec_qs = rec_qs.filter(Q(gst_registration=registration) | Q(gst_registration__isnull=True))

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
        # Eligible vouchers are those with date <= period_end_date (cannot match future invoices!)
        voucher_qs = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE'],
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).select_related('party_ledger').prefetch_related('items').defer('attachment_data', 'attachment_mime')

        if period_end_date:
            voucher_qs = voucher_qs.filter(voucher_date__lte=period_end_date)
        if period_start_date:
            # When running multi-period or isolated period, vouchers eligible for missing check
            pass

        vouchers = list(voucher_qs.order_by('voucher_date', 'voucher_number'))

        matched_record_ids: Set[Any] = set()
        matched_voucher_ids: Set[Any] = set()
        vouchers_to_update = []
        records_to_update = []

        # 3. Match candidate vouchers against GSTR-2B records
        for v in vouchers:
            supp_gstin = (v.party_ledger.gstin if v.party_ledger and v.party_ledger.gstin else (v.buyer_gstin or '')).strip().upper()
            bill_num = (v.external_invoice_number or v.reference_number or v.voucher_number or '').strip()
            norm_bill_num = cls.normalize_invoice_number(bill_num)

            # Book tax totals
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

                if mismatches:
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
                # Only mark as MISSING_IN_2B if the voucher date falls within the reconciled window!
                # Do NOT mark vouchers from outside the reconciled period as missing.
                # Do NOT overwrite a voucher that was ALREADY MATCHED in another return period.
                in_period_window = True
                if period_start_date and v.voucher_date and v.voucher_date < period_start_date:
                    in_period_window = False
                if period_end_date and v.voucher_date and v.voucher_date > period_end_date:
                    in_period_window = False

                if in_period_window and v.itc_match_status != 'MATCHED':
                    v.itc_match_status = 'MISSING_IN_2B'
                    period_desc = f" ({return_period})" if return_period else ""
                    v.itc_notes = f"Invoice not found in GSTR-2B{period_desc}. Vendor has not filed GSTR-1."
                    if (v.itc_held_amount is None or v.itc_held_amount == Decimal('0.00')) and book_total_tax > Decimal('0.00'):
                        v.itc_held_amount = book_total_tax
                    vouchers_to_update.append(v)

        # 4. Mark unmatched GSTR-2B records as MISSING_IN_BOOKS
        for rec in gstr2b_records:
            if rec.id not in matched_record_ids:
                if rec.match_status != 'MISSING_IN_BOOKS' or rec.matched_voucher is not None:
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
    def get_summary_stats(
        cls,
        company: Company,
        return_period: Optional[str] = None,
        registration: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Aggregates live compliance metrics for the ITC Risk Shield dashboard.
        Scoped strictly to company, return period, and registration.
        Uses exact Decimal arithmetic.
        """
        vouchers = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE'],
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).prefetch_related('items', 'gstr2b_matches').defer('attachment_data', 'attachment_mime')

        if return_period and return_period != 'ALL':
            try:
                p_info = GSTPeriodService.parse_return_period(return_period)
                vouchers = vouchers.filter(voucher_date__year=p_info.year_int, voucher_date__month=p_info.month_int)
            except Exception:
                pass

        matched_vouchers_count = 0
        mismatched_vouchers_count = 0
        missing_in_2b_count = 0

        itc_safe = Decimal('0.00')
        itc_at_risk = Decimal('0.00')
        itc_held_total = Decimal('0.00')

        for v in vouchers:
            v_tax = sum(quantize_amount(i.cgst_amount + i.sgst_amount + i.igst_amount + getattr(i, 'cess_amount', 0)) for i in v.items.all())
            itc_held_total += quantize_amount(v.itc_held_amount or 0)

            matched_rec = v.gstr2b_matches.first()
            eff_status = v.itc_match_status or 'UNCHECKED'
            if eff_status == 'UNCHECKED':
                eff_status = 'MATCHED' if matched_rec else 'MISSING_IN_2B'

            if eff_status == 'MATCHED':
                matched_vouchers_count += 1
                itc_safe += v_tax
            elif eff_status == 'MISMATCHED':
                mismatched_vouchers_count += 1
                itc_at_risk += v_tax
            elif eff_status == 'MISSING_IN_2B':
                missing_in_2b_count += 1
                itc_at_risk += v_tax

        # 2B records missing in books
        rec_qs = GSTR2BRecord.objects.filter(company=company)
        if return_period and return_period != 'ALL':
            try:
                p_info = GSTPeriodService.parse_return_period(return_period)
                rec_qs = rec_qs.filter(return_period=p_info.normalized_period)
            except Exception:
                pass
        if registration:
            rec_qs = rec_qs.filter(Q(gst_registration=registration) | Q(gst_registration__isnull=True))

        missing_in_books_count = rec_qs.filter(match_status='MISSING_IN_BOOKS').count()
        missing_in_books_itc = sum(
            quantize_amount(r.cgst_amount + r.sgst_amount + r.igst_amount + r.cess_amount)
            for r in rec_qs.filter(match_status='MISSING_IN_BOOKS')
        )

        return {
            'itc_at_risk': float(itc_at_risk),
            'itc_safe': float(itc_safe),
            'itc_held_total': float(itc_held_total),
            'matched_count': matched_vouchers_count,
            'mismatched_count': mismatched_vouchers_count,
            'missing_in_2b_count': missing_in_2b_count,
            'missing_in_books_count': missing_in_books_count,
            'missing_in_books_itc': float(missing_in_books_itc),
            'return_period': return_period or 'ALL'
        }

    @classmethod
    def get_sec16_4_expiry_radar(cls, company: Company, registration: Optional[Any] = None) -> Dict[str, Any]:
        """
        Section 16(4) Radar: Invoices of FY (T-1) must be claimed by 30th November of FY (T).
        Detects un-reconciled purchase invoices that are approaching this hard legal deadline.
        """
        today = timezone.now().date()
        current_fy_start_year = today.year if today.month >= 4 else today.year - 1
        deadline = date(current_fy_start_year, 11, 30)

        days_remaining = (deadline - today).days

        prev_fy_start = date(current_fy_start_year - 1, 4, 1)
        prev_fy_end = date(current_fy_start_year, 3, 31)

        expiring_vouchers = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE'],
            voucher_date__gte=prev_fy_start,
            voucher_date__lte=prev_fy_end,
            itc_match_status__in=['MISSING_IN_2B', 'MISMATCHED', 'UNCHECKED'],
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).select_related('party_ledger').prefetch_related('items').defer('attachment_data', 'attachment_mime')

        expiring_list = []
        total_expiring_itc = Decimal('0.00')

        for v in expiring_vouchers:
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
