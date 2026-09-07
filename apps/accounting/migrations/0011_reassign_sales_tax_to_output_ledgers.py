from django.db import migrations
from decimal import Decimal

def reassign_sales_tax_entries(apps, schema_editor):
    Company = apps.get_model('companies', 'Company')
    Ledger = apps.get_model('ledgers', 'Ledger')
    LedgerGroup = apps.get_model('ledgers', 'LedgerGroup')
    LedgerEntry = apps.get_model('accounting', 'LedgerEntry')

    for company in Company.objects.all():
        duties_grp, _ = LedgerGroup.objects.get_or_create(
            company=company,
            name='Duties & Taxes',
            defaults={'nature': 'LIABILITY'}
        )

        output_cgst, _ = Ledger.objects.get_or_create(
            company=company,
            name='Output CGST',
            defaults={'group': duties_grp, 'ledger_type': 'TAX'}
        )
        output_sgst, _ = Ledger.objects.get_or_create(
            company=company,
            name='Output SGST',
            defaults={'group': duties_grp, 'ledger_type': 'TAX'}
        )
        output_igst, _ = Ledger.objects.get_or_create(
            company=company,
            name='Output IGST',
            defaults={'group': duties_grp, 'ledger_type': 'TAX'}
        )

        affected_ledgers = set()

        # Find all credit entries in Sales vouchers that hit an Input tax ledger or generic tax ledger
        sales_tax_entries = LedgerEntry.objects.filter(
            voucher__company=company,
            voucher__voucher_type='SALES',
            credit_amount__gt=0
        ).select_related('ledger')

        for entry in sales_tax_entries:
            lname = (entry.ledger.name or '').upper()
            if 'INPUT' in lname or lname in ['CGST', 'SGST', 'IGST']:
                affected_ledgers.add(entry.ledger)
                if 'CGST' in lname:
                    entry.ledger = output_cgst
                    affected_ledgers.add(output_cgst)
                elif 'SGST' in lname or 'UTGST' in lname:
                    entry.ledger = output_sgst
                    affected_ledgers.add(output_sgst)
                elif 'IGST' in lname:
                    entry.ledger = output_igst
                    affected_ledgers.add(output_igst)
                entry.save(update_fields=['ledger'])

        # Recalculate balances strictly from the single source of truth for all affected ledgers
        for ledger in affected_ledgers:
            op_balance = Decimal(str(ledger.opening_balance or '0.00'))
            entries = LedgerEntry.objects.filter(ledger=ledger, voucher__status='POSTED')
            total_dr = Decimal('0.00')
            total_cr = Decimal('0.00')
            for e in entries:
                total_dr += Decimal(str(e.debit_amount or '0.00'))
                total_cr += Decimal(str(e.credit_amount or '0.00'))

            if ledger.opening_balance_type == 'DEBIT':
                ledger.current_balance = op_balance + total_dr - total_cr
            else:
                ledger.current_balance = op_balance + total_cr - total_dr

            ledger.save(update_fields=['current_balance'])

class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0010_voucher_buyer_details'),
    ]

    operations = [
        migrations.RunPython(reassign_sales_tax_entries, migrations.RunPython.noop),
    ]
