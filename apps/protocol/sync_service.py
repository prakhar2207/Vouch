from typing import List, Dict, Any
from .operation import AccountingOperation, OperationType
from .crdt import DE_CRDT

class SyncService:
    """
    Manages the 2-way synchronization between disconnected replicas (e.g., Service Workers)
    and the central Vouch node using the DE-CRDT merge algorithm.
    """

    @staticmethod
    def process_sync_payload(
        transaction_id: str,
        client_replica_id: str,
        client_operations: List[Dict[str, Any]],
        server_operations: List[AccountingOperation]
    ) -> Dict[str, Any]:
        """
        Idempotent 2-way synchronization endpoint.
        Takes the client's operation log, merges it with the server's log,
        validates the invariants, and returns the missing server operations to the client.
        """
        # 1. Reconstruct Server CRDT from local database state
        server_crdt = DE_CRDT("SERVER")
        for op in server_operations:
            server_crdt.apply_operation(op)

        # 2. Reconstruct Client CRDT from incoming payload
        client_crdt = DE_CRDT(client_replica_id)
        for op_dict in client_operations:
            # Work on a copy to avoid mutating the caller's data
            op_copy = {**op_dict}
            # Rehydrate string enums back to OperationType if necessary
            if isinstance(op_copy.get('operation_type'), str):
                op_copy['operation_type'] = OperationType(op_copy['operation_type'])
                
            op_copy.pop('payload_hash', None)
            op = AccountingOperation(**op_copy)
            client_crdt.apply_operation(op)

        # 3. Deterministic CRDT Merge
        # This inherently deduplicates operations using operation_id
        merged_crdt = server_crdt.merge(client_crdt)

        # 4. Evaluate & Validate Converged State
        try:
            is_valid = merged_crdt.validate_convergence()
            if not is_valid:
                return {"status": "SYNC_REJECTED", "reason": "Invariant validation returned False."}
        except Exception as e:
            return {"status": "SYNC_REJECTED", "reason": str(e)}

        # 5. Determine Missing Operations for Client (2-Way Sync)
        # Send back operations the server knows about that the client didn't include in its payload
        client_op_ids = {op['operation_id'] for op in client_operations}
        operations_for_client = [
            op.to_dict() for op_id, op in merged_crdt.operations.items()
            if op_id not in client_op_ids
        ]

        # 6. Generate Mathematical State Commitment
        commitment_hash = merged_crdt.generate_state_commitment()
        
        # 7. Execute actual DB commit here (Phase 13 implementation)
        # db.commit(merged_crdt.operations)

        return {
            "status": "SYNC_SUCCESS",
            "transaction_id": transaction_id,
            "server_operations_to_apply": operations_for_client,
            "state_commitment": commitment_hash,
            "converged_state": merged_crdt.evaluate_state()
        }
