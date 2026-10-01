# Categorization of Novel Mechanisms & Architectural Status

This document explicitly distinguishes between mechanisms that were already present in the baseline Vouch application, mechanisms newly implemented in the protocol architecture, and future conceptual mechanisms.

---

## 1. ALREADY EXISTING (Pre-Protocol Baseline in Vouch)
* **Double-Entry Ledger Engine:** Posting voucher records into debit/credit `LedgerEntry` tables (`apps/accounting/`).
* **Indian GST Tax Engine:** Calculation of CGST, SGST, IGST, HSN lookup, and GSTR reporting (`apps/gst/`).
* **Basic EDI Document Dispatch:** The legacy `EDIService.create_inward_request_for_sales_voucher` and `accept_inward_request` sending static JSON snapshots between companies.
* **Invoice PDF & Report Generation:** ReportLab and HTML renderers for invoices and statements (`apps/documents/`).
* **Multi-tenant Company Partitioning:** Foreign keys on `Company` across models (`apps/companies/`).

---

## 2. NEWLY IMPLEMENTED (The Technical Invention)

### Mechanism 1: Immutable Accounting Operation Model & Taxonomy
* **File:** `apps/protocol/operation.py`
* **Novelty:** Complete departure from database mutation synchronization. Formal taxonomy of operation classes (`COMMUTATIVE`, `CAUSAL`, `COMPENSATING`, `FINALIZING`, `REVERSAL`). In-memory immutability locking via recursive `ReadOnlyDict` and canonical SHA-256 node digests.

### Mechanism 2: Causal Operation Directed Acyclic Graph (DAG) with Orphan Quarantine
* **File:** `apps/protocol/causal_dag.py`
* **Novelty:** Replaces linear timestamp ordering with a causal DAG. Operations cannot execute until causal parent dependencies are satisfied. Disconnected/out-of-order deliveries are quarantined in an orphan buffer and automatically promoted upon parent arrival. Deterministic topological sorting via Kahn's algorithm.

### Mechanism 3: Double-Entry CRDT (DE-CRDT) Merge Engine
* **File:** `apps/protocol/crdt.py`
* **Novelty:** Specialized accounting CRDT mathematically proven to satisfy commutativity ($\text{Merge}(A,B) == \text{Merge}(B,A)$), associativity, and idempotency across chaotic network reconnects.

### Mechanism 4: Deterministic Semantic Delta & Reciprocal Compensation Engine
* **Files:** `apps/protocol/semantic_delta.py`, `apps/protocol/compensation.py`
* **Novelty:** Calculates multi-variable economic deltas ($\Delta\text{qty}, \Delta\text{taxable}, \Delta\text{tax}, \Delta\text{AR}, \Delta\text{stock}$) and deterministically generates balanced compensating operations ($F(\Delta)$). Automatically derives reciprocal counterparty operations (e.g. Seller Credit Note derived from Buyer Rejection) with explicit causal parentage.

### Mechanism 5: Multi-Variable Invariant Gatekeeper
* **File:** `apps/protocol/invariants.py`
* **Novelty:** Mathematical gatekeeper enforcing five invariant conservation laws (double-entry equality, invoice algebra, GST component decomposition, inventory conservation, and payment non-over-allocation) prior to database persistence.

### Mechanism 6: 4-Way Merkle Cross-Ledger State Commitment ($C_n$) & Ed25519 Interlock
* **File:** `apps/protocol/crypto.py`
* **Novelty:** Derives four discrete Merkle trees ($O_n, L_n, I_n, T_n$) representing operations, ledgers, inventory, and baseline transaction lines. Chained commitment hash $C_n = H( \text{TxID} \parallel T_n \parallel O_n \parallel L_n \parallel I_n \parallel S_n \parallel B_n \parallel C_{n-1} \parallel V_n )$ countersigned with Ed25519 asymmetric keypairs.

### Mechanism 7: Ephemeral Dynamic QR Bootstrap & 11-State Handshake
* **Files:** `apps/protocol/qr_bootstrap.py`, `apps/protocol/handshake.py`
* **Novelty:** Ephemeral session initialization preventing replay attacks using cache-backed atomic nonces, driving an 11-state transition state machine (`DISCOVER` to `COMMITTED`).

---

## 3. CONCEPTUAL / FUTURE
* **Zero-Knowledge Tax Proofs (ZKP):** Proving GST compliance to tax authorities without revealing confidential counterparty pricing (conceptual; not required for core convergence).
* **Automated Machine-Learning Ontology Alignment:** Fully unsupervised HSN/SKU semantic alignment with continuous Bayesian retraining (future enhancement).
* **Hardware Security Module (HSM) Key Management:** Cloud KMS / hardware token storage for enterprise Ed25519 private keys (production deployment consideration).
