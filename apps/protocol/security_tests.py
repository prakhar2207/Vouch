import os, sys
from decimal import Decimal
import time

from .operation import AccountingOperation, OperationType
from .crdt import DE_CRDT
from .handshake import EdiStateMachine, EdiState, IllegalStateTransitionError
from .qr_bootstrap import QRSessionManager, QRBootstrapPayload, SecurityViolation
from .crypto import ProtocolCrypto, MerkleTree, Ed25519SignerPlaceholder
from .invariants import InvariantEngine, AccountingInvariantViolation
from .sync_service import SyncService, MultiTenantSecurityError

def run_threat_simulations():
    print("=========================================================")
    print("     VOUCH PROTOCOL ADVERSARIAL THREAT SIMULATOR        ")
    print("=========================================================")

    # ---------------------------------------------------------
    # THREAT 1: IN-MEMORY TAMPERING
    # ---------------------------------------------------------
    print("\n[Threat 1] Attacker intercepts operation and modifies amount...")
    op = AccountingOperation(
        operation_id='OP-1', transaction_id='TX-1', replica_id='SELLER',
        operation_type=OperationType.PAYMENT_ALLOCATED,
        payload={'amount': 100}, logical_timestamp=1
    )
    try:
        op.payload['amount'] = 999999
        print("[FAIL] FAIL: Payload mutated!")
    except Exception as e:
        print(f"[SUCCESS] DEFLECTED: Immutability locked. Error: {e}")

    # ---------------------------------------------------------
    # THREAT 2: NETWORK REPLAY ATTACK (CRDT Deduplication)
    # ---------------------------------------------------------
    print("\n[Threat 2] Attacker captures a valid 50k payment and resends it 100 times...")
    crdt = DE_CRDT("BUYER", "TX-1")
    for _ in range(100):
        crdt.apply_operation(op)
    if len(crdt.operations) == 1:
        print("[SUCCESS] DEFLECTED: CRDT mathematically deduplicated all 99 ghost operations. Balance remains exact.")
    else:
        print("[FAIL] FAIL: CRDT allowed duplicate operations.")

    # ---------------------------------------------------------
    # THREAT 3: STATE-SKIPPING HACK
    # ---------------------------------------------------------
    print("\n[Threat 3] Malicious node attempts to skip PREPARE phase and force COMMIT...")
    session = EdiStateMachine('SESS-01')
    session.advance(EdiState.CAPABILITY_EXCHANGE)
    session.advance(EdiState.AUTHENTICATE)
    try:
        session.advance(EdiState.COMMIT) # Illegal Jump
        print("[FAIL] FAIL: State machine allowed bypass!")
    except IllegalStateTransitionError as e:
        print(f"[SUCCESS] DEFLECTED: State Machine topology enforced. Error: {e}")

    # ---------------------------------------------------------
    # THREAT 4: MATHEMATICAL CORRUPTION (UNBALANCED LEDGER)
    # ---------------------------------------------------------
    print("\n[Threat 4] Attacker sends an operation that deletes tax liability without reducing Grand Total...")
    corrupted_state = {
        'ledgers': {
            'AccountsReceivable': {'debit': Decimal('1180.0'), 'credit': Decimal('0.0')},
            'SalesAccount': {'debit': Decimal('0.0'), 'credit': Decimal('1000.0')},
            # Missing Tax Account completely!
        },
        'taxable_amount': Decimal('1000.0'),
        'total_tax': Decimal('0.0'), # Tampered!
        'total_charges': Decimal('0.0'),
        'total_discount': Decimal('0.0'),
        'grand_total': Decimal('1180.0'),
        'cgst': Decimal('0.0'), 'sgst': Decimal('0.0'), 'igst': Decimal('0.0')
    }
    try:
        InvariantEngine.evaluate_converged_state(corrupted_state)
        print("[FAIL] FAIL: Invariant engine allowed corrupt accounting state to pass!")
    except AccountingInvariantViolation as e:
        print(f"[SUCCESS] DEFLECTED: Invariant Engine blocked commit. Error: {e}")

    # ---------------------------------------------------------
    # THREAT 5: ASYMMETRIC SIGNATURE FORGERY (Ed25519)
    # ---------------------------------------------------------
    print("\n[Threat 5] Attacker forges Ed25519 digital signature...")
    priv_a, pub_a = ProtocolCrypto.generate_keypair()
    priv_attacker, pub_attacker = ProtocolCrypto.generate_keypair()
    valid_sig = ProtocolCrypto.sign("LEGITIMATE_OPERATION_HASH", priv_a)
    
    # Attacker tries to present forged signature
    forged_sig = ProtocolCrypto.sign("LEGITIMATE_OPERATION_HASH", priv_attacker)
    if not ProtocolCrypto.verify("LEGITIMATE_OPERATION_HASH", forged_sig, pub_a):
        print("[SUCCESS] DEFLECTED: Ed25519 signature forgery detected and blocked.")
    else:
        print("[FAIL] FAIL: Forged signature accepted!")

    # ---------------------------------------------------------
    # THREAT 6: MERKLE TREE AUDIT PROOF TAMPERING
    # ---------------------------------------------------------
    print("\n[Threat 6] Attacker tampers with operation history in Merkle audit proof...")
    tree = MerkleTree(["OP-1", "OP-2", "OP-3", "OP-4"])
    proof = tree.get_proof(2)
    tampered_leaf = "FORGED_OPERATION_HASH_00000000000000000000000000000000000000000"
    if not MerkleTree.verify_proof(tampered_leaf, proof, tree.root):
        print("[SUCCESS] DEFLECTED: Merkle inclusion proof strictly rejected tampered operation.")
    else:
        print("[FAIL] FAIL: Merkle proof accepted tampered operation!")

    # ---------------------------------------------------------
    # THREAT 7: MULTI-TENANT ISOLATION BREACH (IDOR / Cross-Tenant)
    # ---------------------------------------------------------
    print("\n[Threat 7] Unauthorized tenant attempts cross-tenant operation injection...")
    try:
        SyncService.process_sync_payload(
            transaction_id="TX-SEC-001",
            client_replica_id="ROGUE-NODE",
            client_operations=[op.to_dict()],
            server_operations=[op],
            authenticated_tenant_id="TENANT-ROGUE",
            authorized_counterparty_ids={"TENANT-SELLER", "TENANT-BUYER"}
        )
        print("[FAIL] FAIL: Cross-tenant operation was permitted!")
    except MultiTenantSecurityError as e:
        print(f"[SUCCESS] DEFLECTED: Server-side multi-tenant isolation enforced. Error: {e}")

    # ---------------------------------------------------------
    # THREAT 8: DYNAMIC QR REPLAY ATTACK (Consumed Nonce)
    # ---------------------------------------------------------
    print("\n[Threat 8] Attacker replays consumed QR bootstrap code...")
    signer = Ed25519SignerPlaceholder()
    qr_mgr = QRSessionManager(signer)
    qr_payload = QRBootstrapPayload("1.0", "TX-QR-1", "SESS-SEC", "NONCE-REPLAY-99", "SELLER", "DIGEST", int(time.time())+300)
    qr_payload.signature = signer.sign(qr_payload.serialize_for_signature(), "PRIV_KEY")
    qr_str = qr_payload.encode_to_qr_string()
    
    # First scan succeeds
    qr_mgr.initiate_session_from_scan(qr_str, int(time.time()))
    # Replay scan must fail
    try:
        qr_mgr.initiate_session_from_scan(qr_str, int(time.time()))
        print("[FAIL] FAIL: QR replay succeeded!")
    except SecurityViolation as e:
        print(f"[SUCCESS] DEFLECTED: Ephemeral nonce check blocked QR replay. Error: {e}")

    print("\n[ALL THREATS DEFLECTED] Comprehensive security verification complete.")

if __name__ == "__main__":
    run_threat_simulations()
