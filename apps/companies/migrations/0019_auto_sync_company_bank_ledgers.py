from django.db import migrations

def sync_existing_company_bank_ledgers(apps, schema_editor):
    Company = apps.get_model('companies', 'Company')
    Ledger = apps.get_model('ledgers', 'Ledger')
    LedgerGroup = apps.get_model('ledgers', 'LedgerGroup')
    from decimal import Decimal

    for company in Company.objects.all():
        bank_name = str(company.bank_name or '').strip()
        account_number = str(company.bank_account_number or '').strip()
        bank_ifsc = str(company.bank_ifsc or '').strip().upper()
        upi_id = str(company.upi_id or '').strip()

        if not bank_name and not account_number:
            continue

        bank_grp, _ = LedgerGroup.objects.get_or_create(
            company=company,
            name="Bank Accounts",
            defaults={"nature": "ASSET"}
        )

        if bank_name and account_number:
            last4 = account_number[-4:] if len(account_number) >= 4 else account_number
            canonical_name = f"{bank_name} (A/c ...{last4})"
        elif bank_name:
            canonical_name = bank_name
        else:
            last4 = account_number[-4:] if len(account_number) >= 4 else account_number
            canonical_name = f"Bank Account (A/c ...{last4})"

        # Check existing
        ledger = None
        if account_number:
            ledger = Ledger.objects.filter(
                company=company,
                ledger_type__in=['BANK', 'BANK_OD', 'BANK_OCC'],
                bank_account_number__iexact=account_number
            ).first()

        if not ledger:
            ledger = Ledger.objects.filter(
                company=company,
                ledger_type__in=['BANK', 'BANK_OD', 'BANK_OCC'],
                name__iexact=canonical_name
            ).first()

        if not ledger and bank_name:
            candidates = Ledger.objects.filter(
                company=company,
                ledger_type__in=['BANK', 'BANK_OD', 'BANK_OCC']
            )
            for cand in candidates:
                if (bank_name.lower() in cand.name.lower() or cand.name.lower() in bank_name.lower()) and not cand.bank_account_number:
                    ledger = cand
                    break
            if not ledger and candidates.count() == 1:
                single_cand = candidates.first()
                if not single_cand.bank_account_number or single_cand.name.strip().lower() in ['bank', 'bank account', 'bank a/c']:
                    ledger = single_cand

        if ledger:
            if account_number and ledger.bank_account_number != account_number:
                ledger.bank_account_number = account_number
            if bank_ifsc and ledger.bank_ifsc != bank_ifsc:
                ledger.bank_ifsc = bank_ifsc
            if upi_id and ledger.upi_id != upi_id:
                ledger.upi_id = upi_id
            ledger.is_active = True
            ledger.is_archived = False
            if ledger.name.strip().lower() in ['bank', 'bank account', 'bank a/c']:
                ledger.name = canonical_name
            ledger.save()
        else:
            Ledger.objects.create(
                company=company,
                group=bank_grp,
                name=canonical_name,
                ledger_type='BANK',
                bank_account_number=account_number,
                bank_ifsc=bank_ifsc,
                upi_id=upi_id,
                opening_balance=Decimal('0.00'),
                opening_balance_type='DEBIT',
                is_active=True,
                is_archived=False
            )


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0018_company_upi_id'),
        ('ledgers', '0008_ledger_ledgers_led_company_f40106_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(sync_existing_company_bank_ledgers, reverse_noop),
    ]
