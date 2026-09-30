from django.core.management.base import BaseCommand
from apps.common.services.backup_service import DatabaseBackupService

class Command(BaseCommand):
    help = 'Executes an automated, compressed, AES-256 encrypted database snapshot with off-site S3 upload.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-encrypt',
            action='store_true',
            help='Skip AES-256 encryption (produces standard .sql.gz).',
        )
        parser.add_argument(
            '--no-s3',
            action='store_true',
            help='Skip S3 upload and retain only local encrypted copy.',
        )
        parser.add_argument(
            '--output-dir',
            type=str,
            default=None,
            help='Custom output directory for the backup file.',
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Test decryption and verify data integrity immediately after backup.',
        )

    def handle(self, *args, **options):
        no_encrypt = options.get('no_encrypt', False)
        no_s3 = options.get('no_s3', False)
        output_dir = options.get('output_dir')
        verify = options.get('verify', False)

        self.stdout.write(self.style.NOTICE("Starting database disaster recovery backup..."))

        result = DatabaseBackupService.perform_backup(
            upload_s3=not no_s3,
            encrypt=not no_encrypt,
            output_dir=output_dir
        )

        if not result.get('success'):
            self.stderr.write(self.style.ERROR(f"Backup failed: {result.get('error')}"))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Backup Succeeded!\n"
            f"  File: {result.get('file_name')}\n"
            f"  Size: {result.get('file_size_mb')} MB\n"
            f"  Encrypted: {result.get('is_encrypted')}\n"
            f"  SHA-256: {result.get('sha256_checksum')}\n"
            f"  S3 Uploaded: {result.get('s3_uploaded')} ({result.get('s3_uri') or 'N/A'})\n"
            f"  Elapsed: {result.get('elapsed_seconds')}s"
        ))

        if verify and result.get('is_encrypted'):
            self.stdout.write(self.style.NOTICE("Testing AES-256 decryption integrity..."))
            try:
                with open(result['file_path'], 'rb') as f:
                    enc_data = f.read()
                dec_data = DatabaseBackupService.decrypt_data(enc_data)
                self.stdout.write(self.style.SUCCESS(f"  Integrity verified! Decrypted stream size: {len(dec_data)} bytes."))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  Decryption test FAILED: {e}"))
