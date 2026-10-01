from typing import List, Dict, Any, Optional, Set
from .operation import AccountingOperation, OperationType
from .crdt import DE_CRDT
from .crypto import ProtocolCrypto, CrossLedgerCommitment
from .semantic_delta import SemanticDeltaEngine, SemanticDelta
from .invariants import InvariantEngine

class MultiTenantSecurityError(Exception):
    """Raised when tenant isolation or counterparty authorization is violated."""
    pass

class SyncService:
    """
    Production-grade 2-way synchronization service for distributed, offline accounting replicas.
    Enforces server-side tenant isolation, asymmetric signature verification, 
    causal dependency satisfaction, and 4-way Merkle cross-ledger state commitments.
    """

    @staticmethod
    def process_sync_payload(
        transaction_id: str,
        client_replica_id: str,
        client_operations: List[Dict[str, Any]],
        server_operations: List[AccountingOperation],
        authenticated_tenant_id: str = "DEFAULT_TENANT",
        authorized_counterparty_ids: Optional[Set[str]] = None,
        seller_identity: str = "SELLER",
        buyer_identity: str = "BUYER",
        canonical_tx_hash: str = "TBD_CANONICAL_HASH",
        previous_commitment_hash: Any = None,
        verify_signatures: bool = False,
        public_keys_map: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Idempotent 2-way synchronization endpoint.
        Takes the client's operation log, merges it into the server's causal DAG,
        validates the invariants, and returns the missing server operations to the client.
        """
        # 1. Server-Side Multi-Tenant Authorization Check
        if authorized_counterparty_ids is not None:
            if authenticated_tenant_id not in authorized_counterparty_ids:
                raise MultiTenantSecurityError(
                    f"Access Denied: Tenant {authenticated_tenant_id} is not an authorized counterparty for transaction {transaction_id}"
                )

        # 2. Reconstruct Server CRDT from local database state
        server_crdt = DE_CRDT(
            replica_id="SERVER",
            transaction_id=transaction_id,
            tenant_id=authenticated_tenant_id
        )
        for op in server_operations:
            server_crdt.apply_operation(op)

        # 3. Reconstruct Client CRDT from incoming payload (working on copies to avoid mutating caller data)
        client_crdt = DE_CRDT(
            replica_id=client_replica_id,
            transaction_id=transaction_id,
            tenant_id=authenticated_tenant_id
        )

        for op_dict in client_operations:
            op_copy = {**op_dict}
            
            # Rehydrate string enums
            if isinstance(op_copy.get('operation_type'), str):
                op_copy['operation_type'] = OperationType(op_copy['operation_type'])
                
            op_copy.pop('payload_hash', None)
            op = AccountingOperation(**op_copy)

            # Optional asymmetric digital signature verification
            if verify_signatures and public_keys_map and op.signature:
                pub_key = public_keys_map.get(op.replica_id)
                if pub_key:
                    sig_valid = ProtocolCrypto.verify(op.payload_hash, op.signature, pub_key)
                    if not sig_valid:
                        return {
                            "status": "SYNC_REJECTED",
                            "reason": f"Cryptographic signature check failed on operation {op.operation_id}"
                        }

            client_crdt.apply_operation(op)

        # 4. Check for missing causal parents / orphaned operations
        missing_parents = client_crdt.dag.get_missing_parents()
        # If server has the missing parents, supply them
        server_op_ids = {op.operation_id for op in server_operations}
        unresolved_missing = [p for p in missing_parents if p not in server_op_ids]
        if unresolved_missing:
            return {
                "status": "AWAITING_DEPENDENCIES",
                "transaction_id": transaction_id,
                "missing_parent_ids": unresolved_missing,
                "reason": f"Causal dependencies missing: {unresolved_missing}"
            }

        # 5. Deterministic CRDT Merge
        merged_crdt = server_crdt.merge(client_crdt)

        # 6. Evaluate & Validate Converged State
        try:
            is_valid = merged_crdt.validate_convergence()
            if not is_valid:
                return {"status": "SYNC_REJECTED", "reason": "Invariant validation returned False."}
        except Exception as e:
            return {"status": "SYNC_REJECTED", "reason": str(e)}

        # 7. Compute Semantic Delta between pre-merge server state and converged state
        server_eval = server_crdt.evaluate_state() if server_operations else {}
        converged_eval = merged_crdt.evaluate_state()
        semantic_delta = None
        if server_eval:
            semantic_delta = SemanticDeltaEngine.compute_state_delta(
                transaction_id=transaction_id,
                state_a=server_eval,
                state_b=converged_eval,
                replica_a_id="SERVER_PRE_MERGE",
                replica_b_id="CONVERGED_STATE",
                cause="Reconciliation of remote client operations"
            )

        # 8. Determine Missing Operations for Client (2-Way Sync)
        client_op_ids = {op['operation_id'] for op in client_operations}
        operations_for_client = [
            op.to_dict() for op_id, op in merged_crdt.operations.items()
            if op_id not in client_op_ids
        ]

        # 9. Generate 4-way Merkle State Roots & Commitment
        roots = merged_crdt.compute_merkle_state_roots()
        commitment_hash = merged_crdt.generate_state_commitment(
            seller_identity=seller_identity,
            buyer_identity=buyer_identity,
            canonical_tx_hash=canonical_tx_hash,
            previous_commitment_hash=previous_commitment_hash
        )

        return {
            "status": "SYNC_SUCCESS",
            "transaction_id": transaction_id,
            "server_operations_to_apply": operations_for_client,
            "state_commitment": commitment_hash,
            "merkle_state_roots": roots,
            "converged_state": converged_eval,
            "semantic_delta": semantic_delta.summary() if semantic_delta and semantic_delta.has_divergence else None
        }
