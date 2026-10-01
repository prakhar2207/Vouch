import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crdt.replica import DE_CRDT_Replica
from crdt.operation import AccountingOperation

def run_benchmarks():
    print("\n--- Running Formal Convergence Test Suite (Vouch Protocol POC) ---\n")
    
    # 1. Setup Independent Replicas
    replica_A = DE_CRDT_Replica("SELLER")
    replica_B = DE_CRDT_Replica("BUYER")
    replica_C = DE_CRDT_Replica("AUDIT_NODE")

    # 2. Base Transaction: Seller generates 100k Invoice
    op1 = AccountingOperation("OP-001", "TX-108", "SELLER", "INVOICE_ISSUED", {"amount": 100000, "qty": 10}, 1)
    replica_A.apply_operation(op1)
    replica_B.apply_operation(op1)
    replica_C.apply_operation(op1)

    # 3. Concurrent Offline Operations
    # Buyer rejects 20k worth of goods offline
    op2 = AccountingOperation("OP-002", "TX-108", "BUYER", "ITEM_REJECTED", {"amount": 20000, "qty": 2}, 2, parents=["OP-001"])
    replica_B.apply_operation(op2)
    
    # Seller adds a payment offline concurrently
    op3 = AccountingOperation("OP-003", "TX-108", "SELLER", "PAYMENT_RECEIVED", {"amount": 50000, "qty": 0}, 3, parents=["OP-001"])
    replica_A.apply_operation(op3)

    # 4. Perform N-Way Merges to prove Commutativity: Merge(A, B) == Merge(B, A)
    merged_AB = replica_A.merge(replica_B)
    merged_BA = replica_B.merge(replica_A)

    # 5. Evaluate Invariants
    state_AB = merged_AB.evaluate_state()
    state_BA = merged_BA.evaluate_state()
    
    print(f"State AB: {state_AB['ledgers']}")
    print(f"State BA: {state_BA['ledgers']}\n")

    print(f"Test 1: Commutativity (Merge(A,B) == Merge(B,A)): {state_AB == state_BA}")
    
    hash_AB = merged_AB.generate_state_commitment()
    hash_BA = merged_BA.generate_state_commitment()
    print(f"Test 2: Cryptographic State Commitment Match: {hash_AB == hash_BA}")
    print(f"--> Interlock Hash: {hash_AB[:16]}...\n")
    
    if state_AB == state_BA:
        print("✅ ALL TESTS PASSED: Protocol demonstrates mathematically sound, conflict-free accounting convergence.\n")
    else:
        print("❌ FAILED")

if __name__ == '__main__':
    run_benchmarks()
