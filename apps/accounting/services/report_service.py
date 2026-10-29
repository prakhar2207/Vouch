import logging
from django.db.models import Sum, Q
from decimal import Decimal
from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import LedgerEntry

logger = logging.getLogger(__name__)

class ReportService:
    @staticmethod
    def generate_trial_balance(
        company: Company,
        from_date=None,
        to_date=None,
        auto_reconcile: bool = True
    ) -> dict:
        """
        Generates the Trial Balance for a company by aggregating all posted ledger entries
        and opening balances, enforcing double-entry equilibrium from first principles.

        Dual-Verification Invariant:
        Dynamically calculates the true balance from posted LedgerEntry records and compares
        it against the stored Ledger.current_balance. If drift is detected, it logs an
        integrity alert and self-heals the cached balance.
        """
        ledgers = list(
            Ledger.objects.filter(company=company)
            .select_related('group')
            .order_by('group__nature', 'name')
        )

        # Batch 1: Identify which ledgers have posted OPENING vouchers
        ledgers_with_opening = set(
            LedgerEntry.objects.filter(
                voucher__company=company,
                voucher__status='POSTED',
                voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
            ).values_list('ledger_id', flat=True).distinct()
        )

        # Batch 2: Aggregate posted ledger entries
        # If date filters are provided, filter by voucher_date range
        entry_qs = LedgerEntry.objects.filter(
            voucher__company=company,
            voucher__status='POSTED'
        )
        if from_date:
            entry_qs = entry_qs.filter(voucher__voucher_date__gte=from_date)
        if to_date:
            entry_qs = entry_qs.filter(voucher__voucher_date__lte=to_date)

        entry_aggregates = {
            row['ledger_id']: (row['total_dr'] or Decimal('0.00'), row['total_cr'] or Decimal('0.00'))
            for row in entry_qs.values('ledger_id').annotate(
                total_dr=Sum('debit_amount'),
                total_cr=Sum('credit_amount')
            )
        }

        trial_balance = []
        discrepancies = []
        total_debit = Decimal('0.00')
        total_credit = Decimal('0.00')

        for ledger in ledgers:
            has_opening_voucher = ledger.id in ledgers_with_opening

            # Include opening balance if no opening voucher has been posted
            initial_net = Decimal('0.00')
            if not has_opening_voucher and ledger.opening_balance:
                if ledger.opening_balance_type == 'DEBIT':
                    initial_net = ledger.opening_balance
                else:
                    initial_net = -ledger.opening_balance

            posted_dr, posted_cr = entry_aggregates.get(ledger.id, (Decimal('0.00'), Decimal('0.00')))

            # Calculate mathematical balance based on ledger's normal balance type
            if ledger.normal_balance == 'DEBIT':
                calculated_balance = initial_net + (posted_dr - posted_cr)
            else:
                calculated_balance = (-initial_net) + (posted_cr - posted_dr)

            # Dual-verification against stored current_balance (only on full-period queries)
            if not from_date and not to_date:
                stored_bal = ledger.current_balance if ledger.current_balance is not None else Decimal('0.00')
                drift = abs(calculated_balance - stored_bal)
                if drift > Decimal('0.005'):
                    discrepancies.append({
                        "ledger_id": str(ledger.id),
                        "ledger_name": ledger.name,
                        "stored_balance": str(stored_bal),
                        "entry_calculated_balance": str(calculated_balance),
                        "variance": str(drift)
                    })
                    logger.warning(
                        f"[Trial Balance Integrity] Drift detected on ledger '{ledger.name}' ({ledger.id}): "
                        f"Stored={stored_bal}, Calculated={calculated_balance}, Diff={drift}"
                    )
                    if auto_reconcile:
                        ledger.current_balance = calculated_balance
                        ledger.save(update_fields=['current_balance'])

            # Determine presentation DR / CR
            dr_amount = Decimal('0.00')
            cr_amount = Decimal('0.00')

            if ledger.normal_balance == 'DEBIT':
                if calculated_balance > 0:
                    dr_amount = calculated_balance
                else:
                    cr_amount = abs(calculated_balance)
            else:
                if calculated_balance > 0:
                    cr_amount = calculated_balance
                else:
                    dr_amount = abs(calculated_balance)

            # Only include ledgers that have active status or non-zero balance
            if dr_amount > Decimal('0.00') or cr_amount > Decimal('0.00') or ledger.is_active:
                if dr_amount > Decimal('0.00') or cr_amount > Decimal('0.00'):
                    trial_balance.append({
                        "ledger_id": str(ledger.id),
                        "ledger_name": ledger.name,
                        "group_name": ledger.group.name if ledger.group else "Unassigned",
                        "nature": ledger.group.nature if ledger.group else "ASSET",
                        "debit": dr_amount,
                        "credit": cr_amount
                    })
                    total_debit += dr_amount
                    total_credit += cr_amount

        diff = abs(total_debit - total_credit)

        return {
            "company_name": company.name,
            "ledgers": trial_balance,
            "totals": {
                "total_debit": total_debit,
                "total_credit": total_credit,
                "difference": diff,
                "is_balanced": total_debit == total_credit
            },
            "integrity_audit": {
                "source": "POSTED_LEDGER_ENTRIES_AGGREGATION",
                "ledgers_evaluated": len(ledgers),
                "discrepancies_detected": len(discrepancies),
                "mismatches": discrepancies
            }
        }
