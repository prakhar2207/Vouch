import hashlib
from typing import Dict, List, Any, Optional
from decimal import Decimal

from .operation import AccountingOperation, OperationType
from .invariants import InvariantEngine
from .causal_dag import CausalDAG
from .crypto import MerkleTree, CrossLedgerCommitment

class DE_CRDT:
    """
    Double-Entry Conflict-Free Replicated Data Type (DE-CRDT).
    Coordinates distributed accounting operations over a Causal DAG,
    computes deterministic double-entry states, validates financial invariants,
    and produces 4-way Merkle state roots for cross-ledger cryptographic commitment.
    """

    def __init__(self, replica_id: str, transaction_id: str = "TX-DEFAULT", tenant_id: str = "DEFAULT_TENANT"):
        self.replica_id = replica_id
        self.transaction_id = transaction_id
        self.tenant_id = tenant_id
        self.dag = CausalDAG(transaction_id)
        
    @property
    def operations(self) -> Dict[str, AccountingOperation]:
        """Provides backward-compatible dict access to admitted operations."""
        return self.dag.operations

    def apply_operation(self, op: AccountingOperation):
        """Idempotently adds an operation to the causal DAG."""
        # Align DAG transaction_id if default
        if self.dag.transaction_id == "TX-DEFAULT" and op.transaction_id != "TX-DEFAULT":
            self.transaction_id = op.transaction_id
            self.dag.transaction_id = op.transaction_id
        self.dag.add_operation(op)

    def merge(self, other: 'DE_CRDT') -> 'DE_CRDT':
        """
        Deterministic mathematical union of two causal operation graphs.
        Guarantees Commutativity (Merge(A, B) == Merge(B, A)),
        Idempotency (Merge(A, A) == A), and Associativity.
        """
        target_tx_id = self.transaction_id if self.transaction_id != "TX-DEFAULT" else other.transaction_id
        merged = DE_CRDT(
            replica_id=f"MERGED_{self.replica_id}_{other.replica_id}",
            transaction_id=target_tx_id,
            tenant_id=self.tenant_id
        )
        
        # Collect all operations (including admitted and queued orphans)
        all_ops = list(self.dag.operations.values()) + list(self.dag.orphans.values()) + \
                  list(other.dag.operations.values()) + list(other.dag.orphans.values())
        
        # Sort by timestamp so root parents are fed first to DAG
        all_ops.sort(key=lambda x: (x.logical_timestamp, x.operation_id))
        
        for op in all_ops:
            merged.apply_operation(op)
            
        return merged

    def _causal_sort(self) -> List[AccountingOperation]:
        """Returns operations in strictly valid causal topological order."""
        return self.dag.topological_sort()

    def get_operations(self) -> List[AccountingOperation]:
        """Returns all admitted operations in strict causal topological order."""
        return self.dag.topological_sort()

    @staticmethod
    def _extract_tax_components(payload: Dict[str, Any], total_tax: Decimal) -> Dict[str, Decimal]:
        """
        Authoritative GST decomposition engine integration.
        Uses explicit payload decomposition if provided, or calls Vouch's GSTCalculator.
        Fails closed on calculation errors. Eliminates naive 'igst += tax' logic.
        """
        has_cgst = 'cgst_amount' in payload
        has_sgst = 'sgst_amount' in payload
        has_igst = 'igst_amount' in payload

        if has_cgst or has_sgst or has_igst:
            cgst = Decimal(str(payload.get('cgst_amount', 0)))
            sgst = Decimal(str(payload.get('sgst_amount', 0)))
            igst = Decimal(str(payload.get('igst_amount', 0)))
            if (cgst + sgst + igst) == Decimal('0.0') and total_tax > Decimal('0.0'):
                if payload.get('treatment') == 'INTERSTATE':
                    igst = total_tax
                else:
                    half = (total_tax / Decimal('2')).quantize(Decimal('0.01'))
                    cgst = half
                    sgst = total_tax - half
            return {'cgst': cgst, 'sgst': sgst, 'igst': igst}

        seller_state = payload.get('seller_state_code') or payload.get('company_state_code')
        buyer_state = payload.get('buyer_state_code') or payload.get('party_state_code')
        taxable = Decimal(str(payload.get('taxable_amount', payload.get('amount', 0))))
        rate = Decimal(str(payload.get('tax_rate_percent', payload.get('gst_rate', 0))))

        if (seller_state or buyer_state) and (taxable > Decimal('0') or total_tax > Decimal('0')):
            from apps.gst.services.gst_calculator import GSTCalculator
            c_state = str(seller_state or buyer_state)
            p_state = str(buyer_state or seller_state)
            # Fail closed: never swallow GST calculation exceptions
            res = GSTCalculator.calculate_taxes(
                company_state_code=c_state,
                party_state_code=p_state,
                taxable_amount=taxable if taxable > Decimal('0') else total_tax,
                gst_rate=rate if rate > Decimal('0') else Decimal('18.00')
            )
            return {
                'cgst': res['cgst'],
                'sgst': res['sgst'],
                'igst': res['igst']
            }

        if total_tax == Decimal('0.0'):
            return {'cgst': Decimal('0.0'), 'sgst': Decimal('0.0'), 'igst': Decimal('0.0')}

        if payload.get('treatment') == 'INTERSTATE':
            return {'cgst': Decimal('0.0'), 'sgst': Decimal('0.0'), 'igst': total_tax}

        half = (total_tax / Decimal('2')).quantize(Decimal('0.01'))
        return {'cgst': half, 'sgst': total_tax - half, 'igst': Decimal('0.0')}

    def evaluate_state(self) -> Dict[str, Any]:
        """
        Projects the causal operation graph into a complete, balanced accounting state:
        Double-Entry Ledgers, Tax Components, Grand Totals, and Inventory.
        """
        ops = self._causal_sort()
        
        state: Dict[str, Any] = {
            'ledgers': {
                'AccountsReceivable': {'debit': Decimal('0.0'), 'credit': Decimal('0.0')},
                'SalesAccount': {'debit': Decimal('0.0'), 'credit': Decimal('0.0')},
                'TaxAccount': {'debit': Decimal('0.0'), 'credit': Decimal('0.0')}
            },
            'inventory_lines': {},
            'total_quantity': Decimal('0.0'),
            'taxable_amount': Decimal('0.0'),
            'total_tax': Decimal('0.0'),
            'total_charges': Decimal('0.0'),
            'total_discount': Decimal('0.0'),
            'grand_total': Decimal('0.0'),
            'round_off': Decimal('0.0'),
            'cgst': Decimal('0.0'),
            'sgst': Decimal('0.0'),
            'igst': Decimal('0.0'),
            'allocated_payment': Decimal('0.0'),
            'invoice_grand_total': Decimal('0.0')
        }

        for op in ops:
            payload = op.payload
            
            if op.operation_type in (OperationType.TRANSACTION_ISSUED, OperationType.INVOICE_ISSUED):
                gt = Decimal(str(payload.get('grand_total', 0)))
                tax = Decimal(str(payload.get('total_tax', payload.get('tax_amount', 0))))
                taxable = Decimal(str(payload.get('taxable_amount', 0)))
                qty = Decimal(str(payload.get('quantity', 0)))
                
                state['grand_total'] += gt
                state['invoice_grand_total'] += gt
                state['total_tax'] += tax
                
                tax_parts = self._extract_tax_components(payload, tax)
                state['cgst'] += tax_parts['cgst']
                state['sgst'] += tax_parts['sgst']
                state['igst'] += tax_parts['igst']
                
                state['taxable_amount'] += taxable
                state['total_quantity'] += qty
                
                state['ledgers']['AccountsReceivable']['debit'] += gt
                state['ledgers']['SalesAccount']['credit'] += taxable
                state['ledgers']['TaxAccount']['credit'] += tax
                
            elif op.operation_type in (OperationType.ITEM_REJECTED, OperationType.CREDIT_NOTE_ISSUED):
                amt = Decimal(str(payload.get('taxable_amount', payload.get('amount', 0))))
                tax = Decimal(str(payload.get('tax_amount', 0)))
                gt = amt + tax
                qty = Decimal(str(payload.get('quantity', 0)))
                
                state['grand_total'] -= gt
                state['total_tax'] -= tax
                
                tax_parts = self._extract_tax_components(payload, tax)
                state['cgst'] -= tax_parts['cgst']
                state['sgst'] -= tax_parts['sgst']
                state['igst'] -= tax_parts['igst']
                
                state['taxable_amount'] -= amt
                state['total_quantity'] -= qty
                
                state['ledgers']['AccountsReceivable']['credit'] += gt
                state['ledgers']['SalesAccount']['debit'] += amt
                state['ledgers']['TaxAccount']['debit'] += tax

            elif op.operation_type in (OperationType.DEBIT_NOTE_ISSUED, OperationType.DEBIT_NOTE_CREATED):
                amt = Decimal(str(payload.get('taxable_amount', payload.get('amount', 0))))
                tax = Decimal(str(payload.get('tax_amount', 0)))
                gt = amt + tax
                
                state['grand_total'] += gt
                state['total_tax'] += tax
                
                tax_parts = self._extract_tax_components(payload, tax)
                state['cgst'] += tax_parts['cgst']
                state['sgst'] += tax_parts['sgst']
                state['igst'] += tax_parts['igst']
                
                state['taxable_amount'] += amt
                
                state['ledgers']['AccountsReceivable']['debit'] += gt
                state['ledgers']['SalesAccount']['credit'] += amt
                state['ledgers']['TaxAccount']['credit'] += tax

            elif op.operation_type == OperationType.PRICE_ADJUSTED:
                amt = Decimal(str(payload.get('taxable_amount', payload.get('amount', 0))))
                tax = Decimal(str(payload.get('tax_amount', 0)))
                gt = amt + tax
                tax_parts = self._extract_tax_components(payload, abs(tax))
                if amt < Decimal('0'):
                    abs_amt = abs(amt)
                    abs_tax = abs(tax)
                    abs_gt = abs_amt + abs_tax
                    state['grand_total'] -= abs_gt
                    state['total_tax'] -= abs_tax
                    state['cgst'] -= tax_parts['cgst']
                    state['sgst'] -= tax_parts['sgst']
                    state['igst'] -= tax_parts['igst']
                    state['taxable_amount'] -= abs_amt
                    state['ledgers']['AccountsReceivable']['credit'] += abs_gt
                    state['ledgers']['SalesAccount']['debit'] += abs_amt
                    state['ledgers']['TaxAccount']['debit'] += abs_tax
                else:
                    state['grand_total'] += gt
                    state['total_tax'] += tax
                    state['cgst'] += tax_parts['cgst']
                    state['sgst'] += tax_parts['sgst']
                    state['igst'] += tax_parts['igst']
                    state['taxable_amount'] += amt
                    state['ledgers']['AccountsReceivable']['debit'] += gt
                    state['ledgers']['SalesAccount']['credit'] += amt
                    state['ledgers']['TaxAccount']['credit'] += tax

            elif op.operation_type == OperationType.PAYMENT_ALLOCATED:
                amt = Decimal(str(payload.get('amount', 0)))
                state['ledgers']['AccountsReceivable']['credit'] += amt
                if 'CashAccount' not in state['ledgers']:
                    state['ledgers']['CashAccount'] = {'debit': Decimal('0.0'), 'credit': Decimal('0.0')}
                state['ledgers']['CashAccount']['debit'] += amt
                state['allocated_payment'] += amt

            elif op.operation_type == OperationType.ITEM_ACCEPTED:
                pass # Acknowledged without financial mutation

        return state
        
    def validate_convergence(self) -> bool:
        """Evaluates state and validates all double-entry and tax invariants."""
        state = self.evaluate_state()
        return InvariantEngine.evaluate_converged_state(state)

    def compute_merkle_state_roots(self) -> Dict[str, str]:
        """
        Builds formal Merkle trees for the distinct accounting subsystems:
        1. Operation State Root (O_n)
        2. Seller Ledger State Root (L_seller)
        3. Seller Inventory State Root (I_seller)
        4. Buyer Ledger State Root (L_buyer)
        5. Buyer Inventory State Root (I_buyer)
        6. Transaction Baseline Root (T_n)
        """
        ops = self._causal_sort()
        state = self.evaluate_state()
        
        # 1. Operation Root
        op_leaves = [op.payload_hash for op in ops]
        op_root = MerkleTree(op_leaves).root

        # 2. Seller Ledger Root (Receivable, Sales Income, Output Tax)
        seller_leaves = [
            f"{acct}:{data['debit']}:{data['credit']}"
            for acct, data in sorted(state['ledgers'].items())
        ]
        seller_ledger_root = MerkleTree(seller_leaves).root

        # 3. Seller Inventory Root
        seller_inv_leaves = [f"SELLER_DISPATCHED:{state['total_quantity']}"]
        seller_inv_root = MerkleTree(seller_inv_leaves).root

        # 4. Buyer Ledger Root (Reciprocal Payable, Purchase Expense, Input Tax Credit)
        ar = state['ledgers'].get('AccountsReceivable', {'debit': Decimal('0.0'), 'credit': Decimal('0.0')})
        sales = state['ledgers'].get('SalesAccount', {'debit': Decimal('0.0'), 'credit': Decimal('0.0')})
        tax = state['ledgers'].get('TaxAccount', {'debit': Decimal('0.0'), 'credit': Decimal('0.0')})
        cash = state['ledgers'].get('CashAccount', {'debit': Decimal('0.0'), 'credit': Decimal('0.0')})

        buyer_ledgers = {
            'AccountsPayable': {'debit': ar['credit'], 'credit': ar['debit']},
            'PurchaseAccount': {'debit': sales['credit'], 'credit': sales['debit']},
            'InputTaxAccount': {'debit': tax['credit'], 'credit': tax['debit']},
            'CashAccount': {'debit': cash['credit'], 'credit': cash['debit']}
        }
        buyer_leaves = [
            f"{acct}:{data['debit']}:{data['credit']}"
            for acct, data in sorted(buyer_ledgers.items())
        ]
        buyer_ledger_root = MerkleTree(buyer_leaves).root

        # 5. Buyer Inventory Root
        buyer_inv_leaves = [f"BUYER_RECEIVED:{state['total_quantity']}"]
        buyer_inv_root = MerkleTree(buyer_inv_leaves).root

        # 6. Transaction Baseline Root
        tx_leaves = [
            f"TX_ID:{self.transaction_id}",
            f"GT:{state['grand_total']}",
            f"TAX:{state['total_tax']}"
        ]
        tx_root = MerkleTree(tx_leaves).root

        # Combined roots for backward compatibility
        combined_ledger_root = MerkleTree(seller_leaves + buyer_leaves).root
        combined_inv_root = MerkleTree(seller_inv_leaves + buyer_inv_leaves).root

        return {
            "operation_state_root": op_root,
            "seller_ledger_root": seller_ledger_root,
            "seller_inventory_root": seller_inv_root,
            "buyer_ledger_root": buyer_ledger_root,
            "buyer_inventory_root": buyer_inv_root,
            "transaction_state_root": tx_root,
            "ledger_state_root": combined_ledger_root,
            "inventory_state_root": combined_inv_root
        }

    def generate_state_commitment(
        self,
        seller_identity: str = "SELLER",
        buyer_identity: str = "BUYER",
        canonical_tx_hash: Optional[str] = None,
        previous_commitment_hash: Any = None
    ) -> str:
        """
        Calculates the Cross-Ledger State Commitment ($C_n$) hash binding the independent Merkle state roots.
        """
        roots = self.compute_merkle_state_roots()
        ops = self._causal_sort()
        base_op = ops[0] if ops else None
        base_payload = base_op.payload if base_op else {}

        seller = seller_identity if seller_identity != "SELLER" else base_payload.get("source_company_id", "SELLER")
        buyer = buyer_identity if buyer_identity != "BUYER" else base_payload.get("destination_company_id", "BUYER")
        tx_hash = canonical_tx_hash if (canonical_tx_hash and canonical_tx_hash != "TBD_CANONICAL_HASH") else roots["transaction_state_root"]

        commitment = CrossLedgerCommitment(
            transaction_id=self.transaction_id,
            transaction_state_root=tx_hash,
            operation_state_root=roots["operation_state_root"],
            seller_ledger_root=roots["seller_ledger_root"],
            seller_inventory_root=roots["seller_inventory_root"],
            buyer_ledger_root=roots["buyer_ledger_root"],
            buyer_inventory_root=roots["buyer_inventory_root"],
            seller_identity=seller,
            buyer_identity=buyer,
            protocol_version="1.0",
            previous_commitment_hash=previous_commitment_hash
        )
        return commitment.calculate_hash()
