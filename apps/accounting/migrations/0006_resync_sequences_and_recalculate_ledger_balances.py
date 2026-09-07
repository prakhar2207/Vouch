# Generated manually to repair sequence counter and ledger balance drift
from decimal import Decimal
import datetime
import re
from django.db import migrations
from django.db.models import Sum

def resync_all(apps, schema_editor):
    Company = apps.get_model('companies', 'Company')
    Ledger = apps.get_model('ledgers', 'Ledger')
    FinancialYear = apps.get_model('accounting', 'FinancialYear')
    Voucher = apps.get_model('accounting', 'Voucher')
    VoucherSequence = apps.get_model('accounting', 'VoucherSequence')
    LedgerEntry = apps.get_model('accounting', 'LedgerEntry')

    # 1. Backfill any missing financial_year on existing vouchers
    for v in Voucher.objects.filter(financial_year__isnull=True):
        v_date = v.voucher_date or datetime.date.today()
        if v_date.month >= 4:
            s_year = v_date.year
            e_year = v_date.year + 1
        else:
            s_year = v_date.year - 1
            e_year = v_date.year
        code = f"{str(s_year)[-2:]}-{str(e_year)[-2:]}"
        fy = FinancialYear.objects.filter(company=v.company, code=code).first()
        if not fy:
            fy = FinancialYear.objects.create(
                company=v.company,
                code=code,
                name=f"FY {s_year}-{str(e_year)[-2:]}",
                start_date=datetime.date(s_year, 4, 1),
                end_date=datetime.date(e_year, 3, 31),
                is_closed=False
            )
        v.financial_year = fy
        v.save(update_fields=['financial_year'])

    # 2. Recalculate all ledger current balances strictly from opening balance + posted entries
    for ledger in Ledger.objects.all():
        op_bal = Decimal(str(ledger.opening_balance or 0))
        totals = LedgerEntry.objects.filter(
            ledger=ledger,
            voucher__status='POSTED'
        ).aggregate(
            total_dr=Sum('debit_amount'),
            total_cr=Sum('credit_amount')
        )
        dr = Decimal(str(totals['total_dr'] or 0))
        cr = Decimal(str(totals['total_cr'] or 0))

        if ledger.opening_balance_type == 'DEBIT':
            new_bal = op_bal + dr - cr
        else:
            new_bal = op_bal + cr - dr

        if ledger.current_balance != new_bal:
            ledger.current_balance = new_bal
            ledger.save(update_fields=['current_balance'])

    # 3. Resync all VoucherSequences across companies and financial years to match existing vouchers
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
                        seq.save(update_fields=['last_number'])
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
        ('accounting', '0005_financialyear_is_split_archived_and_more'),
        ('ledgers', '0003_consolidate_party_ledgers'),
    ]

    operations = [
        migrations.RunPython(resync_all, reverse_resync),
    ]
