from django.core.management.base import BaseCommand
from pathlib import Path
from apps.common.services.backup_service import DatabaseBackupService

class Command(BaseCommand):
    help = 'Restores a database snapshot from an encrypted/compressed backup archive.'

    def add_arguments(self, parser):
        parser.add_argument(
            'backup_file',
            type=str,
            help='Path to the backup file (.enc, .sql.gz, or .sql).'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate and count records in the backup archive without persisting changes.'
        )
        parser.add_argument(
            '--database',
            type=str,
            default='default',
            help='Target database alias to restore into (default: default).'
        )

    def handle(self, *args, **options):
        backup_file = options.get('backup_file')
        dry_run = options.get('dry_run', False)
        target_db = options.get('database', 'default')

        backup_path = Path(backup_file)
        if not backup_path.exists():
            self.stderr.write(self.style.ERROR(f"Backup file not found: {backup_path}"))
            return

        self.stdout.write(self.style.NOTICE(f"Initiating disaster recovery restore from: {backup_path.name}..."))
        if dry_run:
            self.stdout.write(self.style.WARNING("Running in DRY-RUN mode. No changes will be written to the database."))

        try:
            result = DatabaseBackupService.restore_backup(
                backup_path=backup_path,
                target_db_alias=target_db,
                dry_run=dry_run
            )

            if result.get('success'):
                self.stdout.write(self.style.SUCCESS(
                    f"Restore Succeeded!\n"
                    f"  Backup Type: {result.get('backup_type')}\n"
                    f"  Records Processed: {result.get('records_restored', 'N/A')}\n"
                    f"  Elapsed: {result.get('elapsed_seconds')}s\n"
                    f"  Dry Run: {result.get('dry_run')}"
                ))
            else:
                self.stderr.write(self.style.WARNING(
                    f"Restore completed with errors:\n"
                    f"  Errors: {result.get('error_count')}\n"
                    f"  Sample errors: {result.get('errors')[:3]}"
                ))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Fatal error during restore: {e}"))
