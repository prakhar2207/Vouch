# Protocol Specification: Threat Model & Security Hardening

**Version:** 1.0.0
**Phase:** 11 (Security Layer)

## Abstract
The Vouch Distributed Accounting Convergence Protocol operates in zero-trust environments where network payloads, QR matrices, and offline storage may be intercepted, manipulated, or replayed by malicious actors. This document formalizes the deterministic mitigations engineered into the protocol.

## Threat Model & Mitigations

### 1. Tampering (Amount/Data Modification)
* **Threat:** A malicious proxy alters an invoice amount from ₹1,000 to ₹10,000 in transit.
* **Mitigation:** Enforced at two layers. 
  1. `AccountingOperation` dataclasses are strictly frozen (`@dataclass(frozen=True)`). 
  2. The `CrossLedgerCommitment` securely hashes the `operation_state_root` and is sealed by an Asymmetric Digital Signature (Ed25519). If a single bit is flipped, the signature verification fails and the EDI Handshake instantly aborts at the `AUTHENTICATE` step.

### 2. Replay Attacks
* **Threat A (Session Replay):** An attacker scans an old Dynamic QR code to open an unauthorized EDI handshake.
* **Mitigation A:** `QRSessionManager` strictly validates the ephemeral `nonce` against a consumed cache and enforces the `expires_at` Unix timestamp.
* **Threat B (Operation Replay):** An attacker resends a valid `PAYMENT_ALLOCATED` operation multiple times to artificially inflate balances.
* **Mitigation B:** `DE_CRDT.apply_operation()` evaluates `operation_id`. Because CRDT merges are mathematically idempotent ($Merge(A, A) = A$), replaying the same operation 1,000 times results in exactly 1 state change.

### 3. State-Skipping & Handshake Hacks
* **Threat:** A malicious node attempts to bypass validation by jumping directly from `PROPOSE` to `COMMIT`.
* **Mitigation:** The `EdiStateMachine` (Phase 8) maps a rigid topology. Illegal transitions throw an `IllegalStateTransitionError` and immediately force a `ROLLBACK_REQUIRED` terminal state.

### 4. Cross-Tenant Leakage
* **Threat:** A user logged into Tenant B attempts to merge an operation belonging to Tenant A.
* **Mitigation:** Every operation fundamentally binds to `transaction_id` and `replica_id`. The Canonical Schema maps explicit `source_entity` and `destination_entity` GSTINs. The `CrossLedgerCommitment` explicitly hashes the `seller_identity` and `buyer_identity`. Merging a foreign operation inherently produces a completely invalid hash that the target tenant's private key will refuse to sign.

### 5. Identity & SKU Substitution
* **Threat:** An attacker manipulates the mapping to swap a ₹500 product for a ₹50,000 product.
* **Mitigation:** The `MappingResolutionEngine` (Phase 10) binds translations to a `mapping_version` that is locked at the time of transaction creation. Furthermore, ML predictions cannot bypass the `PENDING` state without explicit cryptographic approval.

### 6. Invalid Accounting State Injection
* **Threat:** A malicious node mathematically corrupts an operation payload (e.g., deducting Inventory without crediting Accounts Payable).
* **Mitigation:** The `InvariantEngine` (Phase 3) acts as the final gatekeeper. The system calculates the projected mathematical state of the CRDT and runs proofs against it. Unbalanced operations trigger an `AccountingInvariantViolation` and the transaction is aborted before touching the database.
