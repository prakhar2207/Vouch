import hashlib
from typing import Dict, List, Any
from decimal import Decimal
from .operation import AccountingOperation, OperationType
from .invariants import InvariantEngine

class DE_CRDT:
    """
    Double-Entry Conflict-Free Replicated Data Type.
    Merges offline accounting operations and projects them into verifiable states.
    """
    def __init__(self, replica_id: str):
        self.replica_id = replica_id
        self.operations: Dict[str, AccountingOperation] = {}
        
    def apply_operation(self, op: AccountingOperation):
        """Idempotently adds an operation to the local graph."""
        if op.operation_id not in self.operations:
            self.operations[op.operation_id] = op

    def merge(self, other: 'DE_CRDT') -> 'DE_CRDT':
        """
        Mathematical merge of two replicas.
        Guarantees Commutativity: Merge(A, B) == Merge(B, A)
        """
        merged = DE_CRDT(f"MERGED_{self.replica_id}_{other.replica_id}")
        for op in self.operations.values():
            merged.apply_operation(op)
        for op in other.operations.values():
            merged.apply_operation(op)
        return merged

    def _causal_sort(self) -> List[AccountingOperation]:
        """
        Sorts operations topologically.
        (Simplified to logical_timestamp for Phase 4)
        """
        return sorted(self.operations.values(), key=lambda x: x.logical_timestamp)

    def evaluate_state(self) -> Dict[str, Any]:
        """
        Projects the operation graph into a double-entry accounting state.
        This calculates the final effect of all compensating operations.
        """
        ops = self._causal_sort()
        
        state = {
            'ledgers': {
                'AccountsReceivable': {'debit': Decimal('0.0'), 'credit': Decimal('0.0')},
                'SalesAccount': {'debit': Decimal('0.0'), 'credit': Decimal('0.0')},
                'TaxAccount': {'debit': Decimal('0.0'), 'credit': Decimal('0.0')}
            },
            'taxable_amount': Decimal('0.0'),
            'total_tax': Decimal('0.0'),
            'total_charges': Decimal('0.0'),
            'total_discount': Decimal('0.0'),
            'grand_total': Decimal('0.0'),
            'cgst': Decimal('0.0'),
            'sgst': Decimal('0.0'),
            'igst': Decimal('0.0')
        }

        for op in ops:
            payload = op.payload
            
            if op.operation_type == OperationType.TRANSACTION_ISSUED:
                gt = Decimal(str(payload.get('grand_total', 0)))
                tax = Decimal(str(payload.get('total_tax', 0)))
                taxable = Decimal(str(payload.get('taxable_amount', 0)))
                
                state['grand_total'] += gt
                state['total_tax'] += tax
                state['igst'] += tax  # Simplified to IGST for POC
                state['taxable_amount'] += taxable
                
                # Base Invoice Ledgers
                state['ledgers']['AccountsReceivable']['debit'] += gt
                state['ledgers']['SalesAccount']['credit'] += taxable
                state['ledgers']['TaxAccount']['credit'] += tax
                
            elif op.operation_type == OperationType.ITEM_REJECTED:
                # Deterministic Compensating Operation
                amt = Decimal(str(payload.get('taxable_amount', 0)))
                tax = Decimal(str(payload.get('tax_amount', 0)))
                gt = amt + tax
                
                state['grand_total'] -= gt
                state['total_tax'] -= tax
                state['igst'] -= tax
                state['taxable_amount'] -= amt
                
                # Reversal Ledgers (Debit Note equivalent)
                state['ledgers']['AccountsReceivable']['credit'] += gt
                state['ledgers']['SalesAccount']['debit'] += amt
                state['ledgers']['TaxAccount']['debit'] += tax

            elif op.operation_type == OperationType.PAYMENT_ALLOCATED:
                amt = Decimal(str(payload.get('amount', 0)))
                state['ledgers']['AccountsReceivable']['credit'] += amt
                if 'CashAccount' not in state['ledgers']:
                    state['ledgers']['CashAccount'] = {'debit': Decimal('0.0'), 'credit': Decimal('0.0')}
                state['ledgers']['CashAccount']['debit'] += amt

        return state
        
    def validate_convergence(self) -> bool:
        """
        Passes the evaluated state through the rigid Invariant Engine.
        Must return True before a database commit is allowed.
        """
        state = self.evaluate_state()
        return InvariantEngine.evaluate_converged_state(state)

    def generate_state_commitment(self) -> str:
        """
        Calculates the Cross-Ledger State Commitment (CLSC) hash for the graph.
        """
        import json
        from .crypto import CrossLedgerCommitment
        
        # 1. Operation State Root (O_n)
        ops = self._causal_sort()
        ops_str = json.dumps([op.to_dict() for op in ops], sort_keys=True)
        operation_state_root = hashlib.sha256(ops_str.encode('utf-8')).hexdigest()
        
        # 2. Extract context from base operation (Assume first operation is TRANSACTION_ISSUED)
        base_op = ops[0] if ops else None
        tx_id = base_op.transaction_id if base_op else "UNKNOWN"
        
        # 3. Generate final commitment
        commitment = CrossLedgerCommitment(
            transaction_id=tx_id,
            canonical_tx_hash="TBD_CANONICAL_HASH",  # Normally injected from CanonicalTx
            operation_state_root=operation_state_root,
            seller_identity="SELLER", # Extracted from context
            buyer_identity="BUYER",   # Extracted from context
            protocol_version="1.0",
            previous_commitment_hash=None
        )
        return commitment.calculate_hash()

