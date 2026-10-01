from decimal import Decimal
import hashlib
from typing import Dict, Any, Optional

from .schema import CanonicalTransaction
from .operation import AccountingOperation, OperationType, OperationClass
from .semantic_delta import SemanticDelta

class CompensationEngine:
    """
    Evaluates semantic divergence (SemanticDelta) and generates deterministic, 
    mathematically balanced Accounting Operations and Cross-Enterprise Reciprocal Corrections.
    C = F(Delta, TransactionHistory, AccountingRules)
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
        Derives deterministic financial correction for a rejected line item on Buyer replica.
        """
        line = next((l for l in transaction.items if l.line_id == line_id), None)
        if not line:
            raise ValueError(f"Line {line_id} not found in Canonical Transaction.")
            
        if quantity_rejected <= Decimal('0') or quantity_rejected > line.quantity:
            raise ValueError("Invalid rejection quantity. Must be between 0 and original quantity.")

        ratio = quantity_rejected / line.quantity
        taxable_reduction = round(line.taxable_amount * ratio, 2)
        
        # Integrate Authoritative Vouch GST Engine
        try:
            from apps.gst.services.gst_calculator import GSTCalculator
            seller_state = transaction.source_entity.state_code or (transaction.source_entity.identity_value[:2] if len(transaction.source_entity.identity_value) >= 2 else "27")
            buyer_state = transaction.destination_entity.state_code or (transaction.destination_entity.identity_value[:2] if len(transaction.destination_entity.identity_value) >= 2 else "27")
            gst_res = GSTCalculator.calculate_taxes(
                company_state_code=seller_state,
                party_state_code=buyer_state,
                taxable_amount=taxable_reduction,
                gst_rate=line.tax_rate_percent
            )
            tax_reduction = gst_res['total_tax']
            cgst_reduction = gst_res['cgst']
            sgst_reduction = gst_res['sgst']
            igst_reduction = gst_res['igst']
        except Exception:
            tax_reduction = round(taxable_reduction * (line.tax_rate_percent / Decimal('100')), 2)
            cgst_reduction = Decimal('0.0')
            sgst_reduction = Decimal('0.0')
            igst_reduction = tax_reduction

        payload = {
            "line_id": line_id,
            "sku": line.sku,
            "quantity": float(quantity_rejected),
            "taxable_amount": float(taxable_reduction),
            "tax_amount": float(tax_reduction),
            "cgst_amount": float(cgst_reduction),
            "sgst_amount": float(sgst_reduction),
            "igst_amount": float(igst_reduction),
            "inventory_delta": float(-quantity_rejected) # Stock rejected / returned
        }

        # Deterministic operation ID ensures F(Delta) = F(Delta) regardless of discoverer
        seed = f"{transaction.transaction_id}|{line_id}|{float(quantity_rejected)}|ITEM_REJECTED|{parent_operation_id}"
        op_id = f"OP-COMP-{hashlib.sha256(seed.encode()).hexdigest()[:8].upper()}"

        return AccountingOperation(
            operation_id=op_id,
            transaction_id=transaction.transaction_id,
            replica_id=replica_id,
            operation_type=OperationType.ITEM_REJECTED,
            operation_class=OperationClass.COMPENSATING,
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
        
        # Authoritative GST Engine
        try:
            from apps.gst.services.gst_calculator import GSTCalculator
            seller_state = transaction.source_entity.state_code or (transaction.source_entity.identity_value[:2] if len(transaction.source_entity.identity_value) >= 2 else "27")
            buyer_state = transaction.destination_entity.state_code or (transaction.destination_entity.identity_value[:2] if len(transaction.destination_entity.identity_value) >= 2 else "27")
            gst_res = GSTCalculator.calculate_taxes(
                company_state_code=seller_state,
                party_state_code=buyer_state,
                taxable_amount=abs(taxable_delta),
                gst_rate=line.tax_rate_percent
            )
            sign = 1 if taxable_delta >= 0 else -1
            tax_delta = gst_res['total_tax'] * sign
            cgst_delta = gst_res['cgst'] * sign
            sgst_delta = gst_res['sgst'] * sign
            igst_delta = gst_res['igst'] * sign
        except Exception:
            tax_delta = round(taxable_delta * (line.tax_rate_percent / Decimal('100')), 2)
            cgst_delta = Decimal('0.0')
            sgst_delta = Decimal('0.0')
            igst_delta = tax_delta

        payload = {
            "line_id": line_id,
            "sku": line.sku,
            "old_unit_price": float(line.unit_price),
            "new_unit_price": float(new_unit_price),
            "taxable_amount": float(taxable_delta),
            "tax_amount": float(tax_delta),
            "cgst_amount": float(cgst_delta),
            "sgst_amount": float(sgst_delta),
            "igst_amount": float(igst_delta),
            "inventory_delta": 0.0
        }

        seed = f"{transaction.transaction_id}|{line_id}|{float(new_unit_price)}|PRICE_ADJUSTED|{parent_operation_id}"
        op_id = f"OP-COMP-{hashlib.sha256(seed.encode()).hexdigest()[:8].upper()}"

        return AccountingOperation(
            operation_id=op_id,
            transaction_id=transaction.transaction_id,
            replica_id=replica_id,
            operation_type=OperationType.PRICE_ADJUSTED,
            operation_class=OperationClass.COMPENSATING,
            payload=payload,
            logical_timestamp=logical_timestamp,
            parents=[parent_operation_id]
        )

    @staticmethod
    def generate_reciprocal_seller_credit_note(
        rejection_op: AccountingOperation,
        seller_replica_id: str,
        logical_timestamp: int
    ) -> AccountingOperation:
        """
        Generates reciprocal Credit Note operation for Seller when Buyer rejects goods.
        Maintains autonomous counterparty ledger without unilateral database mutation.
        """
        if rejection_op.operation_type != OperationType.ITEM_REJECTED:
            raise ValueError("Reciprocal credit note can only be derived from an ITEM_REJECTED operation.")

        payload = {
            "reference_rejection_op": rejection_op.operation_id,
            "line_id": rejection_op.payload.get("line_id"),
            "sku": rejection_op.payload.get("sku"),
            "quantity": rejection_op.payload.get("quantity"),
            "taxable_amount": rejection_op.payload.get("taxable_amount"),
            "tax_amount": rejection_op.payload.get("tax_amount"),
            "inventory_inward": rejection_op.payload.get("quantity"), # Goods returned back into seller inventory
            "note_type": "SALES_RETURN_CREDIT_NOTE"
        }

        seed = f"{rejection_op.transaction_id}|{rejection_op.operation_id}|RECIPROCAL_CREDIT_NOTE|{seller_replica_id}"
        op_id = f"OP-RECIP-{hashlib.sha256(seed.encode()).hexdigest()[:8].upper()}"

        return AccountingOperation(
            operation_id=op_id,
            transaction_id=rejection_op.transaction_id,
            replica_id=seller_replica_id,
            operation_type=OperationType.CREDIT_NOTE_ISSUED,
            operation_class=OperationClass.COMPENSATING,
            payload=payload,
            logical_timestamp=logical_timestamp,
            parents=[rejection_op.operation_id] # Strictly declares causal dependency on Buyer's rejection
        )

    @staticmethod
    def generate_reciprocal_price_adjustment_note(
        price_adj_op: AccountingOperation,
        seller_replica_id: str,
        logical_timestamp: int
    ) -> AccountingOperation:
        """
        Generates reciprocal Credit Note or Debit Note when a price adjustment is negotiated.
        Downwards adjustment -> Reciprocal Credit Note
        Upwards adjustment   -> Reciprocal Debit Note
        """
        if price_adj_op.operation_type != OperationType.PRICE_ADJUSTED:
            raise ValueError("Reciprocal adjustment note can only be derived from PRICE_ADJUSTED operation.")

        payload_taxable = Decimal(str(price_adj_op.payload.get('taxable_amount', 0)))
        payload_tax = Decimal(str(price_adj_op.payload.get('tax_amount', 0)))
        is_downward = (payload_taxable < Decimal('0'))

        op_type = OperationType.CREDIT_NOTE_ISSUED if is_downward else OperationType.DEBIT_NOTE_ISSUED
        note_type = "PRICE_REDUCTION_CREDIT_NOTE" if is_downward else "PRICE_INCREASE_DEBIT_NOTE"

        payload = {
            "reference_price_op": price_adj_op.operation_id,
            "line_id": price_adj_op.payload.get("line_id"),
            "sku": price_adj_op.payload.get("sku"),
            "taxable_amount": float(abs(payload_taxable)),
            "tax_amount": float(abs(payload_tax)),
            "cgst_amount": float(abs(Decimal(str(price_adj_op.payload.get('cgst_amount', 0))))),
            "sgst_amount": float(abs(Decimal(str(price_adj_op.payload.get('sgst_amount', 0))))),
            "igst_amount": float(abs(Decimal(str(price_adj_op.payload.get('igst_amount', 0))))),
            "note_type": note_type
        }

        seed = f"{price_adj_op.transaction_id}|{price_adj_op.operation_id}|RECIPROCAL_PRICE_NOTE|{seller_replica_id}"
        op_id = f"OP-RECIP-PRC-{hashlib.sha256(seed.encode()).hexdigest()[:8].upper()}"

        return AccountingOperation(
            operation_id=op_id,
            transaction_id=price_adj_op.transaction_id,
            replica_id=seller_replica_id,
            operation_type=op_type,
            operation_class=OperationClass.COMPENSATING,
            payload=payload,
            logical_timestamp=logical_timestamp,
            parents=[price_adj_op.operation_id]
        )
