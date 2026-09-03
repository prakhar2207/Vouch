import datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Q
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import FinancialYear, Voucher, LedgerEntry, LedgerBalance

class YearEndClosingService:
    @staticmethod
    def pre_close_audit(company_id: str, current_fy_id: str) -> dict:
        """
        Pre-closing audit checklist:
        1. Checks for unposted (draft/validating) vouchers.
        2. Checks trial balance equilibrium (Total Debit == Total Credit).
        3. Returns validation status.
        """
        fy = FinancialYear.objects.get(id=current_fy_id, company_id=company_id)

        # 1. Unposted vouchers count
        unposted_count = Voucher.objects.filter(
            company_id=company_id,
            financial_year=fy,
            status__in=['DRAFT', 'VALIDATING']
        ).count()

        # 2. Total Debits and Credits in FY
        entries_agg = LedgerEntry.objects.filter(
            voucher__company_id=company_id,
            voucher__financial_year=fy,
            voucher__status='POSTED'
        ).aggregate(
            total_dr=Sum('debit_amount'),
            total_cr=Sum('credit_amount')
        )

        total_dr = entries_agg.get('total_dr') or Decimal('0.00')
        total_cr = entries_agg.get('total_cr') or Decimal('0.00')
        trial_balance_diff = abs(total_dr - total_cr)
        is_balanced = trial_balance_diff == Decimal('0.00')

        # 3. Total Vouchers Count
        total_vouchers = Voucher.objects.filter(
            company_id=company_id,
            financial_year=fy
        ).count()

        return {
            "financial_year_id": str(fy.id),
            "financial_year_name": fy.name,
            "financial_year_code": fy.code,
            "is_closed": fy.is_closed,
            "total_vouchers": total_vouchers,
            "unposted_vouchers_count": unposted_count,
            "total_debits": str(total_dr),
            "total_credits": str(total_cr),
            "trial_balance_difference": str(trial_balance_diff),
            "is_trial_balance_balanced": is_balanced,
            "can_close": unposted_count == 0 and is_balanced and not fy.is_closed
        }

    @staticmethod
    @transaction.atomic
    def close_and_roll_forward(company_id: str, current_fy_id: str, next_fy_id: str = None) -> dict:
        """
        Executes Year-End Closing and Balance Carry-Forward:
        1. Computes closing balance for all active ledgers in current FY.
        2. Rolls forward Balance Sheet accounts (Assets, Liabilities, Equity) to next FY as Opening Balances.
        3. Computes Net Profit/Loss from P&L accounts (Income vs Expenses) and transfers it to Retained Earnings in next FY.
        4. Resets nominal P&L accounts to 0.00 in next FY.
        5. Marks current FY as closed.
        """
        current_fy = FinancialYear.objects.select_for_update().get(id=current_fy_id, company_id=company_id)
        if current_fy.is_closed:
            raise ValidationError(f"Financial Year '{current_fy.name}' is already closed.")

        audit = YearEndClosingService.pre_close_audit(company_id, current_fy_id)
        if audit['unposted_vouchers_count'] > 0:
            raise ValidationError(
                f"Cannot close Financial Year: There are {audit['unposted_vouchers_count']} unposted draft vouchers. Please post or cancel them first."
            )

        # 1. Resolve or Create next FY
        if next_fy_id:
            next_fy = FinancialYear.objects.get(id=next_fy_id, company_id=company_id)
        else:
            next_start_date = current_fy.end_date + datetime.timedelta(days=1)
            next_end_date = datetime.date(next_start_date.year + 1, 3, 31)
            start_yy = str(next_start_date.year)[-2:]
            end_yy = str(next_start_date.year + 1)[-2:]
            next_code = f"{start_yy}-{end_yy}"
            next_name = f"FY {next_start_date.year}-{end_yy}"

            next_fy, _ = FinancialYear.objects.get_or_create(
                company_id=company_id,
                code=next_code,
                defaults={
                    'name': next_name,
                    'start_date': next_start_date,
                    'end_date': next_end_date,
                    'is_closed': False
                }
            )

        company_ledgers = Ledger.objects.filter(company_id=company_id).select_related('group')

        total_income = Decimal('0.00')
        total_expense = Decimal('0.00')
        carried_accounts_count = 0

        # 2. Iterate through ledgers and calculate closing balances
        for ledger in company_ledgers:
            # Determine current FY opening balance
            existing_lb = LedgerBalance.objects.filter(ledger=ledger, financial_year=current_fy).first()
            if existing_lb:
                op_dr = existing_lb.opening_balance if existing_lb.opening_type == 'DR' else Decimal('0.00')
                op_cr = existing_lb.opening_balance if existing_lb.opening_type == 'CR' else Decimal('0.00')
            else:
                op_dr = ledger.opening_balance if ledger.opening_balance_type == 'DEBIT' else Decimal('0.00')
                op_cr = ledger.opening_balance if ledger.opening_balance_type == 'CREDIT' else Decimal('0.00')

            # Aggregate posted voucher entries in current FY
            entries_agg = LedgerEntry.objects.filter(
                voucher__company_id=company_id,
                voucher__financial_year=current_fy,
                voucher__status='POSTED',
                ledger=ledger
            ).aggregate(
                dr=Sum('debit_amount'),
                cr=Sum('credit_amount')
            )
            period_dr = entries_agg.get('dr') or Decimal('0.00')
            period_cr = entries_agg.get('cr') or Decimal('0.00')

            # Net Balance = (Opening Dr - Opening Cr) + (Period Dr - Period Cr)
            net_balance = (op_dr - op_cr) + (period_dr - period_cr)
            if net_balance >= Decimal('0.00'):
                closing_amount = net_balance
                closing_type = 'DR'
            else:
                closing_amount = abs(net_balance)
                closing_type = 'CR'

            # Save closing balance for current FY
            LedgerBalance.objects.update_or_create(
                ledger=ledger,
                financial_year=current_fy,
                defaults={
                    'opening_balance': (op_dr if op_dr >= op_cr else op_cr),
                    'opening_type': ('DR' if op_dr >= op_cr else 'CR'),
                    'closing_balance': closing_amount,
                    'closing_type': closing_type
                }
            )

            group_nature = (ledger.group.nature or '').upper()

            # 3. Balance Sheet Accounts -> Roll forward to next FY
            if group_nature in ['ASSET', 'LIABILITY', 'EQUITY']:
                LedgerBalance.objects.update_or_create(
                    ledger=ledger,
                    financial_year=next_fy,
                    defaults={
                        'opening_balance': closing_amount,
                        'opening_type': closing_type,
                        'closing_balance': closing_amount,
                        'closing_type': closing_type
                    }
                )
                carried_accounts_count += 1

            # 4. P&L Accounts (Income & Expense) -> Track for Net Profit/Loss and reset opening in next FY
            elif group_nature in ['INCOME', 'EXPENSE']:
                if group_nature == 'INCOME':
                    # Income is naturally Credit
                    total_income += (period_cr - period_dr)
                else:
                    # Expense is naturally Debit
                    total_expense += (period_dr - period_cr)

                # Reset to 0 in next FY
                LedgerBalance.objects.update_or_create(
                    ledger=ledger,
                    financial_year=next_fy,
                    defaults={
                        'opening_balance': Decimal('0.00'),
                        'opening_type': 'DR',
                        'closing_balance': Decimal('0.00'),
                        'closing_type': 'DR'
                    }
                )

        # 5. Transfer Net Profit / Loss to Retained Earnings / Capital Account in next FY
        net_profit = total_income - total_expense  # Positive = Profit, Negative = Loss
        if net_profit != Decimal('0.00'):
            equity_group, _ = LedgerGroup.objects.get_or_create(
                company_id=company_id,
                name='Retained Earnings & Reserves',
                defaults={'nature': 'EQUITY'}
            )
            re_ledger, _ = Ledger.objects.get_or_create(
                company_id=company_id,
                name='Retained Earnings',
                defaults={
                    'group': equity_group,
                    'ledger_type': 'GENERAL',
                    'opening_balance': Decimal('0.00')
                }
            )

            # Check existing opening balance of Retained Earnings in next FY
            re_balance = LedgerBalance.objects.filter(ledger=re_ledger, financial_year=next_fy).first()
            current_re_op = Decimal('0.00')
            current_re_type = 'CR'
            if re_balance:
                current_re_op = re_balance.opening_balance
                current_re_type = re_balance.opening_type

            # Profit increases Credit (Equity); Loss increases Debit
            signed_re = (current_re_op if current_re_type == 'CR' else -current_re_op) + net_profit
            new_re_type = 'CR' if signed_re >= Decimal('0.00') else 'DR'
            new_re_amount = abs(signed_re)

            LedgerBalance.objects.update_or_create(
                ledger=re_ledger,
                financial_year=next_fy,
                defaults={
                    'opening_balance': new_re_amount,
                    'opening_type': new_re_type,
                    'closing_balance': new_re_amount,
                    'closing_type': new_re_type
                }
            )

        # 6. Mark current FY as closed
        current_fy.is_closed = True
        current_fy.save(update_fields=['is_closed'])

        return {
            "success": True,
            "closed_financial_year": current_fy.name,
            "next_financial_year": next_fy.name,
            "carried_accounts_count": carried_accounts_count,
            "total_income": str(total_income),
            "total_expense": str(total_expense),
            "net_profit_loss": str(net_profit),
            "profit_loss_type": "PROFIT" if net_profit >= 0 else "LOSS",
            "message": f"Financial Year {current_fy.name} closed successfully. Real & Personal balances rolled forward to {next_fy.name}."
        }
