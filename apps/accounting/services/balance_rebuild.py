from decimal import Decimal
from django.db import transaction
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.services.voucher_service import VoucherService

class BalanceRebuildService:
    @staticmethod
    @transaction.atomic
    def rebuild_company_ledger_balances(company: Company) -> dict:
        """
        Reconstructs every ledger's current_balance from scratch by evaluating
        its opening balance and aggregating all immutable POSTED ledger entries.
        Eliminates any data drift.
        """
        ledgers = Ledger.objects.filter(company=company)
        rebuilt_count = 0
        results = {}

        for ledger in ledgers:
            new_balance = VoucherService.recalculate_ledger_balance(ledger)
            rebuilt_count += 1
            results[str(ledger.id)] = {
                "name": ledger.name,
                "current_balance": str(new_balance)
            }

        return {
            "success": True,
            "company_id": str(company.id),
            "company_name": company.name,
            "rebuilt_ledgers_count": rebuilt_count,
            "balances": results
        }
