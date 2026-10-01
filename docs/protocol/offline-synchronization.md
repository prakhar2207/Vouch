# Protocol Specification: Offline Synchronization Layer

**Version:** 1.0.0
**Phase:** 6 (Network & Synchronization)

## Abstract
The Offline Synchronization Layer governs how disconnected Replicas (such as a Vouch PWA Service Worker operating without internet) transmit their local changes to the central network and achieve convergence. 

Crucially, **the protocol does not synchronize databases.** It only transmits mathematical deltas (the `AccountingOperations`), drastically reducing network bandwidth and preventing standard "last-write-wins" data corruption.

## The Synchronization Lifecycle

### 1. Offline Operation (Client-Side)
When a user modifies a transaction while offline (e.g., rejecting an item), the frontend application evaluates the semantic delta and generates a Compensating `AccountingOperation`. This operation is strictly appended to the browser's IndexedDB (via Dexie) in an `Outbox` table.

### 2. Network Restoration & Handshake
When the Service Worker detects network connectivity, it initiates a Sync Handshake with the server, transmitting only the array of pending `AccountingOperations` for the given `transaction_id`.

### 3. Server-Side Ingestion & Merge
1. The Server loads its own authoritative CRDT graph for the transaction.
2. The Server iterates through the Client's operations, discarding duplicates based on `operation_id` (Idempotency Guarantee).
3. The Server executes `ServerCRDT.merge(ClientCRDT)`.
4. The Server evaluates the accounting invariants. If the client's operations result in mathematical impossibility (e.g., rejecting an item that was never invoiced), the sync is rejected and the client is forced to rollback.
5. If valid, the operations are committed to the Server's database.

### 4. 2-Way Reconciliation
To complete the sync, the Server compares the merged graph to the Client's payload and returns any operations that occurred on the server (e.g., a counterparty payment) that the Client is missing. The Client applies these to its local IndexedDB, perfectly synchronizing both devices to the same Cryptographic State Commitment.
