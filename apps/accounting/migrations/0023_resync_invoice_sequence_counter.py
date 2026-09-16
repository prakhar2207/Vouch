# Generated manually to resync invoice sequences to match actual existing vouchers
import re
from django.db import migrations

DEFAULT_PREFIXES = {
    'SALES': 'INV',
    'PURCHASE': 'PUR',
    'PAYMENT': 'PAY',
    'RECEIPT': 'RCP',
    'CONTRA': 'CNT',
    'JOURNAL': 'JRN',
    'CREDIT_NOTE': 'CN',
    'DEBIT_NOTE': 'DN',
}

def resync_sequences(apps, schema_editor):
    Company = apps.get_model('companies', 'Company')
    FinancialYear = apps.get_model('accounting', 'FinancialYear')
    Voucher = apps.get_model('accounting', 'Voucher')
    VoucherSequence = apps.get_model('accounting', 'VoucherSequence')

    for company in Company.objects.all():
        for fy in FinancialYear.objects.filter(company=company):
            for v_type, default_prefix in DEFAULT_PREFIXES.items():
                vouchers = Voucher.objects.filter(
                    company=company,
                    financial_year=fy,
                    voucher_type=v_type
                ).values_list('voucher_number', flat=True)

                prefix_fy = f"{default_prefix}/{fy.code}/".upper()
                prefix_dash = f"{default_prefix}-".upper()
                prefix_slash = f"{default_prefix}/".upper()

                max_num = 0
                for v_num in vouchers:
                    if not v_num:
                        continue
                    v_str = str(v_num).strip().upper()
                    num = None
                    if v_str.startswith(prefix_fy):
                        tail = v_str[len(prefix_fy):].strip()
                        if tail.isdigit():
                            num = int(tail)
                    elif v_str.startswith(prefix_dash):
                        tail = v_str[len(prefix_dash):].strip()
                        if tail.isdigit():
                            num = int(tail)
                    elif v_str.startswith(prefix_slash):
                        tail = v_str[len(prefix_slash):].strip()
                        if tail.isdigit():
                            num = int(tail)
                    elif v_str.isdigit():
                        num = int(v_str)
                    else:
                        m = re.search(r'(\d+)$', v_str)
                        if m:
                            try:
                                num = int(m.group(1))
                            except ValueError:
                                pass

                    if num is not None and num > max_num:
                        max_num = num

                seq = VoucherSequence.objects.filter(
                    company=company,
                    financial_year=fy,
                    voucher_type=v_type
                ).first()

                if seq:
                    if seq.last_number != max_num:
                        seq.last_number = max_num
                        seq.save(update_fields=['last_number', 'updated_at'])
                elif max_num > 0:
                    VoucherSequence.objects.create(
                        company=company,
                        financial_year=fy,
                        voucher_type=v_type,
                        prefix=default_prefix,
                        last_number=max_num
                    )

def reverse_resync(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('accounting', '0022_banktransaction_bank_tx_non_negative_amounts_and_more'),
    ]

    operations = [
        migrations.RunPython(resync_sequences, reverse_code=reverse_resync),
    ]
