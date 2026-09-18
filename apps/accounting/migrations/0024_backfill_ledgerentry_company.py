# Generated to backfill company_id on LedgerEntry from voucher.company_id
from django.db import migrations

def backfill_ledger_entry_company(apps, schema_editor):
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('''
            UPDATE accounting_ledgerentry
            SET company_id = (
                SELECT company_id FROM accounting_voucher
                WHERE accounting_voucher.id = accounting_ledgerentry.voucher_id
            )
            WHERE company_id IS NULL;
        ''')

def reverse_backfill(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('accounting', '0023_resync_invoice_sequence_counter'),
    ]

    operations = [
        migrations.RunPython(backfill_ledger_entry_company, reverse_code=reverse_backfill),
    ]
