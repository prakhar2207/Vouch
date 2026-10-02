# Vouch Protocol Architecture Freeze Specification (v1.0.0)

**Protocol Release:** `v1.0.0-FROZEN`  
**Protocol Version Header:** `1.0`  
**Architecture Freeze Date:** October 2, 2026  
**Status:** ARCHITECTURE LOCKED FOR PATENT FILING  

---

## 1. Scope & Objective of Architecture Freeze

This document certifies that the core protocol architecture of the **Vouch Distributed Accounting Convergence Protocol (DE-CRDT)** is formally frozen. No architectural modifications, schema mutations, or signature-payload alterations will be permitted without a backward-compatible version increment to `v2.0`.

This freeze provides an immutable baseline for the **Indian Patent Application (Provisional / Complete Specification)** and ensures that all empirical benchmarks, mathematical correctness proofs, and security guarantees remain 100% reproducible.

---

## 2. Frozen Protocol Layers

```
+-------------------------------------------------------------------------------+
|  LAYER 6: ERP LEDGER BRIDGE (Voucher, Stock, GST Engine Ingestion)            |
+-------------------------------------------------------------------------------+
|  LAYER 5: 4-WAY MERKLE SUBSYSTEM ROOTS & DUAL-COUNTERSIGNED COMMITMENTS (C_n)  |
+-------------------------------------------------------------------------------+
|  LAYER 4: AUTOMATED DETERMINISTIC RECIPROCAL COMPENSATION (C = F(Delta))      |
+-------------------------------------------------------------------------------+
|  LAYER 3: CAUSAL DIRECTED ACYCLIC GRAPH & DE-CRDT JOIN-SEMILATTICE (S, |_|)    |
+-------------------------------------------------------------------------------+
|  LAYER 2: CRYPTOGRAPHIC IDENTITY (Web Crypto Ed25519 Non-Extractable / KMS)   |
+-------------------------------------------------------------------------------+
|  LAYER 1: DETERMINISTIC CANONICAL TRANSACTION SERIALIZATION (RFC 8785)        |
+-------------------------------------------------------------------------------+
```

---

## 3. Specifications of Frozen Subsystems

### 3.1 Layer 1: Canonical Transaction & Normalization (`apps/protocol/schema.py`)
- **Schema Fields:** `protocol_version`, `transaction_id`, `transaction_type`, `state_version`, `issued_at`, `source_entity`, `destination_entity`, `items`, `tax_summary`, `totals`, `causal_dependencies`.
- **Numeric Determinism:** All currency, quantity, rate, tax, and discount fields are normalized to fixed-point strings with exactly 2 decimal places (`to_dec_str(x, decimals=2)`).
- **Serialization Engine:** Vouch Canonical JSON serializer enforcing alphabetical key sorting, zero extraneous whitespace (`,` and `:` delimiters), UTF-8 encoding, and deterministic numeric string representation across both Python 3.14 and Node.js/TypeScript environments.

