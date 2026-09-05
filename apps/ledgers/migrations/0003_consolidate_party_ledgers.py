# Generated for data consolidation: Satyam & Co. and Apex cleanup

from django.db import migrations
from decimal import Decimal


def consolidate_party_ledgers(apps, schema_editor):
    Ledger = apps.get_model('ledgers', 'Ledger')
    Company = apps.get_model('companies', 'Company')
    Voucher = apps.get_model('accounting', 'Voucher')
    LedgerEntry = apps.get_model('accounting', 'LedgerEntry')
    LedgerBalance = apps.get_model('accounting', 'LedgerBalance')

    # 1. Delete Apex customer ledgers and any associated transactions
    apex_ledgers = list(Ledger.objects.filter(name__icontains='Apex'))
    for apex in apex_ledgers:
        for v in Voucher.objects.filter(party_ledger=apex):
            v.items.all().delete()
            v.ledger_entries.all().delete()
            v.delete()
        LedgerEntry.objects.filter(ledger=apex).delete()
        LedgerBalance.objects.filter(ledger=apex).delete()
        apex.delete()

    # 2. Consolidate Satyam & Co. instances into 1 single canonical ledger per company
    for company in Company.objects.all():
        satyam_ledgers = list(Ledger.objects.filter(company=company, name__icontains='Satyam').order_by('created_at'))
        if not satyam_ledgers:
            continue

        canonical = satyam_ledgers[0]
        for l in satyam_ledgers:
            if l.gstin and not canonical.gstin:
                canonical = l
                break

        canonical.name = 'Satyam & Co.'
        canonical.ledger_type = 'SUPPLIER'

        for dup in satyam_ledgers:
            if dup.id == canonical.id:
                continue

            if dup.gstin and not canonical.gstin:
                canonical.gstin = dup.gstin
            if dup.address and not canonical.address:
                canonical.address = dup.address
            if dup.phone and not canonical.phone:
                canonical.phone = dup.phone
            if dup.email and not canonical.email:
                canonical.email = dup.email
            if dup.state_code and not canonical.state_code:
                canonical.state_code = dup.state_code

            Voucher.objects.filter(party_ledger=dup).update(party_ledger=canonical)
            LedgerEntry.objects.filter(ledger=dup).update(ledger=canonical)
            LedgerBalance.objects.filter(ledger=dup).delete()
            dup.delete()

        entries = LedgerEntry.objects.filter(ledger=canonical)
        total_dr = sum(Decimal(str(e.debit_amount or 0)) for e in entries)
        total_cr = sum(Decimal(str(e.credit_amount or 0)) for e in entries)
        op = Decimal(str(canonical.opening_balance or 0))

        if canonical.opening_balance_type == 'DEBIT':
            canonical.current_balance = op + total_dr - total_cr
        else:
            canonical.current_balance = op + total_cr - total_dr

        canonical.save()


class Migration(migrations.Migration):

    dependencies = [
        ('ledgers', '0002_ledger_opening_date'),
        ('accounting', '0005_financialyear_is_split_archived_and_more'),
    ]

    operations = [
        migrations.RunPython(consolidate_party_ledgers, reverse_code=migrations.RunPython.noop),
    ]
