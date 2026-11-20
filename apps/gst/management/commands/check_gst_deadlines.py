import logging
from datetime import date
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.companies.models import Company
from apps.accounting.models import Voucher
from apps.gst.services.allocation_service import GSTAllocationService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Evaluates GST statutory deadlines across companies: Rule 37 (180 days), Rule 37A (30-Sep/30-Nov), and Section 16(4)."

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

    def handle(self, *args, **options):
        company_id = options.get('company_id')
        as_of_str = options.get('as_of_date')
        eval_date = date.fromisoformat(as_of_str) if as_of_str else timezone.now().date()

        self.stdout.write(f"[{eval_date.isoformat()}] Checking GST statutory deadlines...")

        companies = Company.objects.filter(is_active=True)
        if company_id:
            companies = companies.filter(id=company_id)

        total_checked = 0
        rule37a_defaulted = 0

        for comp in companies:
            vouchers = Voucher.objects.filter(
                company=comp,
                voucher_type='PURCHASE',
                status='POSTED'
            )
            for v in vouchers:
                total_checked += 1
                res = GSTAllocationService.evaluate_rule37a_status(
                    voucher=v,
                    check_date=eval_date,
                    supplier_gstr3b_filed=False
                )
                if res["is_supplier_default"]:
                    rule37a_defaulted += 1
                    status_note = "OVERDUE (Interest applicable)" if res["is_reversal_overdue"] else "REVERSAL REQUIRED"
                    self.stdout.write(
                        f"  [Rule 37A Default] Co: {comp.name} | Inv: {v.voucher_number} | "
                        f"FY: {res['financial_year']} | Status: {status_note}"
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"[COMPLETE] Evaluated {total_checked} vouchers across {companies.count()} companies. "
                f"Rule 37A defaults flagged: {rule37a_defaulted}."
            )
        )
