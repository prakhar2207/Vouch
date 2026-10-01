# Protocol Specification: Double-Entry CRDT (DE-CRDT)

**Version:** 1.0.0
**Phase:** 4 (State Resolution Layer)

## Abstract
The Double-Entry Conflict-Free Replicated Data Type (DE-CRDT) is the core algorithmic invention of the Vouch Protocol. It provides a deterministic mathematical structure for two or more independent accounting systems to modify a shared transaction offline, merge their operation graphs upon reconnection, and reliably converge to an identical, mathematically valid accounting state.

## Mathematical Properties
To satisfy distributed system requirements, the DE-CRDT guarantees:
1. **Commutativity:** `Merge(ReplicaA, ReplicaB) == Merge(ReplicaB, ReplicaA)`
2. **Idempotence:** `Merge(ReplicaA, ReplicaA) == ReplicaA`
3. **Associativity:** `Merge(ReplicaA, Merge(ReplicaB, ReplicaC)) == Merge(Merge(ReplicaA, ReplicaB), ReplicaC)`

## The Merge & Validation Algorithm
When `ReplicaA` syncs with `ReplicaB`:
1. **Operation Union:** The engine calculates the union of both operation graphs based on deterministic `operation_id` deduplication.
2. **Causal Sort:** The operations are ordered topologically based on their `logical_timestamp` and explicit `parents` dependencies.
3. **State Projection:** The engine executes the operations sequentially to calculate the intermediate monetary values (Debits, Credits, Tax, Inventory).
4. **Invariant Validation:** The projected state is passed to the `InvariantEngine`.
5. **Commitment (Phase 7):** If invariants pass, the state is finalized and ready for Cryptographic Commitment.
