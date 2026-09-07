from django.db import migrations

def reassign_round_off_to_indirect_expenses(apps, schema_editor):
    Ledger = apps.get_model('ledgers', 'Ledger')
    LedgerGroup = apps.get_model('ledgers', 'LedgerGroup')
    Company = apps.get_model('companies', 'Company')

    for company in Company.objects.all():
        indirect_grp, _ = LedgerGroup.objects.get_or_create(
            company=company,
            name="Indirect Expenses",
            defaults={"nature": "EXPENSE"}
        )
        round_off_ledgers = Ledger.objects.filter(company=company, name__iexact="Round Off")
        for ro in round_off_ledgers:
            if ro.group_id != indirect_grp.id:
                ro.group = indirect_grp
                ro.save(update_fields=['group'])

class Migration(migrations.Migration):

    dependencies = [
        ('ledgers', '0004_ledger_discount_percent'),
    ]

    operations = [
        migrations.RunPython(
            reassign_round_off_to_indirect_expenses,
            reverse_code=migrations.RunPython.noop
        ),
    ]
