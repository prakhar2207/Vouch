from decimal import Decimal
from typing import Dict, Any

class AccountingInvariantViolation(Exception):
    """Raised when a converged CRDT state violates fundamental accounting rules."""
    pass

class InvariantEngine:
    """
    Deterministic mathematical gatekeeper.
    Evaluates the resulting state of a CRDT merge before it can be committed.
    """

    @staticmethod
    def validate_double_entry(ledgers: Dict[str, Dict[str, Decimal]]) -> bool:
        """
        Enforces SUM(Debits) == SUM(Credits)
        Format: {'AccountsReceivable': {'debit': Decimal('100'), 'credit': Decimal('0')}, ...}
        """
        total_debit = Decimal('0.0')
        total_credit = Decimal('0.0')
        
        for account, balances in ledgers.items():
            total_debit += balances.get('debit', Decimal('0.0'))
            total_credit += balances.get('credit', Decimal('0.0'))
            
        if abs(total_debit - total_credit) > Decimal('0.01'):
            raise AccountingInvariantViolation(
                f"Double-entry violation: Total Debits ({total_debit}) != Total Credits ({total_credit})"
            )
        return True

    @staticmethod
    def validate_invoice_totals(
        taxable: Decimal, 
        tax: Decimal, 
        charges: Decimal, 
        discount: Decimal, 
        grand_total: Decimal
    ) -> bool:
        """Enforces GrandTotal = TaxableAmount + TotalTax + Charges - Discount"""
        expected_total = taxable + tax + charges - discount
        if abs(expected_total - grand_total) > Decimal('0.01'):
            raise AccountingInvariantViolation(
                f"Invoice total violation: Algebra yields {expected_total}, but header claims {grand_total}"
            )
        return True

    @staticmethod
    def validate_tax_components(total_tax: Decimal, cgst: Decimal, sgst: Decimal, igst: Decimal) -> bool:
        """Enforces TotalTax = CGST + SGST + IGST"""
        component_sum = cgst + sgst + igst
        if abs(component_sum - total_tax) > Decimal('0.01'):
            raise AccountingInvariantViolation(
                f"Tax breakdown violation: Components sum to {component_sum} != Total Tax {total_tax}"
            )
        return True

    @staticmethod
    def evaluate_converged_state(state: Dict[str, Any]) -> bool:
        """
        Main entry point. Takes a snapshot of a transaction's financial state 
        (post-CRDT merge) and executes all invariant proofs.
        """
        InvariantEngine.validate_double_entry(state.get('ledgers', {}))
        
        InvariantEngine.validate_invoice_totals(
            taxable=state.get('taxable_amount', Decimal('0.0')),
            tax=state.get('total_tax', Decimal('0.0')),
            charges=state.get('total_charges', Decimal('0.0')),
            discount=state.get('total_discount', Decimal('0.0')),
            grand_total=state.get('grand_total', Decimal('0.0'))
        )
        
        InvariantEngine.validate_tax_components(
            total_tax=state.get('total_tax', Decimal('0.0')),
            cgst=state.get('cgst', Decimal('0.0')),
            sgst=state.get('sgst', Decimal('0.0')),
            igst=state.get('igst', Decimal('0.0'))
        )
        
        return True
