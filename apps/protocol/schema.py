from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
from decimal import Decimal

class ProtocolException(Exception):
    pass

class InvariantViolation(ProtocolException):
    pass

@dataclass
class ProtocolEntity:
    identity_type: str  # e.g., 'GSTIN', 'PAN'
    identity_value: str
    name: str
    state_code: Optional[str] = None

@dataclass
class TransactionLine:
    line_id: str
    sku: str
    name: str
    hsn_code: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    tax_rate_percent: Decimal

    def validate(self):
        expected_taxable = (self.quantity * self.unit_price) - self.discount_amount
        if abs(self.taxable_amount - expected_taxable) > Decimal('0.05'):
            raise InvariantViolation(f"Line {self.line_id} taxable amount mismatch. Expected {expected_taxable}, got {self.taxable_amount}")

@dataclass
class TaxSummary:
    cgst_amount: Decimal = Decimal('0.0')
    sgst_amount: Decimal = Decimal('0.0')
    igst_amount: Decimal = Decimal('0.0')
    cess_amount: Decimal = Decimal('0.0')

    @property
    def total_tax(self) -> Decimal:
        return self.cgst_amount + self.sgst_amount + self.igst_amount + self.cess_amount

@dataclass
class TransactionTotals:
    subtotal: Decimal
    total_tax: Decimal
    shipping_charges: Decimal = Decimal('0.0')
    total_discount: Decimal = Decimal('0.0')
    grand_total: Decimal = Decimal('0.0')

@dataclass
class CanonicalTransaction:
    protocol_version: str
    transaction_id: str
    transaction_type: str  # SALE, PURCHASE, DEBIT_NOTE, CREDIT_NOTE
    state_version: int
    issued_at: datetime
    
    source_entity: ProtocolEntity
    destination_entity: ProtocolEntity
    
    items: List[TransactionLine]
    tax_summary: TaxSummary
    totals: TransactionTotals
    
    causal_dependencies: List[str] = field(default_factory=list)
    references: List[Dict[str, str]] = field(default_factory=list)
    expires_at: Optional[datetime] = None

    def validate_invariants(self):
        """Enforces deterministic accounting invariants on the canonical payload."""
        # 1. Line Level Integrity
        calc_subtotal = Decimal('0.0')
        for item in self.items:
            item.validate()
            calc_subtotal += item.taxable_amount
            
        # 2. Subtotal Integrity
        if abs(self.totals.subtotal - calc_subtotal) > Decimal('0.05'):
            raise InvariantViolation(f"Subtotal mismatch. Lines sum to {calc_subtotal}, header claims {self.totals.subtotal}")

        # 3. Tax Integrity
        if abs(self.totals.total_tax - self.tax_summary.total_tax) > Decimal('0.05'):
            raise InvariantViolation("Tax summary sum does not match header total_tax")

        # 4. Grand Total Integrity
        expected_grand_total = self.totals.subtotal + self.totals.total_tax + self.totals.shipping_charges - self.totals.total_discount
        if abs(self.totals.grand_total - expected_grand_total) > Decimal('0.05'):
            raise InvariantViolation(f"Grand total invariant violated. Expected {expected_grand_total}, got {self.totals.grand_total}")
        
        # 5. Causality Checks
        if self.transaction_type in ['CREDIT_NOTE', 'DEBIT_NOTE'] and not self.causal_dependencies:
            raise InvariantViolation(f"{self.transaction_type} must declare causal dependencies on the parent transaction.")
