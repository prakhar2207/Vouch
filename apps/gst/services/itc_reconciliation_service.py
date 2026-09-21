import re
import json
import logging
from decimal import Decimal
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.utils import timezone

from apps.companies.models import Company
from apps.accounting.models import Voucher, VoucherItem
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService
from apps.gst.models import GSTR2BImport, GSTR2BRecord

logger = logging.getLogger(__name__)


class ITCReconciliationService:
    """
    Vendor ITC Risk Shield - Ingestion and Reconciliation Engine.
    Parses GSTR-2B JSON & Excel files, normalizes invoice numbers,
    and performs 4-way delta reconciliation against purchase vouchers.
    """

    @staticmethod
    def normalize_invoice_number(inum: str) -> str:
        """
        Normalizes an invoice number for fuzzy matching across systems.
        E.g.: 'INV/2026-27/0081' -> '2026270081'
        Also strips non-alphanumerics and converts to upper case.
        """
        if not inum:
            return ""
        # Remove common separators: /, -, _, spaces, dots
        cleaned = re.sub(r'[\/\-_\s\.]', '', str(inum).strip().upper())
        # Remove leading 'INV' prefix if present
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
        return_period: Optional[str] = None
    ) -> GSTR2BImport:
        """
        Ingests official GSTR-2B JSON downloaded from the GST Portal.
        Parses B2B (Table 3), B2BA (Amendments), and CDNR (Credit/Debit notes).
        """
        if isinstance(json_data, (str, bytes)):
            json_data = json.loads(json_data)

        # Detect return period (e.g. '082026')
        fp = return_period or json_data.get('fp') or json_data.get('data', {}).get('fp') or datetime.now().strftime('%m%Y')
        
        # Calculate financial year from period (e.g., '082026' -> '2026-27')
        fy = ''
        if len(fp) == 6:
            m = int(fp[:2])
            y = int(fp[2:])
            if m >= 4:
                fy = f"{y}-{str(y+1)[2:]}"
            else:
                fy = f"{y-1}-{str(y)[2:]}"

        import_batch = GSTR2BImport.objects.create(
            company=company,
            return_period=fp,
            financial_year=fy,
            file_format='JSON',
            file_name=file_name or f"gstr2b_{fp}.json",
            uploaded_by=user,
            status='PROCESSING'
        )

        records_to_create = []
        total_invoices = 0
        total_taxable = Decimal('0.00')
        total_itc = Decimal('0.00')

        # Navigate payload structures: root.b2b, root.data.b2b, or root.docdata.b2b
        data_root = json_data.get('data', json_data)
        b2b_list = data_root.get('b2b', [])
        b2ba_list = data_root.get('b2ba', [])
        cdnr_list = data_root.get('cdnr', [])

        all_supplier_entries = []
        for s in b2b_list:
            all_supplier_entries.append(('B2B', s))
        for s in b2ba_list:
            all_supplier_entries.append(('B2BA', s))

        for doc_type, supplier_entry in all_supplier_entries:
            ctin = str(supplier_entry.get('ctin', '')).strip().upper()
            trdnm = str(supplier_entry.get('trdnm') or supplier_entry.get('lgl_name') or '').strip()
            
            invoices = supplier_entry.get('inv', [])
            for inv in invoices:
                inum = str(inv.get('inum', '')).strip()
                if not inum:
                    continue
                
                dt = cls.parse_date(inv.get('dt')) or timezone.now().date()
                val = Decimal(str(inv.get('val', '0') or '0'))
                pos = str(inv.get('pos', '')).strip()
                rev = str(inv.get('rev', 'N')).strip().upper()
                itcavl = str(inv.get('itcavl', 'Y')).strip().upper() == 'Y'
                rsn = str(inv.get('rsn', '')).strip()
                inv_typ = str(inv.get('inv_typ', 'R')).strip()

                # Sum up line items
                items = inv.get('items', [])
                inv_txval = Decimal('0.00')
                inv_iamt = Decimal('0.00')
                inv_camt = Decimal('0.00')
                inv_samt = Decimal('0.00')
                inv_csamt = Decimal('0.00')

                for itm in items:
                    # Item can be nested inside 'itmdet' or flat
                    det = itm.get('itmdet', itm)
                    inv_txval += Decimal(str(det.get('txval', '0') or '0'))
                    inv_iamt += Decimal(str(det.get('iamt', '0') or '0'))
                    inv_camt += Decimal(str(det.get('camt', '0') or '0'))
                    inv_samt += Decimal(str(det.get('samt', '0') or '0'))
                    inv_csamt += Decimal(str(det.get('csamt', '0') or '0'))

                # Fallback if no item details but total val provided
                if inv_txval == 0 and val > 0:
                    inv_txval = val

                rec_itc = (inv_iamt + inv_camt + inv_samt + inv_csamt) if itcavl else Decimal('0.00')

                record = GSTR2BRecord(
                    import_batch=import_batch,
                    company=company,
                    supplier_gstin=ctin,
                    supplier_name=trdnm,
                    invoice_number=inum,
                    normalized_invoice_number=cls.normalize_invoice_number(inum),
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
                records_to_create.append(record)

                total_invoices += 1
                total_taxable += inv_txval
                total_itc += rec_itc

        # Also parse CDNR (Credit/Debit notes)
        for s in cdnr_list:
            ctin = str(s.get('ctin', '')).strip().upper()
            trdnm = str(s.get('trdnm') or s.get('lgl_name') or '').strip()
            notes = s.get('nt', [])
            for nt in notes:
                nt_num = str(nt.get('nt_num', '')).strip()
                if not nt_num:
                    continue
                dt = cls.parse_date(nt.get('nt_dt')) or timezone.now().date()
                val = Decimal(str(nt.get('val', '0') or '0'))
                nt_typ = str(nt.get('ntty', 'C')).strip()  # C = Credit, D = Debit
                itcavl = str(nt.get('itcavl', 'Y')).strip().upper() == 'Y'

                items = nt.get('items', [])
                nt_txval = Decimal('0.00')
                nt_iamt = Decimal('0.00')
                nt_camt = Decimal('0.00')
                nt_samt = Decimal('0.00')
                nt_csamt = Decimal('0.00')

                for itm in items:
                    det = itm.get('itmdet', itm)
                    nt_txval += Decimal(str(det.get('txval', '0') or '0'))
                    nt_iamt += Decimal(str(det.get('iamt', '0') or '0'))
                    nt_camt += Decimal(str(det.get('camt', '0') or '0'))
                    nt_samt += Decimal(str(det.get('samt', '0') or '0'))
                    nt_csamt += Decimal(str(det.get('csamt', '0') or '0'))

                rec_itc = (nt_iamt + nt_camt + nt_samt + nt_csamt) if itcavl else Decimal('0.00')

                record = GSTR2BRecord(
                    import_batch=import_batch,
                    company=company,
                    supplier_gstin=ctin,
                    supplier_name=trdnm,
                    invoice_number=nt_num,
                    normalized_invoice_number=cls.normalize_invoice_number(nt_num),
                    invoice_type=f"CDNR_{nt_typ}",
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
                records_to_create.append(record)
                total_invoices += 1
                total_taxable += nt_txval
                total_itc += rec_itc

        # Bulk create records
        GSTR2BRecord.objects.bulk_create(records_to_create, batch_size=500)

        import_batch.total_invoices_count = total_invoices
        import_batch.total_taxable_amount = total_taxable
        import_batch.total_itc_available = total_itc
        import_batch.status = 'PROCESSED'
        import_batch.save(update_fields=['total_invoices_count', 'total_taxable_amount', 'total_itc_available', 'status'])

        # Automatically execute reconciliation for the period
        cls.reconcile_period(company, return_period=fp)

        return import_batch

    @classmethod
    def ingest_gstr2b_excel(
        cls,
        company: Company,
        file_obj,
        user=None,
        file_name: str = '',
        return_period: Optional[str] = None
    ) -> GSTR2BImport:
        """
        Ingests GSTR-2B standard Excel workbook downloaded from the GST Portal.
        Parses sheets such as 'B2B', 'B2BA', 'CDNR'.
        """
        import openpyxl

        wb = openpyxl.load_workbook(file_obj, data_only=True)
        fp = return_period or datetime.now().strftime('%m%Y')
        fy = ''
        if len(fp) == 6:
            m = int(fp[:2])
            y = int(fp[2:])
            fy = f"{y}-{str(y+1)[2:]}" if m >= 4 else f"{y-1}-{str(y)[2:]}"

        import_batch = GSTR2BImport.objects.create(
            company=company,
            return_period=fp,
            financial_year=fy,
            file_format='EXCEL',
            file_name=file_name or f"gstr2b_{fp}.xlsx",
            uploaded_by=user,
            status='PROCESSING'
        )

        records_to_create = []
        total_invoices = 0
        total_taxable = Decimal('0.00')
        total_itc = Decimal('0.00')

        # Check standard sheets
        target_sheets = [s for s in wb.sheetnames if s.strip().upper() in ['B2B', 'B2BA', 'CDNR']]
        if not target_sheets:
            # Fall back to active sheet if standard names not found
            target_sheets = [wb.active.title]

        for sheet_name in target_sheets:
            ws = wb[sheet_name]
            header_row_idx = None
            headers = {}

            # Locate header row (search first 10 rows for 'GSTIN' or 'Invoice Number')
            for r in range(1, min(15, ws.max_row + 1)):
                row_vals = [str(ws.cell(row=r, column=c).value or '').strip().lower() for c in range(1, ws.max_column + 1)]
                if any('gstin' in v for v in row_vals) and any('invoice' in v or 'inv' in v or 'number' in v for v in row_vals):
                    header_row_idx = r
                    for c_idx, val in enumerate(row_vals, start=1):
                        headers[val] = c_idx
                    break

            if not header_row_idx:
                continue

            def get_col(candidates):
                for cand in candidates:
                    for h_text, c_num in headers.items():
                        if cand in h_text:
                            return c_num
                return None

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

            for r in range(header_row_idx + 1, ws.max_row + 1):
                raw_gstin = ws.cell(row=r, column=c_gstin).value if c_gstin else ''
                if not raw_gstin:
                    continue
                gstin = str(raw_gstin).strip().upper()
                if len(gstin) < 10:
                    continue

                inum = str(ws.cell(row=r, column=c_inum).value or '').strip() if c_inum else ''
                if not inum:
                    continue

                name = str(ws.cell(row=r, column=c_name).value or '').strip() if c_name else ''
                raw_dt = ws.cell(row=r, column=c_date).value if c_date else None
                dt = cls.parse_date(raw_dt) or timezone.now().date()

                val = Decimal(str(ws.cell(row=r, column=c_val).value or '0').replace(',', '').strip() or '0') if c_val else Decimal('0.00')
                txval = Decimal(str(ws.cell(row=r, column=c_txval).value or '0').replace(',', '').strip() or '0') if c_txval else Decimal('0.00')
                iamt = Decimal(str(ws.cell(row=r, column=c_iamt).value or '0').replace(',', '').strip() or '0') if c_iamt else Decimal('0.00')
                camt = Decimal(str(ws.cell(row=r, column=c_camt).value or '0').replace(',', '').strip() or '0') if c_camt else Decimal('0.00')
                samt = Decimal(str(ws.cell(row=r, column=c_samt).value or '0').replace(',', '').strip() or '0') if c_samt else Decimal('0.00')
                csamt = Decimal(str(ws.cell(row=r, column=c_csamt).value or '0').replace(',', '').strip() or '0') if c_csamt else Decimal('0.00')

                pos = str(ws.cell(row=r, column=c_pos).value or '').strip() if c_pos else ''
                rev = str(ws.cell(row=r, column=c_rev).value or 'N').strip().upper() if c_rev else 'N'
                itc_val = str(ws.cell(row=r, column=c_itc).value or 'Y').strip().upper() if c_itc else 'Y'
                itcavl = itc_val in ['Y', 'YES', 'AVAILABLE', 'TRUE']

                if txval == 0 and val > 0:
                    txval = val

                rec_itc = (iamt + camt + samt + csamt) if itcavl else Decimal('0.00')

                record = GSTR2BRecord(
                    import_batch=import_batch,
                    company=company,
                    supplier_gstin=gstin,
                    supplier_name=name,
                    invoice_number=inum,
                    normalized_invoice_number=cls.normalize_invoice_number(inum),
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
                records_to_create.append(record)
                total_invoices += 1
                total_taxable += txval
                total_itc += rec_itc

        GSTR2BRecord.objects.bulk_create(records_to_create, batch_size=500)

        import_batch.total_invoices_count = total_invoices
        import_batch.total_taxable_amount = total_taxable
        import_batch.total_itc_available = total_itc
        import_batch.status = 'PROCESSED'
        import_batch.save(update_fields=['total_invoices_count', 'total_taxable_amount', 'total_itc_available', 'status'])

        cls.reconcile_period(company, return_period=fp)
        return import_batch

    @classmethod
    @transaction.atomic
    def reconcile_period(
        cls,
        company: Company,
        return_period: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Executes multi-way reconciliation between:
        1. Buyer's Purchase Vouchers in Vouch
        2. Ingested GSTR-2B Records
        """
        # Fetch purchase vouchers
        voucher_qs = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE'],
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).select_related('party_ledger').prefetch_related('items').defer('attachment_data', 'attachment_mime')

        if start_date:
            voucher_qs = voucher_qs.filter(voucher_date__gte=start_date)
        if end_date:
            voucher_qs = voucher_qs.filter(voucher_date__lte=end_date)

        vouchers = list(voucher_qs)

        # Fetch 2B records
        rec_qs = GSTR2BRecord.objects.filter(company=company)
        if return_period:
            rec_qs = rec_qs.filter(import_batch__return_period=return_period)

        gstr2b_records = list(rec_qs.select_related('import_batch'))

        # Index 2B records by (supplier_gstin, normalized_invoice_number)
        records_by_key = {}
        # Also index by supplier_gstin and invoice numeric suffix for fuzzy fallback
        records_by_supplier_suffix = {}

        for rec in gstr2b_records:
            gstin = rec.supplier_gstin.upper()
            norm_no = rec.normalized_invoice_number
            records_by_key[(gstin, norm_no)] = rec

            # Extract trailing numeric digits (e.g. '0081' -> '81')
            num_match = re.search(r'(\d+)$', norm_no)
            if num_match:
                suffix = num_match.group(1).lstrip('0') or '0'
                records_by_supplier_suffix.setdefault((gstin, suffix), []).append(rec)

        matched_record_ids = set()
        vouchers_to_update = []
        records_to_update = []

        for v in vouchers:
            # Determine supplier GSTIN
            supp_gstin = (v.party_ledger.gstin if v.party_ledger and v.party_ledger.gstin else (v.buyer_gstin or '')).strip().upper()
            # Reference or external invoice number entered by buyer for the purchase bill
            bill_num = (v.external_invoice_number or v.reference_number or v.voucher_number or '').strip()
            norm_bill_num = cls.normalize_invoice_number(bill_num)

            # Calculate book tax & taxable
            book_taxable = Decimal('0.00')
            book_cgst = Decimal('0.00')
            book_sgst = Decimal('0.00')
            book_igst = Decimal('0.00')

            for item in v.items.all():
                book_taxable += item.taxable_amount
                book_cgst += item.cgst_amount
                book_sgst += item.sgst_amount
                book_igst += item.igst_amount

            book_total_tax = book_cgst + book_sgst + book_igst

            # Attempt 1: Exact Key Match
            target_rec = records_by_key.get((supp_gstin, norm_bill_num))

            # Attempt 2: Trailing Numeric Suffix Match if not matched
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
                target_rec.matched_voucher = v

                # Comparison & Tolerance Check (₹2.00 threshold for rounding differences)
                rec_total_tax = target_rec.cgst_amount + target_rec.sgst_amount + target_rec.igst_amount
                taxable_diff = abs(book_taxable - target_rec.taxable_value)
                tax_diff = abs(book_total_tax - rec_total_tax)

                mismatches = []
                if taxable_diff > Decimal('2.00'):
                    mismatches.append(f"Taxable value mismatch: Books ₹{book_taxable:,.2f} vs 2B ₹{target_rec.taxable_value:,.2f} (Diff ₹{taxable_diff:,.2f})")
                if tax_diff > Decimal('2.00'):
                    mismatches.append(f"Tax amount mismatch: Books ₹{book_total_tax:,.2f} vs 2B ₹{rec_total_tax:,.2f} (Diff ₹{tax_diff:,.2f})")
                if (book_igst > 0 and target_rec.cgst_amount > 0) or (book_cgst > 0 and target_rec.igst_amount > 0):
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
                    v.itc_notes = 'Reconciled successfully with GSTR-2B.'
                    # Release any previously held amount if clean match
                    if v.itc_held_amount > 0 and not v.itc_notes.startswith('MANUAL_HOLD'):
                        v.itc_held_amount = Decimal('0.00')

                records_to_update.append(target_rec)
                vouchers_to_update.append(v)
            else:
                # Purchase voucher exists in Books, but NOT in GSTR-2B
                v.itc_match_status = 'MISSING_IN_2B'
                v.itc_notes = 'Invoice not found in uploaded GSTR-2B. Vendor has not filed GSTR-1.'
                # Suggest holding the entire GST amount for cash-flow protection
                if v.itc_held_amount == 0 and book_total_tax > 0:
                    v.itc_held_amount = book_total_tax
                vouchers_to_update.append(v)

        # Mark unmatched 2B records as MISSING_IN_BOOKS
        for rec in gstr2b_records:
            if rec.id not in matched_record_ids:
                if rec.match_status != 'MISSING_IN_BOOKS' or rec.matched_voucher is not None:
                    rec.match_status = 'MISSING_IN_BOOKS'
                    rec.matched_voucher = None
                    records_to_update.append(rec)

        # Bulk update
        if vouchers_to_update:
            Voucher.objects.bulk_update(vouchers_to_update, ['itc_match_status', 'itc_held_amount', 'itc_notes'], batch_size=200)

        if records_to_update:
            GSTR2BRecord.objects.bulk_update(records_to_update, ['match_status', 'matched_voucher', 'mismatch_details'], batch_size=200)

        return cls.get_summary_stats(company, return_period=return_period)

    @classmethod
    def get_summary_stats(cls, company: Company, return_period: Optional[str] = None) -> Dict[str, Any]:
        """
        Aggregates live compliance metrics for the ITC Risk Shield dashboard.
        """
        # Purchase vouchers
        vouchers = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE'],
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).prefetch_related('items')

        matched_vouchers_count = 0
        mismatched_vouchers_count = 0
        missing_in_2b_count = 0

        itc_safe = Decimal('0.00')
        itc_at_risk = Decimal('0.00')
        itc_held_total = Decimal('0.00')

        for v in vouchers:
            v_tax = sum((i.cgst_amount + i.sgst_amount + i.igst_amount) for i in v.items.all())
            itc_held_total += v.itc_held_amount

            if v.itc_match_status == 'MATCHED':
                matched_vouchers_count += 1
                itc_safe += v_tax
            elif v.itc_match_status == 'MISMATCHED':
                mismatched_vouchers_count += 1
                itc_at_risk += v_tax
            elif v.itc_match_status == 'MISSING_IN_2B':
                missing_in_2b_count += 1
                itc_at_risk += v_tax

        # 2B records missing in books
        rec_qs = GSTR2BRecord.objects.filter(company=company)
        if return_period:
            rec_qs = rec_qs.filter(import_batch__return_period=return_period)

        missing_in_books_count = rec_qs.filter(match_status='MISSING_IN_BOOKS').count()
        missing_in_books_itc = sum(
            (r.cgst_amount + r.sgst_amount + r.igst_amount)
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
    def get_sec16_4_expiry_radar(cls, company: Company) -> Dict[str, Any]:
        """
        Section 16(4) Radar: Invoices of FY (T-1) must be claimed by 30th November of FY (T).
        Detects un-reconciled purchase invoices that are approaching this hard legal deadline.
        """
        today = timezone.now().date()
        # Current FY start
        current_fy_start_year = today.year if today.month >= 4 else today.year - 1
        deadline = date(current_fy_start_year, 11, 30)

        days_remaining = (deadline - today).days

        # Preceding FY dates: 1st April (current_fy_start_year - 1) to 31st March (current_fy_start_year)
        prev_fy_start = date(current_fy_start_year - 1, 4, 1)
        prev_fy_end = date(current_fy_start_year, 3, 31)

        expiring_vouchers = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE'],
            voucher_date__gte=prev_fy_start,
            voucher_date__lte=prev_fy_end,
            itc_match_status__in=['MISSING_IN_2B', 'MISMATCHED', 'UNCHECKED'],
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).prefetch_related('items')

        expiring_list = []
        total_expiring_itc = Decimal('0.00')

        for v in expiring_vouchers:
            tax = sum((i.cgst_amount + i.sgst_amount + i.igst_amount) for i in v.items.all())
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
