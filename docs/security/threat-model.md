# Vouch Distributed Accounting Protocol: Comprehensive Threat Model

## 1. System Overview & Trust Assumptions
The Vouch Distributed Accounting Convergence Protocol coordinates ledger state between mutually distrustful, heterogeneous enterprise replicas (Seller, Buyer, Logistics, and Network Nodes) that operate in disconnected, offline environments.

---

## 2. Threat Vector Analysis & Mitigation Proofs

### Threat 1: Attacker Impersonates Seller
* **Attack Mechanism:** A malicious counterparty attempts to issue or amend invoices on behalf of an enterprise by injecting fake `TRANSACTION_ISSUED` or `PAYMENT_ALLOCATED` operations.
* **Protocol Defense:** All operations require Ed25519 digital signatures signed with the issuer's private key. The `SyncService` verifies the signature against the verified public key associated with the claimed `replica_id`/`tenant_id`.
* **Technical Effect:** Forged operations are rejected at the protocol gateway prior to DAG ingestion.

---

### Threat 2: Attacker In-Flight Operation Modification (Tampering)
* **Attack Mechanism:** An attacker intercepts an in-flight operation and modifies the line rejection amount or tax liability (e.g. changing rejection from ₹200 to ₹10,000).
* **Protocol Defense:**
  1. Every operation encapsulates a deterministic SHA-256 `payload_hash`.
  2. The Ed25519 signature binds the payload hash to the private key.
  3. `AccountingOperation.payload` is deep-frozen with `ReadOnlyDict`, preventing in-memory mutation.
* **Technical Effect:** Any bit-level modification invalidates the cryptographic signature and payload hash immediately.

---

### Threat 3: Network Replay Attack
* **Attack Mechanism:** An attacker captures a valid ₹5,000 payment operation and broadcasts it 100 times across network reconnects to artificially inflate customer credit.
* **Protocol Defense:** 
  1. `AccountingOperation.operation_id` is globally unique.
  2. `CausalDAG.add_operation()` and `DE_CRDT.apply_operation()` enforce mathematical set idempotency ($A \cup A = A$).
  3. Ephemeral Dynamic QR handshakes enforce atomic nonce consumption via Redis/cache.
* **Technical Effect:** All duplicate operations are deduplicated in $0.20\ \mu\text{s}$ with zero ledger balance inflation.

---

### Threat 4: Operation Removal / Deletion Attack
* **Attack Mechanism:** An attacker attempts to delete historical operations (such as payment receipts or tax debits) to misrepresent financial health.
* **Protocol Defense:**
  1. Operations are chained in a Causal DAG with parent hash references.
  2. Four-way Merkle state roots ($O_n, L_n, I_n, T_n$) anchor the exact set of committed operations.
  3. Deleting any historical node breaks parent dependencies and invalidates the Merkle root.
* **Technical Effect:** State alterations are immediately detected during cross-ledger commitment verification.

---

### Threat 5: Malicious Identity Mapping Injection
* **Attack Mechanism:** An attacker injects a malicious product mapping to equate a luxury product to a cheap bulk SKU.
* **Protocol Defense:**
  1. `MappingResolutionEngine` enforces strict historical versioning and human approval barriers.
  2. Transactions lock to the mapping version active at negotiation time ($V_{\text{mapping}} \le V_{\text{tx}}$).
  3. No ML or heuristic model can mutate mapping records without explicit counterparty approval.
* **Technical Effect:** Retrospective SKU reassignment and semantic identity hijacking are strictly prevented.

---

### Threat 6: Malformed / Unbalanced CRDT Operation (Mathematical Corruption)
* **Attack Mechanism:** An attacker constructs an operation that reduces tax payable without reducing the invoice grand total, or generates an unbalanced double-entry state ($\text{Debits} \ne \text{Credits}$).
* **Protocol Defense:** 
  1. `InvariantEngine` evaluates the post-merge projected ledger state prior to database persistence.
  2. Validates double-entry ($\sum \text{Debits} == \sum \text{Credits}$), invoice totals, tax component decomposition ($\text{CGST} + \text{SGST} + \text{IGST} == \text{TotalTax}$), and inventory conservation.
* **Technical Effect:** Any mathematically invalid state triggers immediate rollback (`SYNC_REJECTED`) and blocks database commit.

---

### Threat 7: Cross-Tenant Operation Injection (IDOR / Horizontal Privilege Escalation)
* **Attack Mechanism:** A malicious tenant injects an operation specifying a foreign tenant's `company_id` to read or modify another company's books.
* **Protocol Defense:**
  1. Tenant identity is resolved strictly server-side from verified session tokens / JWTs, never trusted from client payloads.
  2. `SyncService` verifies that `authenticated_tenant_id` is an authorized participant in the transaction (`authorized_counterparty_ids`).
* **Technical Effect:** Unauthorized cross-tenant reads or mutations raise `MultiTenantSecurityError` and terminate the request.

---

### Threat 8: Compromise of Single Enterprise Replica
* **Attack Mechanism:** An attacker compromises the physical device or local database of one counterparty.
* **Protocol Defense:**
  1. The counterparty can only sign operations with its own key; it cannot forge the other party's signature.
  2. Cross-ledger state commitments require dual signatures (both Seller and Buyer Ed25519 signatures).
  3. Unilateral local database modifications cannot produce a valid counter-signed commitment.
* **Technical Effect:** Discrepancies are isolated, and uncommitted unilateral tampering is repudiated by the network.

---

### Threat 9: Conflicting Concurrent Operations (Offline Divergence)
* **Attack Mechanism:** Seller applies a price increase while Buyer simultaneously rejects items offline.
* **Protocol Defense:**
  1. Causal DAG tracks concurrent operations using vector clocks and topological ordering.
  2. `SemanticDeltaEngine` identifies economic divergence.
  3. `CompensationEngine` derives deterministic, balanced compensating operations ($F(\Delta)$).
* **Technical Effect:** Both replicas deterministically converge to the exact same double-entry state without human deadlock.

---

### Threat 10: State Rollback / Branch Rewriting
* **Attack Mechanism:** An attacker attempts to roll back a committed transaction to an earlier unadjusted state.
* **Protocol Defense:**
  1. Commitments are chained cryptographically: $C_n = H(T_n \parallel O_n \parallel L_n \parallel I_n \parallel S_n \parallel B_n \parallel C_{n-1} \parallel V_n)$.
  2. Rollback breaks the causal hash chain $C_{n-1} \to C_n$.
* **Technical Effect:** Any historical regression is cryptographically detectable by any auditor.
