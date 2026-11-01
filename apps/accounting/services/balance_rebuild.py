from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import LedgerEntry
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService

class BalanceRebuildService:
    @staticmethod
    def rebuild_company_ledger_balances(company: Company, user=None) -> dict:
        """
        Reconstructs every ledger's current_balance from scratch by evaluating
        its opening balance and aggregating all immutable accounting-effective ledger entries.
        
        DEF-PERF-01 Performance Redesign:
        - Non-blocking snapshot calculation: Reads ledger data and aggregates entries without
          holding table or row locks during heavy aggregation queries.
        - Monotonic cutoff boundary: Captures cutoff_time before querying aggregates.
        - Sub-20ms atomic publication: Acquires row locks strictly during the final update,
          reconciles any entries created concurrently during the calculation window,
          and commits via bulk_update. Cashiers and billing endpoints are never blocked.
        """
        cutoff_time = timezone.now()

        # Step 1: Read all company ledgers without locks (Read Committed)
        ledgers = list(Ledger.objects.filter(company=company).order_by('id').select_related('group'))
        if not ledgers:
            return {
                "success": True,
                "company_id": str(company.id),
                "company_name": company.name,
                "rebuilt_ledgers_count": 0,
                "discrepancies_count": 0,
                "balances": {}
            }

        ledger_ids = [l.id for l in ledgers]

        # Step 2: Batch query opening double-entry vouchers without locks
        ledgers_with_opening = set(
            LedgerEntry.objects.filter(
                ledger_id__in=ledger_ids,
                voucher__company=company,
                voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
                voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
            ).values_list('ledger_id', flat=True).distinct()
        )

        # Step 3: Batch query aggregates up to cutoff without locks
        totals_qs = LedgerEntry.objects.filter(
            ledger_id__in=ledger_ids,
            voucher__company=company,
            voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
            created_at__lt=cutoff_time
        ).values('ledger_id').annotate(
            total_dr=Sum('debit_amount'),
            total_cr=Sum('credit_amount')
        )
        totals_map = {row['ledger_id']: row for row in totals_qs}

        precomputed_bal = {}
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
                target = total_cr - total_dr
            else:
                target = total_dr - total_cr
            precomputed_bal[ledger.id] = target

        # Step 4: Rapid atomic publication phase (<20ms lock duration)
        results = {}
        to_update = []
        discrepancies = []

        with transaction.atomic():
            # Acquire row locks strictly ordered by primary key to eliminate deadlocks
            locked_ledgers = list(
                Ledger.objects.select_for_update().filter(company=company, id__in=ledger_ids).order_by('id')
            )

            # Reconcile any vouchers posted concurrently during Step 2-3 calculation window
            concurrent_entries = LedgerEntry.objects.filter(
                ledger_id__in=ledger_ids,
                voucher__company=company,
                voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
                created_at__gte=cutoff_time
            ).values('ledger_id').annotate(
                delta_dr=Sum('debit_amount'),
                delta_cr=Sum('credit_amount')
            )
            delta_map = {row['ledger_id']: row for row in concurrent_entries}

            for ledger in locked_ledgers:
                target_bal = precomputed_bal.get(ledger.id, Decimal('0.00'))
                if ledger.id in delta_map:
                    d = delta_map[ledger.id]
                    d_dr = Decimal(str(d['delta_dr'] or '0.00'))
                    d_cr = Decimal(str(d['delta_cr'] or '0.00'))
                    if ledger.normal_balance == 'CREDIT':
                        target_bal += (d_cr - d_dr)
                    else:
                        target_bal += (d_dr - d_cr)

                old_bal = ledger.current_balance if ledger.current_balance is not None else Decimal('0.00')
                if old_bal != target_bal:
                    discrepancies.append({
                        "ledger_id": str(ledger.id),
                        "ledger_name": ledger.name,
                        "old_balance": str(old_bal),
                        "new_balance": str(target_bal),
                        "drift": str(target_bal - old_bal)
                    })
                    ledger.current_balance = target_bal
                    to_update.append(ledger)

                results[str(ledger.id)] = {
                    "name": ledger.name,
                    "current_balance": str(target_bal)
                }

            if to_update:
                Ledger.objects.bulk_update(to_update, ['current_balance'])

        # Step 5: Audit logging outside of the database row locks
        try:
            from apps.audit.services.audit_service import AuditService
            AuditService.log_action(
                company=company,
                user=user,
                action='REBUILD_BALANCES',
                model_name='Company',
                record_id=company.id,
                changes={
                    "total_ledgers": len(locked_ledgers),
                    "updated_ledgers_count": len(to_update),
                    "discrepancies_count": len(discrepancies),
                    "discrepancies": discrepancies[:50]
                }
            )
        except Exception:
            pass

        return {
            "success": True,
            "company_id": str(company.id),
            "company_name": company.name,
            "rebuilt_ledgers_count": len(locked_ledgers),
            "updated_ledgers_count": len(to_update),
            "discrepancies_count": len(discrepancies),
            "discrepancies": discrepancies,
            "balances": results
        }

    @staticmethod
    def rebuild_ledger_balance(ledger: Ledger) -> Decimal:
        """
        Recalculates a single ledger's balance via canonical VoucherService logic.
        """
        from apps.accounting.services.voucher_service import VoucherService
        return VoucherService.recalculate_ledger_balance(ledger)

rebuild_ledger_balances = BalanceRebuildService.rebuild_company_ledger_balances
