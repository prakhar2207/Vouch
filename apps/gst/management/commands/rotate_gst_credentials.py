import logging
from typing import List, Dict, Any
from django.core.management.base import BaseCommand
from django.db import transaction, connection
from apps.gst.models import CompanyGSTConfig, GSTRegistration
from apps.gst.encryption import (
    rotate_credential_value,
    is_encrypted_with_primary_key,
    ENCRYPTION_PREFIX,
    CredentialDecryptionError
)

logger = logging.getLogger('apps.gst.rotation')


def _get_raw_row(model_class, pk, field_names):
    """
    Directly fetches raw ciphertext from the database without invoking
    Django field converters (from_db_value), allowing inspection of the
    exact ciphertext envelope for idempotency checking.
    """
    table_name = model_class._meta.db_table
    col_names = [model_class._meta.get_field(f).column for f in field_names]
    col_str = ", ".join([f'"{c}"' for c in col_names])
    clean_pk = str(pk).replace('-', '')
    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT {col_str} FROM "{table_name}" WHERE "id" = %s OR "id" = %s',
            [str(pk), clean_pk]
        )
        row = cursor.fetchone()
        if not row:
            return {}
        return dict(zip(field_names, row))

CONFIG_ENCRYPTED_FIELDS = [
    'api_key',
    'api_secret',
    'sandbox_api_key',
    'sandbox_api_secret',
    'sandbox_access_token',
    'eway_password',
    'einvoice_password',
    'auth_token'
]

REGISTRATION_ENCRYPTED_FIELDS = [
    'auth_token',
    'einvoice_password',
    'eway_password'
]


class Command(BaseCommand):
    help = (
        "Re-encrypts stored GST credentials using the current primary GST_ENCRYPTION_KEY. "
        "Supports backward compatibility via GST_ENCRYPTION_KEY_OLD. "
        "Idempotent and safe to run multiple times."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate rotation without modifying database records.'
        )
        parser.add_argument(
            '--company-id',
            type=str,
            help='Rotate credentials for a specific company UUID only.'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Batch size for database updates (default: 100).'
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        company_id = options.get('company_id')
        batch_size = options.get('batch_size', 100)

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Starting GST Credential Key Rotation [Dry Run: {dry_run}]"
            )
        )

        stats = {
            "configs_processed": 0,
            "configs_rotated": 0,
            "registrations_processed": 0,
            "registrations_rotated": 0,
            "fields_rotated": 0,
            "fields_skipped": 0,
            "fields_failed": 0,
        }

        # 1. Rotate CompanyGSTConfig records
        config_qs = CompanyGSTConfig.objects.all()
        if company_id:
            config_qs = config_qs.filter(company_id=company_id)

        for config in config_qs.iterator(chunk_size=batch_size):
            stats["configs_processed"] += 1
            fields_to_update = []
            has_error = False

            # Query raw database values to inspect ciphertext directly
            raw_row = _get_raw_row(CompanyGSTConfig, config.pk, CONFIG_ENCRYPTED_FIELDS)
            if not raw_row:
                continue

            for field_name in CONFIG_ENCRYPTED_FIELDS:
                raw_cipher = raw_row.get(field_name) or ""
                if not raw_cipher:
                    stats["fields_skipped"] += 1
                    continue

                if is_encrypted_with_primary_key(raw_cipher):
                    stats["fields_skipped"] += 1
                    continue

                try:
                    new_cipher, was_rotated = rotate_credential_value(raw_cipher)
                    if was_rotated:
                        # Assign raw ciphertext directly to avoid double prep_value
                        setattr(config, field_name, new_cipher)
                        fields_to_update.append(field_name)
                        stats["fields_rotated"] += 1
                    else:
                        stats["fields_skipped"] += 1
                except Exception as e:
                    has_error = True
                    stats["fields_failed"] += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to rotate field '{field_name}' for CompanyGSTConfig {config.pk}: {type(e).__name__}"
                        )
                    )

            if fields_to_update and not dry_run and not has_error:
                with transaction.atomic():
                    # Direct SQL update or update_fields to preserve exact raw ciphertext
                    CompanyGSTConfig.objects.filter(pk=config.pk).update(
                        **{fname: getattr(config, fname) for fname in fields_to_update}
                    )
                stats["configs_rotated"] += 1
            elif fields_to_update and dry_run:
                stats["configs_rotated"] += 1

        # 2. Rotate GSTRegistration records
        reg_qs = GSTRegistration.objects.all()
        if company_id:
            reg_qs = reg_qs.filter(company_id=company_id)

        for reg in reg_qs.iterator(chunk_size=batch_size):
            stats["registrations_processed"] += 1
            fields_to_update = []
            has_error = False

            raw_row = _get_raw_row(GSTRegistration, reg.pk, REGISTRATION_ENCRYPTED_FIELDS)
            if not raw_row:
                continue

            for field_name in REGISTRATION_ENCRYPTED_FIELDS:
                raw_cipher = raw_row.get(field_name) or ""
                if not raw_cipher:
                    stats["fields_skipped"] += 1
                    continue

                if is_encrypted_with_primary_key(raw_cipher):
                    stats["fields_skipped"] += 1
                    continue

                try:
                    new_cipher, was_rotated = rotate_credential_value(raw_cipher)
                    if was_rotated:
                        setattr(reg, field_name, new_cipher)
                        fields_to_update.append(field_name)
                        stats["fields_rotated"] += 1
                    else:
                        stats["fields_skipped"] += 1
                except Exception as e:
                    has_error = True
                    stats["fields_failed"] += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to rotate field '{field_name}' for GSTRegistration {reg.pk}: {type(e).__name__}"
                        )
                    )

            if fields_to_update and not dry_run and not has_error:
                with transaction.atomic():
                    GSTRegistration.objects.filter(pk=reg.pk).update(
                        **{fname: getattr(reg, fname) for fname in fields_to_update}
                    )
                stats["registrations_rotated"] += 1
            elif fields_to_update and dry_run:
                stats["registrations_rotated"] += 1

        # Output Summary
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- Key Rotation Summary ---"))
        self.stdout.write(f"Company Configurations Processed: {stats['configs_processed']}")
        self.stdout.write(f"Company Configurations Rotated:   {stats['configs_rotated']}")
        self.stdout.write(f"GST Registrations Processed:      {stats['registrations_processed']}")
        self.stdout.write(f"GST Registrations Rotated:        {stats['registrations_rotated']}")
        self.stdout.write(f"Total Fields Rotated:             {stats['fields_rotated']}")
        self.stdout.write(f"Total Fields Skipped (Unchanged): {stats['fields_skipped']}")
        self.stdout.write(f"Total Fields Failed:              {stats['fields_failed']}")

        if stats["fields_failed"] > 0:
            self.stdout.write(
                self.style.ERROR("ROTATION INCOMPLETE: One or more fields failed decryption. Do NOT remove GST_ENCRYPTION_KEY_OLD!")
            )
            return

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run completed successfully. No database records were modified."))
        else:
            self.stdout.write(self.style.SUCCESS("Credential re-encryption completed successfully."))
