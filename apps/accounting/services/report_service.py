from django.db.models import Sum
from decimal import Decimal
from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup

class ReportService:
    @staticmethod
    def generate_trial_balance(company: Company) -> dict:
        """
        Generates the Trial Balance for a company by summing all ledger balances.
        Returns a strict dictionary proving Total Debit == Total Credit.
        """
        ledgers = Ledger.objects.filter(company=company, is_active=True).select_related('group')
        
        trial_balance = []
        total_debit = Decimal('0.00')
        total_credit = Decimal('0.00')
        
        for ledger in ledgers:
            # Determine if current balance is a Debit or Credit
            # If opening_balance_type is DEBIT: Positive current_balance means Debit, Negative means Credit
            # If opening_balance_type is CREDIT: Positive current_balance means Credit, Negative means Debit
            
            dr_amount = Decimal('0.00')
            cr_amount = Decimal('0.00')
            
            if ledger.opening_balance_type == 'DEBIT':
                if ledger.current_balance > 0:
                    dr_amount = ledger.current_balance
                else:
                    cr_amount = abs(ledger.current_balance)
            else:
                if ledger.current_balance > 0:
                    cr_amount = ledger.current_balance
                else:
                    dr_amount = abs(ledger.current_balance)
                    
            if dr_amount > 0 or cr_amount > 0:
                trial_balance.append({
                    "ledger_name": ledger.name,
                    "group_name": ledger.group.name,
                    "nature": ledger.group.nature,
                    "debit": dr_amount,
                    "credit": cr_amount
                })
                
                total_debit += dr_amount
                total_credit += cr_amount
                
        return {
            "company_name": company.name,
            "ledgers": trial_balance,
            "totals": {
                "total_debit": total_debit,
                "total_credit": total_credit,
                "is_balanced": total_debit == total_credit
            }
        }
