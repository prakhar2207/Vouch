from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import LedgerEntry

class BalanceRebuildService:
    @staticmethod
    @transaction.atomic
    def rebuild_company_ledger_balances(company: Company) -> dict:
        """
        Reconstructs every ledger's current_balance from scratch by evaluating
        its opening balance and aggregating all immutable POSTED ledger entries.
        Uses batch queries to eliminate N+1 latency across remote database connections.
        Eliminates any data drift.
        """
        ledgers = list(Ledger.objects.filter(company=company).select_related('group'))
        if not ledgers:
            return {
                "success": True,
                "company_id": str(company.id),
                "company_name": company.name,
                "rebuilt_ledgers_count": 0,
                "balances": {}
            }

        ledger_ids = [l.id for l in ledgers]

        # 1. Batch query: Ledgers that have double-entry opening vouchers
        ledgers_with_opening = set(
            LedgerEntry.objects.filter(
                ledger_id__in=ledger_ids,
                voucher__company=company,
                voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED'],
                voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
            ).values_list('ledger_id', flat=True).distinct()
        )

        # 2. Batch query: Sum of debits and credits per ledger
        totals_qs = LedgerEntry.objects.filter(
            ledger_id__in=ledger_ids,
            voucher__company=company,
            voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED']
        ).values('ledger_id').annotate(
            total_dr=Sum('debit_amount'),
            total_cr=Sum('credit_amount')
        )
        totals_map = {row['ledger_id']: row for row in totals_qs}

        results = {}
        to_update = []

        for ledger in ledgers:
            has_op = ledger.id in ledgers_with_opening
            op_balance = Decimal('0.00') if has_op else Decimal(str(ledger.opening_balance or '0.00'))

            if ledger.opening_balance_type == 'CREDIT':
                op_dr = Decimal('0.00')
                op_cr = op_balance
            else:
                op_dr = op_balance
                op_cr = Decimal('0.00')

            t = totals_map.get(ledger.id)
            dr_sum = Decimal(str(t['total_dr'] or '0.00')) if t else Decimal('0.00')
            cr_sum = Decimal(str(t['total_cr'] or '0.00')) if t else Decimal('0.00')

            total_dr = op_dr + dr_sum
            total_cr = op_cr + cr_sum

            if ledger.normal_balance == 'CREDIT':
                new_bal = total_cr - total_dr
            else:
                new_bal = total_dr - total_cr

            ledger.current_balance = new_bal
            to_update.append(ledger)
            results[str(ledger.id)] = {
                "name": ledger.name,
                "current_balance": str(new_bal)
            }

        Ledger.objects.bulk_update(to_update, ['current_balance'])

        return {
            "success": True,
            "company_id": str(company.id),
            "company_name": company.name,
            "rebuilt_ledgers_count": len(to_update),
            "balances": results
        }
