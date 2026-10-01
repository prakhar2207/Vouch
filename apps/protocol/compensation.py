from decimal import Decimal
import hashlib

from .schema import CanonicalTransaction
from .operation import AccountingOperation, OperationType

class CompensationEngine:
    """
    Evaluates semantic divergence (Deltas) and generates deterministic, 
    mathematically balanced Accounting Operations.
    """

    @staticmethod
    def generate_item_rejection(
        transaction: CanonicalTransaction,
        line_id: str,
        quantity_rejected: Decimal,
        replica_id: str,
        logical_timestamp: int,
        parent_operation_id: str
    ) -> AccountingOperation:
        """
        Derives the deterministic financial correction for a rejected line item.
        C = F(Delta, TransactionHistory, AccountingRules)
        """
        # 1. Locate Historical Context
        line = next((l for l in transaction.items if l.line_id == line_id), None)
        if not line:
            raise ValueError(f"Line {line_id} not found in Canonical Transaction.")
            
        if quantity_rejected <= Decimal('0') or quantity_rejected > line.quantity:
            raise ValueError("Invalid rejection quantity. Must be between 0 and original quantity.")

        # 2. Calculate Deterministic Semantic Delta (Proportional)
        ratio = quantity_rejected / line.quantity
        
        # Rounding strictly to 2 decimal places as per currency standard
        taxable_reduction = round(line.taxable_amount * ratio, 2)
        
        # In a real system, this queries the GST engine. For POC, proportional math is used.
        tax_reduction = round(taxable_reduction * (line.tax_rate_percent / Decimal('100')), 2)

        # 3. Construct Balanced Payload
        # The payload explicitly defines the delta so the CRDT merge engine can apply it deterministically.
        payload = {
            "line_id": line_id,
            "sku": line.sku,
            "quantity": float(quantity_rejected),
            "taxable_amount": float(taxable_reduction),
            "tax_amount": float(tax_reduction)
        }

        # 4. Generate Deterministic Operation ID
        # CRITICAL: Both replicas must derive the exact same ID for the same semantic delta.
        # F(Delta) = F(Delta) regardless of which replica discovers the discrepancy first.
        deterministic_seed = f"{transaction.transaction_id}|{line_id}|{float(quantity_rejected)}|ITEM_REJECTED|{parent_operation_id}"
        deterministic_id = f"OP-COMP-{hashlib.sha256(deterministic_seed.encode()).hexdigest()[:8].upper()}"

        return AccountingOperation(
            operation_id=deterministic_id,
            transaction_id=transaction.transaction_id,
            replica_id=replica_id,
            operation_type=OperationType.ITEM_REJECTED,
            payload=payload,
            logical_timestamp=logical_timestamp,
            parents=[parent_operation_id]
        )

    @staticmethod
    def generate_price_adjustment(
        transaction: CanonicalTransaction,
        line_id: str,
        new_unit_price: Decimal,
        replica_id: str,
        logical_timestamp: int,
        parent_operation_id: str
    ) -> AccountingOperation:
        """
        Derives deterministic financial correction for an item price adjustment.
        """
        line = next((l for l in transaction.items if l.line_id == line_id), None)
        if not line:
            raise ValueError(f"Line {line_id} not found in Canonical Transaction.")
            
        unit_price_diff = new_unit_price - line.unit_price
        taxable_delta = round(unit_price_diff * line.quantity, 2)
        tax_delta = round(taxable_delta * (line.tax_rate_percent / Decimal('100')), 2)

        payload = {
            "line_id": line_id,
            "sku": line.sku,
            "old_unit_price": float(line.unit_price),
            "new_unit_price": float(new_unit_price),
            "taxable_amount": float(taxable_delta),
            "tax_amount": float(tax_delta)
        }

        deterministic_seed = f"{transaction.transaction_id}|{line_id}|{float(new_unit_price)}|PRICE_ADJUSTED|{parent_operation_id}"
        deterministic_id = f"OP-COMP-{hashlib.sha256(deterministic_seed.encode()).hexdigest()[:8].upper()}"

        return AccountingOperation(
            operation_id=deterministic_id,
            transaction_id=transaction.transaction_id,
            replica_id=replica_id,
            operation_type=OperationType.PRICE_ADJUSTED,
            payload=payload,
            logical_timestamp=logical_timestamp,
            parents=[parent_operation_id]
        )
