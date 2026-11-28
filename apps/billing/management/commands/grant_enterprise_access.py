import sys
from django.core.management.base import BaseCommand, CommandError
from apps.companies.models import Company
from apps.billing.services.entitlement_service import EntitlementService


class Command(BaseCommand):
    help = "Grants or upgrades a company workspace to full Enterprise tier access with high operational quotas."

    def add_arguments(self, parser):
        parser.add_argument(
            '--company-id',
            type=str,
            default='5d2e5dea-ff86-4871-b2af-fe1c5a05c03c',
            help='Company UUID (default: 5d2e5dea-ff86-4871-b2af-fe1c5a05c03c for Maa Annapurna Belting Store)',
        )
        parser.add_argument(
            '--company-name',
            type=str,
            default='',
            help='Lookup company by name substring if ID not provided',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=3650,
            help='Number of days the enterprise subscription remains valid (default: 3650 / 10 years)',
        )
        parser.add_argument(
            '--fast-ocr-daily',
            type=int,
            default=1000,
            help='Daily Fast OCR quota (default: 1000 scans/day)',
        )
        parser.add_argument(
            '--deep-ocr-daily',
            type=int,
            default=200,
            help='Daily Deep OCR quota (default: 200 scans/day)',
        )
        parser.add_argument(
            '--reset-usage',
            action='store_true',
            default=True,
            help='Immediately reset daily usage trackers to clear existing quota limits (default: True)',
        )

    def handle(self, *args, **options):
        company_id = options.get('company_id')
        company_name = options.get('company_name')
        days = options.get('days')
        fast_ocr = options.get('fast_ocr_daily')
        deep_ocr = options.get('deep_ocr_daily')

        company = None
        if company_id:
            try:
                company = Company.objects.filter(id=company_id).first()
            except Exception:
                pass

        if not company and company_name:
            company = Company.objects.filter(name__icontains=company_name).first()

        if not company:
            raise CommandError(f"Company could not be found with id={company_id} or name={company_name}")

        self.stdout.write(self.style.NOTICE(f"Provisioning Enterprise subscription for '{company.name}' ({company.id})..."))

        custom_limits = {
            "ocr_fast_daily": fast_ocr,
            "ocr_deep_daily": deep_ocr,
        }

        sub = EntitlementService.grant_enterprise_subscription(
            company_id=company.id,
            days=days,
            custom_limits=custom_limits,
            notes=f"Administrative grant for {company.name}"
        )

        entitlements = EntitlementService.get_company_entitlements(company.id)
        fast_usage = EntitlementService.get_daily_usage(company.id, "ocr_fast_scans")
        deep_usage = EntitlementService.get_daily_usage(company.id, "ocr_deep_scans")

        self.stdout.write(self.style.SUCCESS(
            f"SUCCESS: Company '{company.name}' upgraded to {entitlements['plan_name']} tier.\n"
            f"  Subscription ID: {sub.id}\n"
            f"  Status: {sub.status}\n"
            f"  Valid until: {sub.current_period_end}\n"
            f"  OCR Fast Daily Limit: {entitlements['limits'].get('ocr_fast_daily')} (current usage: {fast_usage})\n"
            f"  OCR Deep Daily Limit: {entitlements['limits'].get('ocr_deep_daily')} (current usage: {deep_usage})\n"
            f"  All BI & Platform Features: {all(entitlements['features'].values())}"
        ))
