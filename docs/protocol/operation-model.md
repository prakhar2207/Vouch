# Protocol Specification: Operation Model

**Version:** 1.0.0
**Phase:** 2 (State Transition Layer)

## Abstract
The Operation Model shifts Vouch from a traditional CRUD (Create-Read-Update-Delete) synchronization engine to an **append-only Event Sourcing** architecture. Instead of synchronizing arbitrary database row mutations (e.g., `UPDATE invoice SET quantity=8`), the protocol exclusively synchronizes immutable *Accounting Operations*.

This causally ordered operation graph forms the basis for the Conflict-Free Replicated Data Type (DE-CRDT).

## 1. Supported Operation Types (`OperationType`)
To ensure determinism, all modifications to a transaction must fall into a strict ontology:

* `TRANSACTION_ISSUED`: Bootstraps the causal graph with the `CanonicalTransaction`.
* `ITEM_ACCEPTED` / `ITEM_REJECTED`: Counterparty acceptance workflows.
* `QUANTITY_ADJUSTED` / `PRICE_ADJUSTED`: Line-item modifications.
* `TAX_ADJUSTED`: Tax rate or amount corrections.
* `PAYMENT_ALLOCATED`: Linking a payment receipt to the transaction.
* `CREDIT_NOTE_ISSUED` / `DEBIT_NOTE_ISSUED`: Formal accounting adjustments.
* `VOUCHER_CANCELLED`: Complete invalidation of the transaction.

## 2. Canonical Operation Schema (JSON)

```json
{
  "operation_id": "OP-7F82A1",
  "transaction_id": "TX-9A8B7C6D5E",
  "replica_id": "BUYER-42",
  "operation_type": "ITEM_REJECTED",
  "payload": {
    "line_id": "L-001",
    "quantity_rejected": 2.0,
    "reason": "Damaged in transit"
  },
  "parents": ["OP-001"],
  "logical_timestamp": 183829,
  "version": 1,
  "payload_hash": "a1b2c3d4e5f6...",
  "signature": "sig_..."
}
```

## 3. Structural Guarantees
1. **Immutability:** Once an operation is created and signed, it can never be mutated. Any correction requires a new `AccountingOperation` (e.g. compensating operation).
2. **Deterministic Hashing:** The `payload_hash` is calculated by converting the fields into a strictly ordered, minified JSON string and hashing it via SHA-256. This guarantees that Replica A and Replica B generate the exact same hash for the exact same semantic intent.
3. **Causal Ordering (DAG):** Operations declare their dependencies in the `parents` array. A `PAYMENT_ALLOCATED` operation cannot be committed if its parent `TRANSACTION_ISSUED` operation is missing from the local graph.
