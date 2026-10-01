import logging
import hashlib
from typing import List, Dict, Any, Optional, Set
from .operation import AccountingOperation, OperationType
from .crdt import DE_CRDT
from .crypto import ProtocolCrypto, CrossLedgerCommitment
from .semantic_delta import SemanticDeltaEngine, SemanticDelta
from .invariants import InvariantEngine
from .compensation import CompensationEngine
from .bridge import LedgerBridge
from .schema import CanonicalTransaction

logger = logging.getLogger(__name__)

class MultiTenantSecurityError(Exception):
    """Raised when tenant isolation or counterparty authorization is violated."""
    pass

class SyncService:
    """
    Production-grade 2-way synchronization service for distributed, offline accounting replicas.
    Enforces server-side tenant isolation, asymmetric signature verification, 
    causal dependency satisfaction, atomic merge-compensation pipeline, 
    independent Merkle state roots, and Vouch Ledger Bridge execution.
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
        canonical_tx_hash: Optional[str] = None,
        previous_commitment_hash: Any = None,
        verify_signatures: bool = True,
        public_keys_map: Optional[Dict[str, str]] = None,
        company: Any = None,
        canonical_tx: Optional[CanonicalTransaction] = None,
        user: Any = None,
        persist_to_db: bool = False
    ) -> Dict[str, Any]:
        """
        Production 2-way synchronization endpoint:
        1. Validates multi-tenant isolation and counterparty authorization.
        2. Validates canonical transaction hash integrity.
        3. Enforces cryptographic signatures (fail-closed Ed25519; mandatory in production).
        4. Validates causal parent completeness.
        5. Performs deterministic CRDT merge.
        6. Runs automated atomic compensation pipeline (Item Rejection / Price Adjustments).
        7. Evaluates double-entry and tax invariants.
        8. Calculates semantic delta.
        9. Computes independent Seller and Buyer Merkle state roots & commitment hash.
        10. Executes Authoritative Vouch Ledger Bridge (fails closed on bridge error).
        11. Persists to database atomically (fails closed on persistence error).
        12. Returns missing server operations for 2-way client sync.
        """
        # 1. Server-Side Multi-Tenant Authorization Check
        if authorized_counterparty_ids is not None:
            if authenticated_tenant_id not in authorized_counterparty_ids:
                raise MultiTenantSecurityError(
                    f"Access Denied: Tenant {authenticated_tenant_id} is not an authorized counterparty for transaction {transaction_id}"
                )

        # 2. Canonical Transaction Hash Integrity Verification & Server-Side Reconstruction
        if canonical_tx_hash == "TBD_CANONICAL_HASH":
            return {
                "status": "SYNC_REJECTED",
                "reason": "Invalid canonical transaction hash: placeholder 'TBD_CANONICAL_HASH' is forbidden in production."
            }

        # If canonical_tx is not provided directly, attempt server-side reconstruction
        if canonical_tx is None:
            try:
                from .models import ProtocolTransaction
                db_ptx = ProtocolTransaction.objects.filter(transaction_id=transaction_id).first()
                if db_ptx and db_ptx.canonical_payload:
                    canonical_tx = CanonicalTransaction.from_dict(db_ptx.canonical_payload)
            except Exception:
                pass

        computed_tx_hash = None
        if canonical_tx:
            if hasattr(canonical_tx, 'validate_invariants'):
                try:
                    canonical_tx.validate_invariants()
                except Exception as inv_err:
                    return {
                        "status": "SYNC_REJECTED",
                        "reason": f"Canonical transaction invariant violation: {inv_err}"
                    }
            if hasattr(canonical_tx, 'canonical_hash'):
                computed_tx_hash = canonical_tx.canonical_hash

        if computed_tx_hash:
            if canonical_tx_hash and canonical_tx_hash != computed_tx_hash:
                return {
                    "status": "SYNC_REJECTED",
                    "reason": f"Canonical transaction hash mismatch: claimed {canonical_tx_hash} != calculated {computed_tx_hash}"
                }
            effective_tx_hash = computed_tx_hash
        else:
            if not canonical_tx_hash:
                return {
                    "status": "SYNC_REJECTED",
                    "reason": "Missing canonical transaction payload or deterministic canonical_tx_hash. Transaction-ID hash fallbacks are strictly forbidden before state commitment."
                }
            effective_tx_hash = canonical_tx_hash

        # 3. Reconstruct Server CRDT from local database state
        server_crdt = DE_CRDT(
            replica_id="SERVER",
            transaction_id=transaction_id,
            tenant_id=authenticated_tenant_id
        )
        for op in server_operations:
            server_crdt.apply_operation(op)

        # 4. Cryptographic Hardware Device & Replica Binding
        client_dev = None
        if company:
            from .models import AuthorizedDevice
            client_dev = AuthorizedDevice.objects.filter(company=company, replica_id=client_replica_id).first()
            if not client_dev:
                return {
                    "status": "SYNC_REJECTED",
                    "reason": f"Unregistered device: Replica {client_replica_id} is not an authorized device for company {company.name}."
                }
            if client_dev.status != "ACTIVE":
                return {
                    "status": "SYNC_REJECTED",
                    "reason": f"Unauthorized device status: Device {client_replica_id} has status '{client_dev.status}' (must be ACTIVE)."
                }

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

            op_dev = None
            if company:
                from .models import AuthorizedDevice
                op_dev = AuthorizedDevice.objects.filter(replica_id=op.replica_id).first()
                if not op_dev:
                    if not (public_keys_map and op.replica_id in public_keys_map):
                        return {
                            "status": "SYNC_REJECTED",
                            "reason": f"Operation from unauthorized replica: {op.replica_id} is not registered in system."
                        }
                elif op_dev.status != "ACTIVE":
                    return {
                        "status": "SYNC_REJECTED",
                        "reason": f"Replica device {op.replica_id} has status '{op_dev.status}' (must be ACTIVE)."
                    }
                elif op.replica_id == client_replica_id and op_dev.company_id != company.id:
                    return {
                        "status": "SYNC_REJECTED",
                        "reason": f"Device {op.replica_id} is registered to a different company than authenticated tenant."
                    }

            # Strict Fail-Closed Digital Signature Verification
            if verify_signatures:
                if not op.signature:
                    return {
                        "status": "SYNC_REJECTED",
                        "reason": f"Operation {op.operation_id} from replica {op.replica_id} is unsigned. Production requires valid Ed25519 signatures."
                    }
                
                # Public key resolution: pinned database device key takes authoritative priority
                pub_key = None
                if op_dev:
                    pub_key = op_dev.public_key_hex
                elif public_keys_map and op.replica_id in public_keys_map:
                    pub_key = public_keys_map[op.replica_id]
                else:
                    from .key_manager import ProtocolKeyManager
                    pub_key = ProtocolKeyManager.get_active_public_key(op.replica_id)

                if not pub_key:
                    return {
                        "status": "SYNC_REJECTED",
                        "reason": f"No active public key found for replica {op.replica_id} to verify operation {op.operation_id}."
                    }
                sig_valid = ProtocolCrypto.verify(op.payload_hash, op.signature, pub_key)
                if not sig_valid:
                    return {
                        "status": "SYNC_REJECTED",
                        "reason": f"Cryptographic signature check failed on operation {op.operation_id}."
                    }

            client_crdt.apply_operation(op)

        # 4. Check for missing causal parents / orphaned operations
        missing_parents = client_crdt.dag.get_missing_parents()
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

        # 6. Automated Atomic Compensation Pipeline
        existing_recip_rejections = {
            op.payload.get('reference_rejection_op')
            for op in merged_crdt.operations.values()
            if op.operation_type == OperationType.CREDIT_NOTE_ISSUED and op.payload.get('reference_rejection_op')
        }
        existing_recip_prices = {
            op.payload.get('reference_price_op')
            for op in merged_crdt.operations.values()
            if op.operation_type in (OperationType.CREDIT_NOTE_ISSUED, OperationType.DEBIT_NOTE_ISSUED)
            and op.payload.get('reference_price_op')
        }

        compensations_added = False
        for op in list(merged_crdt.operations.values()):
            if op.operation_type == OperationType.ITEM_REJECTED and op.operation_id not in existing_recip_rejections:
                max_clock = max([o.logical_timestamp for o in merged_crdt.operations.values()] or [0])
                recip_cn = CompensationEngine.generate_reciprocal_seller_credit_note(
                    rejection_op=op,
                    seller_replica_id="SERVER_SELLER",
                    logical_timestamp=max_clock + 1
                )
                merged_crdt.apply_operation(recip_cn)
                compensations_added = True
            elif op.operation_type == OperationType.PRICE_ADJUSTED and op.operation_id not in existing_recip_prices:
                max_clock = max([o.logical_timestamp for o in merged_crdt.operations.values()] or [0])
                recip_note = CompensationEngine.generate_reciprocal_price_adjustment_note(
                    price_adj_op=op,
                    seller_replica_id="SERVER_SELLER",
                    logical_timestamp=max_clock + 1
                )
                merged_crdt.apply_operation(recip_note)
                compensations_added = True

        if compensations_added:
            merged_crdt = merged_crdt.merge(merged_crdt)

        # 7. Evaluate & Validate Converged State
        try:
            is_valid = merged_crdt.validate_convergence()
            if not is_valid:
                return {"status": "SYNC_REJECTED", "reason": "Invariant validation returned False."}
        except Exception as e:
            return {"status": "SYNC_REJECTED", "reason": str(e)}

        # 8. Compute Semantic Delta between pre-merge server state and converged state
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

        # 9. Determine Missing Operations for Client (2-Way Sync)
        client_op_ids = {op['operation_id'] for op in client_operations}
        operations_for_client = [
            op.to_dict() for op_id, op in merged_crdt.operations.items()
            if op_id not in client_op_ids
        ]

        # 10. Generate Independent Merkle State Roots & Commitment
        roots = merged_crdt.compute_merkle_state_roots()
        commitment_hash = merged_crdt.generate_state_commitment(
            seller_identity=seller_identity,
            buyer_identity=buyer_identity,
            canonical_tx_hash=effective_tx_hash,
            previous_commitment_hash=previous_commitment_hash
        )

        # 11. Execute Authoritative Vouch Accounting Ledger Bridge (if requested)
        bridge_result = None
        if company and canonical_tx:
            try:
                bridge_result = LedgerBridge.execute_converged_accounting(
                    company=company,
                    canonical_tx=canonical_tx,
                    converged_operations=merged_crdt.get_operations(),
                    user=user
                )
            except Exception as e:
                logger.error(f"LedgerBridge execution error: {e}", exc_info=True)
                bridge_result = {"status": "BRIDGE_FAILED", "error": str(e)}

            if not bridge_result or bridge_result.get("status") != "BRIDGE_SUCCESS":
                return {
                    "status": "BRIDGE_FAILED",
                    "transaction_id": transaction_id,
                    "error": bridge_result.get("error", "LedgerBridge execution failed") if bridge_result else "Bridge execution returned null",
                    "bridge_result": bridge_result
                }

        # 12. Persist Merged State to Django ORM (if requested)
        if persist_to_db:
            try:
                from django.db import transaction as db_transaction
                from .models import ProtocolTransaction, ProtocolOperation, CryptographicCommitment

                with db_transaction.atomic():
                    payload_dict = canonical_tx.to_dict() if (canonical_tx and hasattr(canonical_tx, 'to_dict')) else {"transaction_id": transaction_id}
                    ptx, _ = ProtocolTransaction.objects.get_or_create(
                        transaction_id=transaction_id,
                        defaults={
                            "transaction_type": "SALE",
                            "protocol_version": "1.0",
                            "source_company_id": seller_identity,
                            "destination_company_id": buyer_identity,
                            "canonical_payload": payload_dict
                        }
                    )

                    for op in merged_crdt.get_operations():
                        op_type_val = op.operation_type.value if hasattr(op.operation_type, 'value') else str(op.operation_type)
                        ProtocolOperation.objects.get_or_create(
                            operation_id=op.operation_id,
                            replica_id=op.replica_id,
                            defaults={
                                "transaction": ptx,
                                "operation_type": op_type_val,
                                "payload": dict(op.payload),
                                "logical_timestamp": op.logical_timestamp,
                                "parents": list(op.parents),
                                "payload_hash": op.payload_hash,
                                "signature": op.signature
                            }
                        )

                    CryptographicCommitment.objects.get_or_create(
                        commitment_hash=commitment_hash,
                        defaults={
                            "transaction": ptx,
                            "operation_state_root": roots["operation_state_root"],
                            "previous_commitment_hash": str(previous_commitment_hash) if previous_commitment_hash else None
                        }
                    )
            except Exception as e:
                logger.error(f"Protocol database persistence failure: {e}", exc_info=True)
                return {
                    "status": "PERSISTENCE_FAILED",
                    "transaction_id": transaction_id,
                    "error": f"Failed to persist protocol state to database: {str(e)}"
                }

        return {
            "status": "SYNC_SUCCESS",
            "transaction_id": transaction_id,
            "server_operations_to_apply": operations_for_client,
            "state_commitment": commitment_hash,
            "merkle_state_roots": roots,
            "converged_state": converged_eval,
            "semantic_delta": semantic_delta.summary() if semantic_delta and semantic_delta.has_divergence else None,
            "bridge_result": bridge_result
        }


class TestSyncService:
    """
    Test harness synchronization service that disables mandatory signature checks
    strictly for unit testing and offline mocking.
    """
    @classmethod
    def process_sync_payload(cls, *args, **kwargs):
        kwargs['verify_signatures'] = False
        return SyncService.process_sync_payload(*args, **kwargs)
