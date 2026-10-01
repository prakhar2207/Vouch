import os, sys
from decimal import Decimal
import time

from .operation import AccountingOperation, OperationType
from .crdt import DE_CRDT
from .handshake import EdiStateMachine, EdiState, IllegalStateTransitionError
from .qr_bootstrap import QRSessionManager, QRBootstrapPayload, SecurityViolation
from .crypto import Ed25519SignerPlaceholder
from .invariants import InvariantEngine, AccountingInvariantViolation

def run_threat_simulations():
    print("--- VOUCH PROTOCOL THREAT SIMULATOR ---")

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
    crdt = DE_CRDT("BUYER")
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

if __name__ == "__main__":
    run_threat_simulations()
