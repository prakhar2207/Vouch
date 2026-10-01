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

def to_dec_str(val: Any, decimals: int = 2) -> str:
    """Normalizes any number/Decimal/string to a deterministic fixed-point string representation."""
    if val is None or val == "":
        return f"{0:.{decimals}f}"
    try:
        d = Decimal(str(val))
        return f"{d:.{decimals}f}"
    except Exception:
        return f"{0:.{decimals}f}"


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
                    "quantity": to_dec_str(line.quantity),
                    "unit": line.unit,
                    "unit_price": to_dec_str(line.unit_price),
                    "discount_amount": to_dec_str(line.discount_amount),
                    "taxable_amount": to_dec_str(line.taxable_amount),
                    "tax_rate_percent": to_dec_str(line.tax_rate_percent)
                }
                for line in self.items
            ],
            "tax_summary": {
                "cgst": to_dec_str(self.tax_summary.cgst_amount),
                "sgst": to_dec_str(self.tax_summary.sgst_amount),
                "igst": to_dec_str(self.tax_summary.igst_amount),
                "cess": to_dec_str(self.tax_summary.cess_amount),
                "total_tax": to_dec_str(self.tax_summary.total_tax)
            },
            "totals": {
                "subtotal": to_dec_str(self.totals.subtotal),
                "total_tax": to_dec_str(self.totals.total_tax),
                "shipping": to_dec_str(self.totals.shipping_charges),
                "discount": to_dec_str(self.totals.total_discount),
                "grand_total": to_dec_str(self.totals.grand_total)
            },
            "causal_dependencies": list(self.causal_dependencies)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CanonicalTransaction':
        """Reconstructs and normalizes a CanonicalTransaction from a dictionary payload."""
        from .canonical_json import canonical_json_dumps
        
        src = data.get("source_entity", {})
        source_entity = ProtocolEntity(
            identity_type=src.get("type") or src.get("identity_type", "GSTIN"),
            identity_value=str(src.get("value") or src.get("identity_value", "")),
            name=str(src.get("name", "")),
            state_code=src.get("state_code")
        )

        dst = data.get("destination_entity", {})
        destination_entity = ProtocolEntity(
            identity_type=dst.get("type") or dst.get("identity_type", "GSTIN"),
            identity_value=str(dst.get("value") or dst.get("identity_value", "")),
            name=str(dst.get("name", "")),
            state_code=dst.get("state_code")
        )

        items = [
            TransactionLine(
                line_id=str(item.get("line_id", f"L{idx+1}")),
                sku=str(item.get("sku", "")),
                name=str(item.get("name", "")),
                hsn_code=str(item.get("hsn_code", "")),
                quantity=Decimal(str(item.get("quantity", "0.0"))),
                unit=str(item.get("unit", "PCS")),
                unit_price=Decimal(str(item.get("unit_price", "0.0"))),
                discount_amount=Decimal(str(item.get("discount_amount", "0.0"))),
                taxable_amount=Decimal(str(item.get("taxable_amount", "0.0"))),
                tax_rate_percent=Decimal(str(item.get("tax_rate_percent", "0.0")))
            )
            for idx, item in enumerate(data.get("items", []))
        ]

        ts = data.get("tax_summary", {})
        tax_summary = TaxSummary(
            cgst_amount=Decimal(str(ts.get("cgst", ts.get("cgst_amount", "0.0")))),
            sgst_amount=Decimal(str(ts.get("sgst", ts.get("sgst_amount", "0.0")))),
            igst_amount=Decimal(str(ts.get("igst", ts.get("igst_amount", "0.0")))),
            cess_amount=Decimal(str(ts.get("cess", ts.get("cess_amount", "0.0"))))
        )

        tot = data.get("totals", {})
        totals = TransactionTotals(
            subtotal=Decimal(str(tot.get("subtotal", "0.0"))),
            total_tax=Decimal(str(tot.get("total_tax", "0.0"))),
            shipping_charges=Decimal(str(tot.get("shipping", tot.get("shipping_charges", "0.0")))),
            total_discount=Decimal(str(tot.get("discount", tot.get("total_discount", "0.0")))),
            grand_total=Decimal(str(tot.get("grand_total", "0.0")))
        )

        issued_at_raw = data.get("issued_at")
        if isinstance(issued_at_raw, str):
            try:
                issued_at = datetime.fromisoformat(issued_at_raw)
            except Exception:
                issued_at = datetime.now()
        elif isinstance(issued_at_raw, datetime):
            issued_at = issued_at_raw
        else:
            issued_at = datetime.now()

        tx = cls(
            protocol_version=str(data.get("protocol_version", "1.0")),
            transaction_id=str(data.get("transaction_id", "")),
            transaction_type=str(data.get("transaction_type", "SALE")),
            state_version=int(data.get("state_version", 1)),
            issued_at=issued_at,
            source_entity=source_entity,
            destination_entity=destination_entity,
            items=items,
            tax_summary=tax_summary,
            totals=totals,
            causal_dependencies=data.get("causal_dependencies", [])
        )
        return tx

    @property
    def canonical_hash(self) -> str:
        """
        Computes deterministic SHA-256 digest over normalized canonical fields.
        Guarantees that both parties compute the exact same identity hash.
        """
        import hashlib
        from .canonical_json import canonical_json_dumps
        canonical_json = canonical_json_dumps(self.to_dict())
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

