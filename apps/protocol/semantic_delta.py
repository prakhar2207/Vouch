from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Any, Optional
import time
import hashlib

@dataclass(frozen=True)
class SemanticDelta:
    """
    Formal representation of accounting divergence between two enterprise replicas.
    Captures economic and tax differences rather than raw database field mutations.
    """
    delta_id: str
    transaction_id: str
    source_replica: str
    target_replica: str
    delta_quantity: Decimal
    delta_taxable: Decimal
    delta_tax: Decimal
    delta_cgst: Decimal
    delta_sgst: Decimal
    delta_igst: Decimal
    delta_grand_total: Decimal
    delta_receivable: Decimal
    delta_stock: Decimal
    line_deltas: List[Dict[str, Any]] = field(default_factory=list)
    cause: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def has_divergence(self) -> bool:
        """Returns True if there is any material financial or stock discrepancy."""
        return (
            abs(self.delta_quantity) > Decimal('0.001') or
            abs(self.delta_taxable) > Decimal('0.01') or
            abs(self.delta_tax) > Decimal('0.01') or
            abs(self.delta_grand_total) > Decimal('0.01') or
            abs(self.delta_stock) > Decimal('0.001')
        )

    def summary(self) -> str:
        return (
            f"[SemanticDelta {self.delta_id}] Delta_Qty: {self.delta_quantity}, "
            f"Delta_Taxable: INR {self.delta_taxable}, Delta_Tax: INR {self.delta_tax}, "
            f"Delta_Total: INR {self.delta_grand_total} | Cause: {self.cause}"
        )


class SemanticDeltaEngine:
    """
    Analyzes evaluated states from two replicas and calculates the 
    formal economic divergence (SemanticDelta).
    """

    @staticmethod
    def compute_state_delta(
        transaction_id: str,
        state_a: Dict[str, Any],
        state_b: Dict[str, Any],
        replica_a_id: str = "REPLICA_A",
        replica_b_id: str = "REPLICA_B",
        cause: str = "State comparison divergence"
    ) -> SemanticDelta:
        """
        Computes Delta = State_B - State_A
        """
        d_qty = Decimal(str(state_b.get('total_quantity', 0))) - Decimal(str(state_a.get('total_quantity', 0)))
        d_taxable = Decimal(str(state_b.get('taxable_amount', 0))) - Decimal(str(state_a.get('taxable_amount', 0)))
        d_tax = Decimal(str(state_b.get('total_tax', 0))) - Decimal(str(state_a.get('total_tax', 0)))
        d_cgst = Decimal(str(state_b.get('cgst', 0))) - Decimal(str(state_a.get('cgst', 0)))
        d_sgst = Decimal(str(state_b.get('sgst', 0))) - Decimal(str(state_a.get('sgst', 0)))
        d_igst = Decimal(str(state_b.get('igst', 0))) - Decimal(str(state_a.get('igst', 0)))
        d_total = Decimal(str(state_b.get('grand_total', 0))) - Decimal(str(state_a.get('grand_total', 0)))

        # Accounts Receivable difference from ledgers
        ar_a = Decimal(str(state_a.get('ledgers', {}).get('AccountsReceivable', {}).get('debit', 0))) - \
               Decimal(str(state_a.get('ledgers', {}).get('AccountsReceivable', {}).get('credit', 0)))
        ar_b = Decimal(str(state_b.get('ledgers', {}).get('AccountsReceivable', {}).get('debit', 0))) - \
               Decimal(str(state_b.get('ledgers', {}).get('AccountsReceivable', {}).get('credit', 0)))
        d_ar = ar_b - ar_a

        # Stock / Inventory difference
        stock_a = Decimal(str(state_a.get('inventory_stock', 0)))
        stock_b = Decimal(str(state_b.get('inventory_stock', 0)))
        d_stock = stock_b - stock_a

        seed = f"{transaction_id}|{replica_a_id}|{replica_b_id}|{d_total}|{d_qty}"
        delta_id = f"DELTA-{hashlib.sha256(seed.encode()).hexdigest()[:8].upper()}"

        return SemanticDelta(
            delta_id=delta_id,
            transaction_id=transaction_id,
            source_replica=replica_a_id,
            target_replica=replica_b_id,
            delta_quantity=d_qty,
            delta_taxable=d_taxable,
            delta_tax=d_tax,
            delta_cgst=d_cgst,
            delta_sgst=d_sgst,
            delta_igst=d_igst,
            delta_grand_total=d_total,
            delta_receivable=d_ar,
            delta_stock=d_stock,
            cause=cause
        )
