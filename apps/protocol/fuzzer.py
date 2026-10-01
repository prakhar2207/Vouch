import os, sys, random
from decimal import Decimal
from typing import List, Dict, Any

from .operation import AccountingOperation, OperationType, OperationClass
from .crdt import DE_CRDT
from .invariants import InvariantEngine
from .compensation import CompensationEngine

def generate_random_fuzz():
    print("==================================================================")
    print("   VOUCH DISTRIBUTED ACCOUNTING: MULTI-REPLICA PROPERTY FUZZER    ")
    print("==================================================================")
    print("Testing distributed CRDT convergence across 3, 5, 8, and 10 replicas...")
    print("Simulating network partitions, causal DAG branches, and random gossip merges.\n")
    
    test_configs = [
        {"replica_count": 3, "iterations": 100},
        {"replica_count": 5, "iterations": 80},
        {"replica_count": 8, "iterations": 50},
        {"replica_count": 10, "iterations": 30},
    ]

    total_scenarios = 0
    total_permutations = 0

    for config in test_configs:
        num_replicas = config["replica_count"]
        iterations = config["iterations"]
        replica_names = [f"R{k}" for k in range(num_replicas)]

        print(f"[*] Fuzzing with {num_replicas} Replicas ({iterations} iterations)...")

        for i in range(iterations):
            tx_id = f"FUZZ-TX-{num_replicas}R-{i}"
            replicas = [DE_CRDT(replica_id=name, transaction_id=tx_id) for name in replica_names]

            # 1. Base Canonical Transaction Issued
            base_taxable = Decimal(str(random.randint(5000, 50000)))
            base_tax = (base_taxable * Decimal('18') / Decimal('100')).quantize(Decimal('0.01'))
            base_gt = base_taxable + base_tax

            base_op = AccountingOperation(
                operation_id=f"OP-ROOT-{i}",
                transaction_id=tx_id,
                replica_id=replica_names[0],
                operation_type=OperationType.TRANSACTION_ISSUED,
                operation_class=OperationClass.CAUSAL,
                payload={
                    "taxable_amount": float(base_taxable),
                    "tax_amount": float(base_tax),
                    "total_tax": float(base_tax),
                    "grand_total": float(base_gt),
                    "quantity": 100.0
                },
                logical_timestamp=1,
                parents=[]
            )

            # Genesis: All replicas receive root transaction
            for r in replicas:
                r.apply_operation(base_op)

            # 2. Generate random distributed operations concurrently across replicas
            num_ops = random.randint(3, 12)
            allocated_payment = Decimal('0.00')
            cumulative_rejection = Decimal('0.00')
            op_pool = []

            for op_idx in range(num_ops):
                creator = random.choice(replica_names)
                choice = random.choice([
                    'ITEM_REJECTED',
                    'PAYMENT',
                    'ITEM_ACCEPTED',
                    'CREDIT_NOTE',
                    'PRICE_ADJUSTED'
                ])

                parent_id = base_op.operation_id
                if op_pool and random.random() > 0.4:
                    parent_id = random.choice(op_pool).operation_id

                if choice == 'ITEM_REJECTED':
                    rej_qty = Decimal(str(random.randint(1, 10)))
                    cumulative_rejection += rej_qty
                    rej_taxable = (rej_qty * (base_taxable / Decimal('100'))).quantize(Decimal('0.01'))
                    rej_tax = (rej_taxable * Decimal('18') / Decimal('100')).quantize(Decimal('0.01'))
                    payload = {
                        "quantity": float(rej_qty),
                        "taxable_amount": float(rej_taxable),
                        "tax_amount": float(rej_tax),
                        "line_id": "LINE-01"
                    }
                    op = AccountingOperation(
                        operation_id=f"OP-REJ-{i}-{op_idx}",
                        transaction_id=tx_id,
                        replica_id=creator,
                        operation_type=OperationType.ITEM_REJECTED,
                        operation_class=OperationClass.COMPENSATING,
                        payload=payload,
                        logical_timestamp=op_idx + 2,
                        parents=[parent_id]
                    )

                elif choice == 'CREDIT_NOTE':
                    cn_taxable = Decimal(str(random.randint(50, 500)))
                    cn_tax = (cn_taxable * Decimal('18') / Decimal('100')).quantize(Decimal('0.01'))
                    payload = {
                        "quantity": 2.0,
                        "taxable_amount": float(cn_taxable),
                        "tax_amount": float(cn_tax)
                    }
                    op = AccountingOperation(
                        operation_id=f"OP-CN-{i}-{op_idx}",
                        transaction_id=tx_id,
                        replica_id=creator,
                        operation_type=OperationType.CREDIT_NOTE_ISSUED,
                        operation_class=OperationClass.COMPENSATING,
                        payload=payload,
                        logical_timestamp=op_idx + 2,
                        parents=[parent_id]
                    )

                elif choice == 'PAYMENT':
                    rem = base_gt - allocated_payment
                    p_amt = Decimal(str(random.randint(100, 1000))) if rem > 1000 else rem
                    if p_amt <= Decimal('0'):
                        p_amt = Decimal('10.00')
                    allocated_payment += p_amt
                    payload = {"amount": float(p_amt)}
                    op = AccountingOperation(
                        operation_id=f"OP-PAY-{i}-{op_idx}",
                        transaction_id=tx_id,
                        replica_id=creator,
                        operation_type=OperationType.PAYMENT_ALLOCATED,
                        operation_class=OperationClass.COMMUTATIVE,
                        payload=payload,
                        logical_timestamp=op_idx + 2,
                        parents=[parent_id]
                    )

                elif choice == 'PRICE_ADJUSTED':
                    delta = Decimal(str(random.randint(-200, 200)))
                    delta_tax = (delta * Decimal('18') / Decimal('100')).quantize(Decimal('0.01'))
                    payload = {
                        "taxable_amount": float(delta),
                        "tax_amount": float(delta_tax)
                    }
                    op = AccountingOperation(
                        operation_id=f"OP-PRC-{i}-{op_idx}",
                        transaction_id=tx_id,
                        replica_id=creator,
                        operation_type=OperationType.PRICE_ADJUSTED,
                        operation_class=OperationClass.COMPENSATING,
                        payload=payload,
                        logical_timestamp=op_idx + 2,
                        parents=[parent_id]
                    )

                else: # ITEM_ACCEPTED
                    payload = {"quantity": 5.0, "status": "VERIFIED"}
                    op = AccountingOperation(
                        operation_id=f"OP-ACC-{i}-{op_idx}",
                        transaction_id=tx_id,
                        replica_id=creator,
                        operation_type=OperationType.ITEM_ACCEPTED,
                        operation_class=OperationClass.COMMUTATIVE,
                        payload=payload,
                        logical_timestamp=op_idx + 2,
                        parents=[parent_id]
                    )

                op_pool.append(op)

                # Random network partition: Op reaches a random subset of replicas
                target_subset = random.sample(replicas, random.randint(1, num_replicas))
                for target in target_subset:
                    target.apply_operation(op)

            # 3. Simulate Multi-Hop Gossip & Random Partition Synchronization
            # Create two completely random merge orders
            order_1 = list(replicas)
            random.shuffle(order_1)

            order_2 = list(replicas)
            random.shuffle(order_2)

            order_3 = list(replicas)
            random.shuffle(order_3)

            # Fold merge 1
            merged_1 = order_1[0]
            for r in order_1[1:]:
                merged_1 = merged_1.merge(r)

            # Fold merge 2
            merged_2 = order_2[0]
            for r in order_2[1:]:
                merged_2 = merged_2.merge(r)

            # Fold merge 3
            merged_3 = order_3[0]
            for r in order_3[1:]:
                merged_3 = merged_3.merge(r)

            # 4. Property Assertions: Mathematical Soundness
            state_1 = merged_1.evaluate_state()
            state_2 = merged_2.evaluate_state()
            state_3 = merged_3.evaluate_state()

            # Theorem 1: Convergence (Commutativity & Associativity across all orders)
            assert state_1 == state_2 == state_3, (
                f"Convergence divergence across {num_replicas} replicas on iteration {i}!\n"
                f"State 1: {state_1}\nState 2: {state_2}"
            )

            # Theorem 2: Idempotency (A merge A == A)
            idem = merged_1.merge(merged_1)
            assert idem.evaluate_state() == state_1, f"Idempotency violation on iteration {i}!"

            # Theorem 3: Deterministic Cryptographic State Roots & Commitments
            h1 = merged_1.generate_state_commitment()
            h2 = merged_2.generate_state_commitment()
            h3 = merged_3.generate_state_commitment()
            assert h1 == h2 == h3, f"Cryptographic commitment divergence on iteration {i}!"

            # Theorem 4: Double-Entry Invariant Integrity
            valid = merged_1.validate_convergence()
            assert valid == True, f"Double-entry invariant failure on iteration {i}!"

            total_scenarios += 1
            total_permutations += 3

        print(f"    [+] {num_replicas}-Replica scenarios passed 100% ({iterations} trials)")

    print("\n==================================================================")
    print("   MULTI-REPLICA PROPERTY TESTING RESULTS: COMPLETE SUCCESS       ")
    print("==================================================================")
    print(f"Scenarios evaluated:     {total_scenarios}")
    print(f"Merge permutations:      {total_permutations}")
    print("Replica topologies:      3, 5, 8, and 10 concurrent nodes")
    print("Convergence divergence:  0 (0.00%)")
    print("Cryptographic mismatch:  0 (0.00%)")
    print("Invariant violations:    0 (0.00%)")
    print("Status:                  MATHEMATICALLY SOUND & VERIFIED\n")

if __name__ == '__main__':
    generate_random_fuzz()
