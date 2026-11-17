import re
import logging
from collections import defaultdict
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from django.db import transaction
from django.utils import timezone
from apps.companies.models import Company
from apps.accounting.models import Voucher, VoucherItem
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService
from apps.gst.models import GSTRegistration, GSTR2BImport, GSTR2BRecord
from apps.gst.services.sandbox_client import SandboxGSTClient

logger = logging.getLogger('apps.gst.reconciliation_service')


def quantize_amount(val: Any) -> Decimal:
    try:
        return Decimal(str(val or '0.00')).quantize(Decimal('0.01'))
    except Exception:
        return Decimal('0.00')


class GSTReconciliationService:
    """
    Comprehensive 11-Category GSTR-2B vs Purchase Register Reconciliation Engine.
    INVARIANT: ZERO alteration of purchase vouchers or accounting ledger balances.
    """

    TOLERANCE = Decimal('1.00')

    @classmethod
    def normalize_invoice_number(cls, num_str: str) -> str:
        """
        Normalizes invoice number by stripping non-alphanumeric characters,
        removing leading zeros and standard prefixes for comparison.
        """
        if not num_str:
            return ""
        cleaned = re.sub(r'[^A-Z0-9]', '', str(num_str).strip().upper())
        if cleaned.startswith('INV') and len(cleaned) > 3:
            cleaned = cleaned[3:]
        return cleaned.lstrip('0') or cleaned

    @classmethod
    def fetch_and_ingest_from_sandbox(
        cls,
        company: Company,
        registration: Optional[GSTRegistration],
        return_period: str,
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Fetches GSTR-2B statement directly from Sandbox by Quicko:
        GET /gst/compliance/tax-payer/gstrs/gstr-2b/{year}/{month}
        And ingests the records into GSTR2BImport and GSTR2BRecord.
        """
        # Parse return_period (e.g. "082026") into year and month
        p = return_period.strip().replace('-', '')
        if len(p) == 6:
            month = p[:2]
            year = p[2:]
        else:
            now = timezone.now()
            month = str(now.month).zfill(2)
            year = str(now.year)

        client = SandboxGSTClient(company=company, registration=registration)
        session_token = registration.auth_token if registration else None

        if not client.is_configured():
            return {
                "success": False,
                "error": "Sandbox GST API is not configured. Please supply API credentials in settings or company configuration."
            }

        res = client.fetch_gstr2b(year=year, month=month, session_token=session_token, user=user)
        if not res.get("success"):
            return res

        data = res.get("data") or {}
        # Ingest the JSON payload into GSTR2BImport
        from apps.gst.services.itc_reconciliation_service import ITCReconciliationService
        import_batch = ITCReconciliationService.ingest_gstr2b_json(
            company=company,
            json_data=data,
            user=user,
            file_name=f"sandbox_gstr2b_{return_period}.json",
            return_period=return_period
        )

        if registration:
            import_batch.gst_registration = registration
            import_batch.save(update_fields=['gst_registration'])
            import_batch.records.update(gst_registration=registration)

        # Execute reconciliation
        rec_summary = cls.reconcile_period(
            company=company,
            registration=registration,
            return_period=return_period
        )

        return {
            "success": True,
            "import_batch_id": str(import_batch.id),
            "return_period": return_period,
            "total_invoices_ingested": import_batch.total_invoices_count,
            "reconciliation_summary": rec_summary
        }

    @classmethod
    @transaction.atomic
    def reconcile_period(
        cls,
        company: Company,
        registration: Optional[GSTRegistration] = None,
        return_period: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Runs comprehensive 11-category discrepancy analysis between:
        1. Buyer's Purchase Register vouchers
        2. GSTR-2B Ingested Records
        """
        # 1. Fetch Purchase Vouchers
        voucher_qs = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE'],
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).select_related('party_ledger').prefetch_related('items').order_by('voucher_date', 'voucher_number')

        vouchers = list(voucher_qs)

        # 2. Fetch GSTR-2B Records
        rec_qs = GSTR2BRecord.objects.filter(company=company)
        if return_period:
            rec_qs = rec_qs.filter(import_batch__return_period=return_period)
        if registration:
            from django.db.models import Q
            rec_qs = rec_qs.filter(Q(gst_registration=registration) | Q(gst_registration__isnull=True))

        gstr2b_records = list(rec_qs.select_related('import_batch'))

        # Build lookup indices for GSTR-2B
        records_by_exact_key = {}  # (gstin, norm_num) -> record
        records_by_num_only = defaultdict(list)  # norm_num -> [records]
        records_by_supplier = defaultdict(list)  # gstin -> [records]

        for r in gstr2b_records:
            gstin = r.supplier_gstin.upper()
            norm = r.normalized_invoice_number
            records_by_exact_key[(gstin, norm)] = r
            records_by_num_only[norm].append(r)
            records_by_supplier[gstin].append(r)

        matched_record_ids = set()
        matched_voucher_ids = set()

        # Category Counts
        category_counts = {
            "MATCHED": 0,
            "PARTIAL_MATCH": 0,
            "MISSING_IN_BOOKS": 0,
            "MISSING_IN_2B": 0,
            "TAX_MISMATCH": 0,
            "GSTIN_MISMATCH": 0,
            "DOC_NUM_MISMATCH": 0,
            "DATE_MISMATCH": 0,
            "DUPLICATE": 0,
            "INELIGIBLE_ITC": 0,
            "MISMATCHED": 0
        }

        records_to_update = []

        # Step A: Evaluate Each GSTR-2B Record Against Purchase Books
        for rec in gstr2b_records:
            # Check Ineligible ITC first
            if not rec.itc_available:
                rec.match_status = 'INELIGIBLE_ITC'
                rec.mismatch_details = {
                    "reason": rec.itc_ineligible_reason or "Vendor marked as ITC Ineligible in GSTR-2B / Section 17(5)."
                }
                category_counts["INELIGIBLE_ITC"] += 1
                records_to_update.append(rec)
                continue

            # Candidate match search
            best_voucher = None
            best_match_category = 'MISSING_IN_BOOKS'
            mismatch_explanation = "Invoice appears in GSTR-2B but no corresponding purchase voucher was found in books."

            r_gstin = rec.supplier_gstin.upper()
            r_norm = rec.normalized_invoice_number
            r_date = rec.invoice_date
            r_txval = quantize_amount(rec.taxable_value)
            r_igst = quantize_amount(rec.igst_amount)
            r_cgst = quantize_amount(rec.cgst_amount)
            r_sgst = quantize_amount(rec.sgst_amount)
            r_tax = r_igst + r_cgst + r_sgst
            r_total = quantize_amount(rec.invoice_value)

            # Try exact match on (supplier_gstin, normalized_invoice_number)
            for v in vouchers:
                if v.id in matched_voucher_ids:
                    continue

                v_gstin = (v.party_ledger.gstin if v.party_ledger and v.party_ledger.gstin else (v.buyer_gstin or '')).strip().upper()
                v_bill_no = (v.external_invoice_number or v.reference_number or v.voucher_number or '').strip()
                v_norm = cls.normalize_invoice_number(v_bill_no)

                v_items = list(v.items.all())
                v_txval = sum(quantize_amount(itm.taxable_amount) for itm in v_items)
                v_igst = sum(quantize_amount(itm.igst_amount) for itm in v_items)
                v_cgst = sum(quantize_amount(itm.cgst_amount) for itm in v_items)
                v_sgst = sum(quantize_amount(itm.sgst_amount) for itm in v_items)
                v_tax = v_igst + v_cgst + v_sgst
                v_total = quantize_amount(v.total_amount)

                # 1. Exact Key Match
                if v_norm == r_norm and v_gstin == r_gstin:
                    best_voucher = v
                    diff_val = abs(v_total - r_total)
                    diff_txval = abs(v_txval - r_txval)
                    diff_tax = abs(v_tax - r_tax)
                    diff_days = abs((v.voucher_date - r_date).days) if v.voucher_date and r_date else 0

                    diff_breakdown = abs(v_igst - r_igst) > cls.TOLERANCE or abs(v_cgst - r_cgst) > cls.TOLERANCE or abs(v_sgst - r_sgst) > cls.TOLERANCE
                    if diff_breakdown:
                        best_match_category = 'TAX_MISMATCH'
                        mismatch_explanation = f"Tax breakdown mismatch: Books has IGST={v_igst}, CGST/SGST={v_cgst}; 2B has IGST={r_igst}, CGST/SGST={r_cgst}."
                    elif diff_val <= cls.TOLERANCE and diff_txval <= cls.TOLERANCE and diff_tax <= cls.TOLERANCE and diff_days <= 3:
                        best_match_category = 'MATCHED'
                        mismatch_explanation = "Exact match on GSTIN, invoice number, amounts, and date."
                    elif diff_days > 30:
                        best_match_category = 'DATE_MISMATCH'
                        mismatch_explanation = f"Invoice date discrepancy: Books={v.voucher_date}, 2B={r_date} ({diff_days} days difference)."
                    elif diff_txval > cls.TOLERANCE or diff_tax > cls.TOLERANCE:
                        best_match_category = 'PARTIAL_MATCH'
                        mismatch_explanation = f"Value mismatch: Taxable diff=₹{diff_txval}, Tax diff=₹{diff_tax}."
                    else:
                        best_match_category = 'MISMATCHED'
                        mismatch_explanation = f"General discrepancy: Total diff=₹{diff_val}."
                    break

                # 2. Number match but GSTIN differs
                elif v_norm == r_norm and abs(v_total - r_total) <= cls.TOLERANCE:
                    best_voucher = v
                    best_match_category = 'GSTIN_MISMATCH'
                    mismatch_explanation = f"Invoice number '{v_bill_no}' matches, but supplier GSTIN differs: Books={v_gstin}, 2B={r_gstin}."
                    break

                # 3. Fuzzy Number Match (formatting variation)
                elif v_gstin == r_gstin and abs(v_total - r_total) <= cls.TOLERANCE:
                    clean_v_num = re.sub(r'\D', '', v_bill_no)
                    clean_r_num = re.sub(r'\D', '', rec.invoice_number)
                    if clean_v_num and clean_r_num and (clean_v_num.endswith(clean_r_num) or clean_r_num.endswith(clean_v_num)):
                        best_voucher = v
                        best_match_category = 'DOC_NUM_MISMATCH'
                        mismatch_explanation = f"Formatting variation in invoice number: Books='{v_bill_no}', 2B='{rec.invoice_number}'."
                        break

            # Update GSTR-2B Record
            rec.match_status = best_match_category
            rec.matched_voucher = best_voucher
            rec.mismatch_details = {
                "category": best_match_category,
                "explanation": mismatch_explanation,
                "book_voucher_number": best_voucher.voucher_number if best_voucher else None,
                "book_date": str(best_voucher.voucher_date) if best_voucher else None,
                "book_total": float(best_voucher.total_amount) if best_voucher else None,
                "gstr2b_total": float(r_total),
            }

            if best_voucher:
                matched_voucher_ids.add(best_voucher.id)
                matched_record_ids.add(rec.id)

            category_counts[best_match_category] += 1
            records_to_update.append(rec)

        GSTR2BRecord.objects.bulk_update(records_to_update, ['match_status', 'matched_voucher', 'mismatch_details'], batch_size=500)

        # Step B: Identify Purchase Vouchers Missing in GSTR-2B
        unmatched_purchase_vouchers = [v for v in vouchers if v.id not in matched_voucher_ids]
        category_counts["MISSING_IN_2B"] = len(unmatched_purchase_vouchers)

        # Totals calculation
        total_2b_records = len(gstr2b_records)
        total_2b_itc = sum(quantize_amount(r.igst_amount + r.cgst_amount + r.sgst_amount) for r in gstr2b_records if r.itc_available)
        matched_itc = sum(
            quantize_amount(r.igst_amount + r.cgst_amount + r.sgst_amount)
            for r in gstr2b_records
            if r.match_status == 'MATCHED' and r.itc_available
        )
        at_risk_itc = total_2b_itc - matched_itc

        return {
            "period": return_period or "ALL",
            "total_gstr2b_records": total_2b_records,
            "total_purchase_vouchers": len(vouchers),
            "matched_count": category_counts["MATCHED"],
            "category_breakdown": category_counts,
            "financial_metrics": {
                "total_gstr2b_itc": float(total_2b_itc),
                "matched_itc": float(matched_itc),
                "at_risk_itc": float(at_risk_itc),
                "reconciliation_percentage": float((matched_itc / total_2b_itc * 100).quantize(Decimal('0.1'))) if total_2b_itc > 0 else 100.0
            }
        }
