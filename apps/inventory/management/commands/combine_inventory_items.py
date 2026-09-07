from django.core.management.base import BaseCommand
from apps.inventory.services.normalization_service import combine_and_deduplicate_inventory


class Command(BaseCommand):
    help = (
        "Combines duplicate items in inventory (e.g. B92 and B-92, A 31 and A-31), "
        "normalizes all belt names without hyphens and with a single space (e.g. A 32, B 92), "
        "sums stock quantities, re-links all vouchers, and sets invoice tags."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--company',
            type=str,
            default=None,
            help='Company name substring to target (e.g. "Maa Annapurna Belting Store"). Defaults to Maa Annapurna / All.'
        )
        parser.add_argument(
            '--company-id',
            type=str,
            default=None,
            help='Specific Company UUID to target.'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate combining items without modifying the database.'
        )

    def handle(self, *args, **options):
        company_name = options['company']
        company_id = options['company_id']
        dry_run = options['dry_run']

        mode_str = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(self.style.NOTICE(f"{mode_str}Starting inventory deduplication & normalization..."))

        report = combine_and_deduplicate_inventory(
            company_id=company_id,
            company_name=company_name,
            dry_run=dry_run
        )

        for comp in report['companies_processed']:
            self.stdout.write(self.style.SUCCESS(f"\nCompany: {comp['company_name']} ({comp['company_id']})"))
            self.stdout.write(f"  - Duplicate groups merged: {comp['merged_groups']}")
            self.stdout.write(f"  - Duplicate records removed: {comp['deleted_duplicates']}")
            self.stdout.write(f"  - Single items renamed to clean format: {comp['renamed_items']}")
            self.stdout.write(f"  - Invoice tags applied: {comp['invoice_tags_set']}")
            if comp['details']:
                self.stdout.write("  - Detailed Merges:")
                for d in comp['details'][:20]:
                    self.stdout.write(f"     * {d}")
                if len(comp['details']) > 20:
                    self.stdout.write(f"     * ... and {len(comp['details']) - 20} more groups.")

        self.stdout.write(self.style.SUCCESS(
            f"\n{mode_str}Complete! Merged {report['total_merged_groups']} duplicate groups, "
            f"deleted {report['total_deleted_duplicates']} redundant rows, "
            f"normalized {report['total_renamed_items']} item names, "
            f"applied {report['total_invoice_tags_set']} invoice tags."
        ))
