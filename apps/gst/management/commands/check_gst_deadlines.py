import logging
import json
from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.companies.models import Company
from apps.accounting.models import Voucher
from apps.gst.models import GSTR2BRecord, GSTReportingAllocation
from apps.gst.services.allocation_service import GSTAllocationService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = (
        "Statutory GST Deadline Engine: Evaluates Rule 37 (180 days non-payment), "
        "Rule 37A (30-Sep supplier default / 30-Nov recipient reversal), and Section 16(4)/16(5)/16(6) time bars."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--company-id',
            type=str,
            default=None,
            help='Company UUID to evaluate (defaults to all active companies)'
        )
        parser.add_argument(
            '--as-of-date',
            type=str,
            default=None,
            help='Evaluation date in YYYY-MM-DD format (defaults to current date)'
        )
        parser.add_argument(
            '--json',
            action='store_true',
            dest='as_json',
            default=False,
            help='Output audit results as machine-readable JSON'
        )

    def handle(self, *args, **options):
        company_id = options.get('company_id')
        as_of_str = options.get('as_of_date')
        as_json = options.get('as_json')
        eval_date = date.fromisoformat(as_of_str) if as_of_str else timezone.now().date()

        if not as_json:
            self.stdout.write(f"[{eval_date.isoformat()}] Running SriLekh Statutory GST Deadline & Compliance Engine...")

        companies = Company.objects.filter(is_active=True)
        if company_id:
            companies = companies.filter(id=company_id)

        report = {
            "evaluation_date": eval_date.isoformat(),
            "companies_evaluated": companies.count(),
            "total_vouchers_checked": 0,
            "rule37": {
                "evaluated": 0,
                "reversal_required_count": 0,
                "total_reversal_tax_required": 0.0,
                "overdue_count": 0,
                "total_est_interest": 0.0,
                "findings": []
            },
            "rule37a": {
                "evaluated": 0,
                "verified_filed_count": 0,
                "verified_default_count": 0,
                "data_unavailable_count": 0,
                "overdue_count": 0,
                "total_est_interest": 0.0,
                "findings": []
            },
            "section16": {
                "evaluated": 0,
                "statute_barred_count": 0,
                "findings": []
            }
        }

        for comp in companies:
            vouchers = Voucher.objects.filter(
                company=comp,
                voucher_type='PURCHASE',
                status='POSTED'
            ).order_by('voucher_date')

            for v in vouchers:
                report["total_vouchers_checked"] += 1

                # 1. Evaluate Rule 37 (180-Day Payment Condition)
                report["rule37"]["evaluated"] += 1
                r37_res = GSTAllocationService.evaluate_rule37_status(voucher=v, check_date=eval_date)
                if r37_res["reversal_required"] or r37_res["is_payment_overdue"]:
                    if r37_res["reversal_required"]:
                        report["rule37"]["reversal_required_count"] += 1
                        report["rule37"]["total_reversal_tax_required"] += float(r37_res["required_reversal_tax"])
                    if r37_res["is_payment_overdue"]:
                        report["rule37"]["overdue_count"] += 1
                    
                    interest_amt = float(r37_res["interest_details"]["interest_amount"]) if r37_res["interest_applicable"] else 0.0
                    report["rule37"]["total_est_interest"] += interest_amt

                    finding_37 = {
                        "company_name": comp.name,
                        "voucher_number": v.voucher_number,
                        "voucher_date": v.voucher_date.isoformat(),
                        "payment_deadline": r37_res["payment_deadline"].isoformat(),
                        "unpaid_amount": float(r37_res["unpaid_amount"]),
                        "required_reversal_tax": float(r37_res["required_reversal_tax"]),
                        "is_overdue": r37_res["is_payment_overdue"],
                        "est_interest_sec_50": interest_amt
                    }
                    report["rule37"]["findings"].append(finding_37)
                    if not as_json and r37_res["reversal_required"]:
                        self.stdout.write(
                            f"  [Rule 37 Reversal Required] Co: {comp.name} | Inv: {v.voucher_number} | "
                            f"Unpaid: ₹{r37_res['unpaid_amount']} | Reversal Tax: ₹{r37_res['required_reversal_tax']} | "
                            f"Est. Interest: ₹{interest_amt:.2f}"
                        )

                # 2. Evaluate Rule 37A (Supplier GSTR-3B Default)
                report["rule37a"]["evaluated"] += 1
                
                # Resolve supplier status from GSTR-2B or records
                gstr2b_rec = GSTR2BRecord.objects.filter(
                    company=comp,
                    matched_voucher=v
                ).first()

                supplier_status = 'UNKNOWN'
                supplier_filing_date = None
                supplier_gstr3b_filed = False

                if gstr2b_rec:
                    if gstr2b_rec.gstr3b_status == 'FILED':
                        supplier_status = 'VERIFIED_FILED'
                        supplier_gstr3b_filed = True
                        supplier_filing_date = gstr2b_rec.gstr1_filing_date
                    elif gstr2b_rec.gstr3b_status in ('NOT_FILED', 'PENDING'):
                        supplier_status = 'VERIFIED_NOT_FILED'
                        supplier_gstr3b_filed = False
                    else:
                        supplier_status = 'DATA_UNAVAILABLE'
                else:
                    # Check manual confirmation or fallback
                    supplier_status = 'UNKNOWN'

                r37a_res = GSTAllocationService.evaluate_rule37a_status(
                    voucher=v,
                    check_date=eval_date,
                    supplier_gstr3b_filed=supplier_gstr3b_filed,
                    supplier_filing_date=supplier_filing_date,
                    supplier_status=supplier_status
                )

                if r37a_res["supplier_status"] == 'VERIFIED_FILED':
                    report["rule37a"]["verified_filed_count"] += 1
                elif r37a_res["supplier_status"] == 'DATA_UNAVAILABLE' or r37a_res["supplier_status"] == 'UNKNOWN':
                    report["rule37a"]["data_unavailable_count"] += 1
                elif r37a_res["is_supplier_default"]:
                    report["rule37a"]["verified_default_count"] += 1
                    if r37a_res["is_reversal_overdue"]:
                        report["rule37a"]["overdue_count"] += 1
                    interest_amt = float(r37a_res["interest_details"]["interest_amount"]) if r37a_res["interest_applicable"] else 0.0
                    report["rule37a"]["total_est_interest"] += interest_amt

                    finding_37a = {
                        "company_name": comp.name,
                        "voucher_number": v.voucher_number,
                        "financial_year": r37a_res["financial_year"],
                        "supplier_status": r37a_res["supplier_status"],
                        "reversal_deadline": r37a_res["recipient_reversal_deadline"].isoformat(),
                        "is_overdue": r37a_res["is_reversal_overdue"],
                        "est_interest_sec_50": interest_amt
                    }
                    report["rule37a"]["findings"].append(finding_37a)
                    if not as_json:
                        status_str = "OVERDUE (Interest Applicable)" if r37a_res["is_reversal_overdue"] else "REVERSAL REQUIRED"
                        self.stdout.write(
                            f"  [Rule 37A Default] Co: {comp.name} | Inv: {v.voucher_number} | "
                            f"FY: {r37a_res['financial_year']} | Status: {status_str} | Est. Interest: ₹{interest_amt:.2f}"
                        )

                # 3. Evaluate Section 16(4) / 16(5) / 16(6) Statutory Time Bars
                report["section16"]["evaluated"] += 1
                cutoff_date = GSTAllocationService.get_statutory_cutoff_date(
                    v.voucher_date,
                    company=comp,
                    return_type='INWARD_ITC'
                )
                
                # Check if voucher has active eligible allocation
                alloc = GSTReportingAllocation.objects.filter(voucher=v, is_active=True).first()
                if (not alloc or not alloc.is_statutorily_eligible) and eval_date > cutoff_date:
                    report["section16"]["statute_barred_count"] += 1
                    finding_16 = {
                        "company_name": comp.name,
                        "voucher_number": v.voucher_number,
                        "voucher_date": v.voucher_date.isoformat(),
                        "statutory_cutoff": cutoff_date.isoformat(),
                        "status": "STATUTE_BARRED_SECTION_16_4"
                    }
                    report["section16"]["findings"].append(finding_16)
                    if not as_json:
                        self.stdout.write(
                            f"  [Section 16(4) Statute-Barred] Co: {comp.name} | Inv: {v.voucher_number} | "
                            f"Invoice Date: {v.voucher_date.isoformat()} | Cutoff: {cutoff_date.isoformat()}"
                        )

        if as_json:
            self.stdout.write(json.dumps(report, indent=2))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n[COMPLETE] Evaluated {report['total_vouchers_checked']} vouchers across {report['companies_evaluated']} companies. "
                    f"Statutory Deadline Evaluation Complete:\n"
                    f"  Rule 37 (180 Days): {report['rule37']['reversal_required_count']} reversals required "
                    f"(Total Tax: ₹{report['rule37']['total_reversal_tax_required']:.2f}, Overdue: {report['rule37']['overdue_count']}, Interest: ₹{report['rule37']['total_est_interest']:.2f})\n"
                    f"  Rule 37A (Supplier Default): Verified Defaults: {report['rule37a']['verified_default_count']} "
                    f"(Overdue: {report['rule37a']['overdue_count']}, Interest: ₹{report['rule37a']['total_est_interest']:.2f}, Data Pending: {report['rule37a']['data_unavailable_count']})\n"
                    f"  Section 16(4)/16(5)/16(6): Statute-Barred ITC: {report['section16']['statute_barred_count']}"
                )
            )