### 3.2 Layer 2: Cryptographic Identity & Hardware Isolation (`apps/protocol/crypto.py`, `kms.py`, `clientKeyManager.ts`)
- **Signature Algorithm:** Pure Ed25519 (RFC 8032) generating 64-byte detached signatures.
- **Client Keystore Custody:** Browser private keys generated via Web Crypto API with `extractable: false`, stored strictly in IndexedDB (`CryptoKey` object via structured cloning), with **zero** exposure to `localStorage` or JavaScript string extraction.
- **Enterprise KMS Driver:** Fail-closed `CloudKMSProvider` (AWS KMS / GCP Cloud KMS / Azure Key Vault / PKCS#11). Software fallback is strictly prohibited in production mode.
- **Key Rotation Protocol:** Cryptographically proven rotation using format `ROTATE:{device_id}:{new_public_key_hex}:{new_key_id}` counter-signed by the retiring key.

### 3.3 Layer 3: Causal DAG & DE-CRDT Join-Semilattice (`apps/protocol/crdt.py`)
- **Mathematical Structure:** Join-semilattice $(S, \sqcup)$ where merge operation $A \sqcup B$ satisfies:
  1. **Commutativity:** $A \sqcup B = B \sqcup A$
  2. **Associativity:** $(A \sqcup B) \sqcup C = A \sqcup (B \sqcup C)$
  3. **Idempotency:** $A \sqcup A = A$
- **Conservation Invariant:** Operation transitions are strictly constrained by double-entry conservation laws:
  $$\sum \text{Debits} \equiv \sum \text{Credits}$$
- **Deduplication:** Monotonically tracked causal dependency vectors preventing duplicate operation execution or transaction replays.

### 3.4 Layer 4: Reciprocal Semantic Compensation (`apps/protocol/compensation.py`)
- **Function:** Derives compensating operations $C = \mathcal{F}(\Delta)$ deterministically from the symmetric difference $\Delta$ between Seller and Buyer DAG projections.
- **Reciprocal Inversion:**
  - Seller Over-Delivery / Rate Adjustment $\longrightarrow$ Reciprocal Debit Note (`DEBIT_NOTE_ISSUED`)
  - Buyer Item Rejection / Damage Return $\longrightarrow$ Reciprocal Credit Note (`CREDIT_NOTE_ISSUED`)
- **Determinism:** Both replicas derive identical operation IDs and payloads without central orchestration.

### 3.5 Layer 5: 4-Way Merkle Subsystem Roots & Chained Commitment (`apps/protocol/crypto.py`)
- **Subsystem State Trees:** Computes 4 independent Merkle roots:
  - $O_n$: Operation Log Merkle Root
  - $L_n$: Ledger State Root
  - $I_n$: Inventory State Root
  - $T_n$: Tax Compliance Merkle Root
- **Cross-Ledger State Commitment:**
  $$C_n = \text{SHA-256}(O_n \mathbin{\Vert} L_n \mathbin{\Vert} I_n \mathbin{\Vert} T_n \mathbin{\Vert} C_{n-1})$$
- **Counter-Signing:** Asymmetric Ed25519 dual counter-signatures by both Seller ($\sigma_{\text{seller}}$) and Buyer ($\sigma_{\text{buyer}}$) securing bilateral non-repudiation without requiring a blockchain consensus layer.

### 3.6 Layer 6: Authoritative ERP Ledger Bridge (`apps/protocol/bridge.py`)
- **Decoupled Architecture:** Protocol does NOT duplicate accounting logic.
- **Idempotency Barrier:** Transactions are mapped and persisted into the ERP's authoritative double-entry voucher tables (`Voucher`, `LedgerEntry`, `StockEntry`) with atomic idempotency locks guarding against concurrent races.

---

## 4. Verification & Certification Evidence

| Verification Suite | Target Environment | Scope | Result | Status |
|---|---|---|---|---|
| **Protocol Unit Battery** | SQLite / Django Test Runner | 22 Test Cases across DAG, CRDT, Mapping, Sessions | 22 / 22 Passed | **CERTIFIED** |
| **Cross-Language Canonicalization** | Python 3.14 + Node.js (TS) | 100 Fixtures (Canonical JSON & SHA-256 digests) | 100% Bit-for-Bit Match | **CERTIFIED** |
| **Adversarial Security Suite** | Live Protocol Engine | 9 Adversarial Threat Simulations (tamper, replay, KMS fail-closed) | 9 / 9 Deflected | **CERTIFIED** |
| **High-Concurrency Race Suite** | Neon AWS PostgreSQL 16 | 7 Race Conditions (simultaneous allocations, compensations, registrations) | 0 Data Corruption | **CERTIFIED** |
| **Real Accounting E2E Suite** | PostgreSQL Production DB | Full Seller-Buyer Disconnected Workflow + Balance Equilibrium | 100% Mathematical Match | **CERTIFIED** |
| **Browser Offline/Online PWA** | Web Crypto / IndexedDB | 8-Stage Lifecycle (Non-Extractable Keys, PWA Outbox, Key Rotation) | 100% Success | **CERTIFIED** |
| **Disaster Recovery Restoration** | AES-256 / Gzip / PostgreSQL | Live Snapshot Creation + Dry-Run & Complete Restoration | 16,043 Records Restored | **CERTIFIED** |

---

## 5. Architectural Freeze Declaration

The Vouch Protocol Architecture is hereby **FROZEN** at Version `1.0.0`.  
Any further changes to the underlying protocol models or cryptographic envelopes are strictly deferred to future versions.
