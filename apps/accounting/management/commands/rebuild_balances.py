from django.core.management.base import BaseCommand
from apps.companies.models import Company
from apps.accounting.services.balance_rebuild import BalanceRebuildService

class Command(BaseCommand):
    help = 'Idempotent, transaction-safe rebuild of all ledger current_balance fields from authoritative ledger entries.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company_id',
            type=str,
            help='Specify a company ID to rebuild balances only for that company',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Rebuild balances for all companies',
        )

    def handle(self, *args, **options):
        company_id = options.get('company_id')
        rebuild_all = options.get('all')

        if not company_id and not rebuild_all:
            self.stderr.write(self.style.ERROR("Must specify either --company_id <id> or --all"))
            return

        if company_id:
            try:
                companies = [Company.objects.get(id=company_id)]
            except Company.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Company {company_id} does not exist."))
                return
        else:
            companies = Company.objects.all()

        total_rebuilt = 0
        self.stdout.write(f"Starting rebuild for {len(companies)} companies...")

        for company in companies:
            self.stdout.write(f"  Rebuilding {company.name} ({company.id})...")
            try:
                res = BalanceRebuildService.rebuild_company_ledger_balances(company)
                rebuilt_count = res.get('rebuilt_ledgers_count', 0)
                total_rebuilt += rebuilt_count
                self.stdout.write(self.style.SUCCESS(f"    Success: rebuilt {rebuilt_count} ledgers."))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"    Failed for {company.name}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f"\nCompleted! Total ledgers rebuilt: {total_rebuilt}"))
