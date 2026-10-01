from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
from decimal import Decimal

class ProtocolException(Exception):
    pass

class InvariantViolation(ProtocolException):
    pass

@dataclass(frozen=True)
class ProtocolEntity:
    identity_type: str  # e.g., 'GSTIN', 'PAN'
    identity_value: str
    name: str
    state_code: Optional[str] = None

@dataclass(frozen=True)
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
        if abs(self.taxable_amount - expected_taxable) > Decimal('0.01'):
            raise InvariantViolation(f"Line {self.line_id} taxable amount mismatch. Expected {expected_taxable}, got {self.taxable_amount}")

@dataclass(frozen=True)
class TaxSummary:
    cgst_amount: Decimal = Decimal('0.0')
    sgst_amount: Decimal = Decimal('0.0')
    igst_amount: Decimal = Decimal('0.0')
    cess_amount: Decimal = Decimal('0.0')

    @property
    def total_tax(self) -> Decimal:
        return self.cgst_amount + self.sgst_amount + self.igst_amount + self.cess_amount

@dataclass(frozen=True)
class TransactionTotals:
    subtotal: Decimal
    total_tax: Decimal
    shipping_charges: Decimal = Decimal('0.0')
    total_discount: Decimal = Decimal('0.0')
    grand_total: Decimal = Decimal('0.0')

@dataclass(frozen=True)
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

    def __post_init__(self):
        if isinstance(self.items, list):
            object.__setattr__(self, 'items', tuple(self.items))
        if isinstance(self.causal_dependencies, list):
            object.__setattr__(self, 'causal_dependencies', tuple(self.causal_dependencies))
        if isinstance(self.references, list):
            object.__setattr__(self, 'references', tuple(self.references))

    def validate_invariants(self):
        """Enforces deterministic accounting invariants on the canonical payload."""
        # 1. Line Level Integrity
        calc_subtotal = Decimal('0.0')
        for item in self.items:
            item.validate()
            calc_subtotal += item.taxable_amount
            
        # 2. Subtotal Integrity
        if abs(self.totals.subtotal - calc_subtotal) > Decimal('0.01'):
            raise InvariantViolation(f"Subtotal mismatch. Lines sum to {calc_subtotal}, header claims {self.totals.subtotal}")

        # 3. Tax Integrity
        if abs(self.totals.total_tax - self.tax_summary.total_tax) > Decimal('0.01'):
            raise InvariantViolation("Tax summary sum does not match header total_tax")

        # 4. Grand Total Integrity
        expected_grand_total = self.totals.subtotal + self.totals.total_tax + self.totals.shipping_charges - self.totals.total_discount
        if abs(self.totals.grand_total - expected_grand_total) > Decimal('0.01'):
            raise InvariantViolation(f"Grand total invariant violated. Expected {expected_grand_total}, got {self.totals.grand_total}")
        
        # 5. Causality Checks
        if self.transaction_type in ['CREDIT_NOTE', 'DEBIT_NOTE'] and not self.causal_dependencies:
            raise InvariantViolation(f"{self.transaction_type} must declare causal dependencies on the parent transaction.")

    def to_dict(self) -> Dict[str, Any]:
        """Serializes CanonicalTransaction into canonical JSON-serializable dictionary."""
        return {
            "protocol_version": self.protocol_version,
            "transaction_id": self.transaction_id,
            "transaction_type": self.transaction_type,
            "state_version": self.state_version,
            "issued_at": self.issued_at.isoformat() if hasattr(self.issued_at, 'isoformat') else str(self.issued_at),
            "source_entity": {
                "type": self.source_entity.identity_type,
                "value": self.source_entity.identity_value,
                "name": self.source_entity.name,
                "state_code": self.source_entity.state_code
            },
            "destination_entity": {
                "type": self.destination_entity.identity_type,
                "value": self.destination_entity.identity_value,
                "name": self.destination_entity.name,
                "state_code": self.destination_entity.state_code
            },
            "items": [
                {
                    "line_id": line.line_id,
                    "sku": line.sku,
                    "name": line.name,
                    "hsn_code": line.hsn_code,
                    "quantity": str(line.quantity),
                    "unit": line.unit,
                    "unit_price": str(line.unit_price),
                    "discount_amount": str(line.discount_amount),
                    "taxable_amount": str(line.taxable_amount),
                    "tax_rate_percent": str(line.tax_rate_percent)
                }
                for line in self.items
            ],
            "tax_summary": {
                "cgst": str(self.tax_summary.cgst_amount),
                "sgst": str(self.tax_summary.sgst_amount),
                "igst": str(self.tax_summary.igst_amount),
                "cess": str(self.tax_summary.cess_amount),
                "total_tax": str(self.tax_summary.total_tax)
            },
            "totals": {
                "subtotal": str(self.totals.subtotal),
                "total_tax": str(self.totals.total_tax),
                "shipping": str(self.totals.shipping_charges),
                "discount": str(self.totals.total_discount),
                "grand_total": str(self.totals.grand_total)
            },
            "causal_dependencies": list(self.causal_dependencies)
        }

    @property
    def canonical_hash(self) -> str:
        """
        Computes deterministic SHA-256 digest over normalized canonical fields.
        Guarantees that both parties compute the exact same identity hash.
        """
        import hashlib, json
        canonical_json = json.dumps(self.to_dict(), sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

