# Patent Evidence: Invention Disclosure
**Title:** Distributed Accounting Convergence Protocol (DE-CRDT) with Authoritative Dual Ledger Bridging  
**Filing Orientation:** Indian Patent Application (Subject to Prior-Art Search & Patent Counsel)  
**Date:** October 2026

---

## 1. The Technical Problem
Conventional enterprise accounting systems utilize centralized relational databases with synchronous CRUD semantics. When adapted for B2B Electronic Data Interchange (EDI), e-invoicing, or offline Progressive Web Apps (PWAs), they suffer from severe technical limitations:
1. **Unresolvable Race Conditions:** If both Seller and Buyer work offline (e.g. Seller adds a delivery charge while Buyer records a damaged item return), classical "Last-Write-Wins" (LWW) overwrites one party's legal accounting record.
2. **Double-Entry Invariant Violations:** Distributed merges across independent accounting systems frequently violate fundamental conservation laws ($\sum \text{Debits} \ne \sum \text{Credits}$).
3. **Duplicate Accounting Engines:** Naive distributed systems reproduce simplified accounting math inside the synchronization protocol, eventually diverging from the ERP's authoritative tax, stock, and ledger engine.
4. **Lack of Cryptographic Non-Repudiation:** Traditional relational databases allow unilateral back-dated editing of invoices without producing mathematical proof of tampering.

---

## 2. The Technical Solution
The invention provides an integrated, mathematically proved distributed accounting architecture:
1. **Single Source of Truth / Operational DAG:** Replaces row-level overwrites with an immutable Causal DAG of atomic `AccountingOperation` records.
2. **Double-Entry CRDT (DE-CRDT):** Formulates a join-semilattice $(S, \sqcup)$ guaranteeing commutativity, associativity, and idempotency across arbitrary gossip network topologies.
3. **Decoupled Architecture with Authoritative Ledger Bridge:** The protocol does NOT maintain an independent accounting engine; it produces canonical operations which the host ERP's authoritative engine (`VoucherService`, `StockService`, `GSTCalculator`) executes.
4. **Automated Semantic Compensation:** Automatically transforms transaction discrepancies into reciprocal, balanced accounting adjustments (`CREDIT_NOTE_ISSUED` / `DEBIT_NOTE_ISSUED`) that converge on both nodes.
5. **4-Way Merkle State Roots & Dual Counter-Signing:** Derives independent cryptographic state roots for Seller Ledgers ($L_{\text{seller}}$), Seller Inventory ($I_{\text{seller}}$), Buyer Ledgers ($L_{\text{buyer}}$), and Buyer Inventory ($I_{\text{buyer}}$), bound in a chained Cross-Ledger Commitment ($C_n$) counter-signed with Ed25519.
6. **Offline-First PWA Contract:** Implements client-side IndexedDB operation logs, outbox queues, inbox queues, and causal cursors for reliable disconnected operation.

---

## 3. Measurable Technical Effects
1. **89.62% Bandwidth Reduction:** Empirical benchmarks prove that transmitting atomic operations requires only 652 bytes compared to 6,279 bytes for traditional full-document JSON synchronization.
2. **Sub-20 Microsecond Convergence:** CRDT topological merge and state projection executes in 17.54 microseconds, sustaining over 57,000 merges per second per CPU core.
3. **0.00% Divergence Across 780 Permutations:** Multi-replica property fuzzing across 3, 5, 8, and 10 nodes verified 0% divergence and 0 invariant violations under arbitrary network partitions.
4. **Instantaneous Replay & Tamper Detection:** Deduplication and replay rejection executes in 0.13 microseconds; Merkle tamper detection executes in 167.70 microseconds.

---

## 4. Delineation of Architecture

### Already Existing in Vouch:
* Double-entry ledger architecture, vouchers, and chart of accounts.
* Authoritative GST engine (`GSTCalculator`) with intra-state vs inter-state rules.
* Standard PWA manifest and caching service workers.

### Newly Implemented by the Invention:
* Canonical Transaction Envelope (`apps/protocol/schema.py`).
* Causal DAG and DE-CRDT Join-Semilattice (`apps/protocol/crdt.py`, `causal_dag.py`).
* Automated Reciprocal Compensation Engine (`apps/protocol/compensation.py`).
* Production-Grade Idempotent Ledger Bridge (`apps/protocol/bridge.py`).
* 4-Way Merkle Subsystem Roots and Dual Ed25519 Cross-Ledger Commitment (`apps/protocol/crypto.py`).
* Key Manager with rotation, revocation, and replay sliding window (`apps/protocol/key_manager.py`).
* Bounded Multi-Tier Semantic SKU Mapping Engine (`apps/protocol/mapping.py`).
* Frontend IndexedDB Outbox/Inbox Operation Log (`frontend/src/lib/crdt/clientOperationManager.ts`).
* Crash-Safe EDI Session and Bridge Audit Persistence (`apps/protocol/models.py`).

---

## 5. Formal Specification Reference Index
* **System Architecture:** [system-architecture.md](system-architecture.md)
* **CRDT Algorithm & Proofs:** [crdt-algorithm.md](crdt-algorithm.md)
* **Semantic Compensation Calculus:** [semantic-compensation.md](semantic-compensation.md)
* **State Roots & Cryptographic Commitments:** [state-roots-and-commitments.md](state-roots-and-commitments.md)
* **Empirical Benchmarks & Experiments:** [benchmarks-and-experiments.md](benchmarks-and-experiments.md)
