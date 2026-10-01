from decimal import Decimal
from typing import Dict, Any, Optional

class AccountingInvariantViolation(Exception):
    """Raised when a converged CRDT state violates fundamental accounting rules."""
    pass

class InvariantEngine:
    """
    Deterministic mathematical gatekeeper.
    Evaluates the resulting state of a CRDT merge before it can be committed.
    Proves double-entry balancing, tax component decomposition, inventory conservation,
    and payment allocation constraints.
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
        grand_total: Decimal,
        round_off: Decimal = Decimal('0.0')
    ) -> bool:
        """Enforces GrandTotal = TaxableAmount + TotalTax + Charges - Discount + RoundOff"""
        expected_total = taxable + tax + charges - discount + round_off
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
    def validate_inventory_conservation(
        opening_stock: Decimal,
        inbound: Decimal,
        outbound: Decimal,
        adjustments: Decimal,
        closing_stock: Decimal
    ) -> bool:
        """Enforces ClosingStock = OpeningStock + Inbound - Outbound + Adjustments"""
        expected = opening_stock + inbound - outbound + adjustments
        if abs(expected - closing_stock) > Decimal('0.001'):
            raise AccountingInvariantViolation(
                f"Inventory conservation violation: Expected {expected}, got {closing_stock}"
            )
        return True

    @staticmethod
    def validate_payment_allocation(allocated_amount: Decimal, outstanding_amount: Decimal) -> bool:
        """Enforces AllocatedAmount <= ApplicableOutstandingAmount"""
        if allocated_amount > outstanding_amount + Decimal('0.01'):
            raise AccountingInvariantViolation(
                f"Payment over-allocation: Allocated ({allocated_amount}) exceeds outstanding ({outstanding_amount})"
            )
        return True

    @staticmethod
    def evaluate_converged_state(state: Dict[str, Any]) -> bool:
        """
        Main entry point. Takes a snapshot of a transaction's financial state 
        (post-CRDT merge) and executes all invariant proofs.
        """
        # 1. Double-Entry Invariant
        InvariantEngine.validate_double_entry(state.get('ledgers', {}))
        
        # 2. Invoice Algebra Invariant
        InvariantEngine.validate_invoice_totals(
            taxable=Decimal(str(state.get('taxable_amount', 0))),
            tax=Decimal(str(state.get('total_tax', 0))),
            charges=Decimal(str(state.get('total_charges', 0))),
            discount=Decimal(str(state.get('total_discount', 0))),
            grand_total=Decimal(str(state.get('grand_total', 0))),
            round_off=Decimal(str(state.get('round_off', 0)))
        )
        
        # 3. Tax Components Invariant
        InvariantEngine.validate_tax_components(
            total_tax=Decimal(str(state.get('total_tax', 0))),
            cgst=Decimal(str(state.get('cgst', 0))),
            sgst=Decimal(str(state.get('sgst', 0))),
            igst=Decimal(str(state.get('igst', 0)))
        )

        # 4. Inventory Conservation (if tracked in state)
        if 'inventory' in state and isinstance(state['inventory'], dict):
            inv = state['inventory']
            InvariantEngine.validate_inventory_conservation(
                opening_stock=Decimal(str(inv.get('opening', 0))),
                inbound=Decimal(str(inv.get('inbound', 0))),
                outbound=Decimal(str(inv.get('outbound', 0))),
                adjustments=Decimal(str(inv.get('adjustments', 0))),
                closing_stock=Decimal(str(inv.get('closing', 0)))
            )

        # 5. Payment Allocation constraint (if payments exist)
        if 'allocated_payment' in state and 'invoice_grand_total' in state:
            InvariantEngine.validate_payment_allocation(
                allocated_amount=Decimal(str(state.get('allocated_payment', 0))),
                outstanding_amount=Decimal(str(state.get('invoice_grand_total', 0)))
            )
        
        return True
