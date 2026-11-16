# SriLekh EDI Network — Architecture Verification Report

**Document ID:** `EDI-ARCH-2026-11`  
**Protocol Version:** `Vouch EDI 1.0`  
**Audit Scope:** `apps/protocol` (Commits `606d942`, `902ab7a`, and working tree)  
**Verification Date:** November 3, 2026  
**Auditor:** Independent Protocol & Cryptographic Security Audit Team  
**Audit Classification:** Evidence-Only Inspection & Empirical Verification

---

## 1. Executive Summary

The **SriLekh EDI Network** (implemented under `apps/protocol/`) is an advanced distributed B2B accounting protocol designed to facilitate peer-to-peer, mathematically verified inter-enterprise accounting between Indian MSMEs. Unlike conventional EDI systems (such as EDIFACT or ANSI X12) which rely on asynchronous, batch-mode, unverified document transport, SriLekh EDI merges principles from **Conflict-Free Replicated Data Types (CRDTs)**, **Causal Directed Acyclic Graphs (DAGs)**, **Asymmetric Ed25519 Cryptography**, and **Double-Entry Bookkeeping Invariants** into an authoritative protocol layer.

This architectural audit evaluated the design, layer separation, dataflow, and concrete implementation of the complete protocol stack against industrial accounting requirements and distributed systems reliability standards.

### Summary of Architectural Health

| Layer / Subsystem | Implementation File(s) | Architectural Grade | Status | Key Observation |
|---|---|---|---|---|
| **Layer 1: Serialization** | `canonical_json.py`, `schema.py` | **A+ (100%)** | Pass | Strict RFC-8785 canonical JSON sorting; 50/50 cross-language test vectors match TypeScript bit-for-bit. |
| **Layer 2: Cryptography & KMS** | `crypto.py`, `kms.py`, `key_manager.py` | **B+** | Vulnerability Identified | Ed25519 signing and Merkle tree proofs pass; AWS/GCP KMS fail-closed; **DEFECT-EDI-04** identified in operation signature hashing. |
| **Layer 3: Causal DAG & CRDT** | `causal_dag.py`, `crdt.py`, `operation.py` | **A** | Pass | Topological sorting, vector clocks, and mathematical deduplication verified across 140 chaos scenarios. |
| **Layer 4: Handshake & 2PC** | `handshake.py`, `views.py` | **D** | **Critical Defect** | Underlying `EdiStateMachine` is mathematically sound, but HTTP endpoint `ProtocolHandshakeAPIView` is broken (**DEFECT-EDI-01**) and persistence errors are silently swallowed (**DEFECT-EDI-03**). |
| **Layer 5: Ledger Bridge** | `bridge.py`, `sync_service.py` | **A-** | Pass with Defect | Double-entry posting (`Debits == Credits`), idempotency locks, and reciprocal voucher generation verified; **DEFECT-EDI-05** identified in mapping review bypass. |
| **Layer 6: Semantic Mapping** | `mapping.py` | **B** | Mislabeling Identified | Lexical Jaccard token matching mislabeled as `ML_PREDICTED`; approval barrier bypassed during auto-provisioning. |

---

## 2. Protocol Architecture & Layer Decomposition

The SriLekh EDI protocol stack is divided into six distinct, strictly decoupled functional layers:

```mermaid
graph TD
    subgraph Layer 1: Canonical Serialization
        A1[CanonicalTransaction Schema] --> A2[RFC-8785 Canonical JSON Encoder]
        A2 --> A3[Deterministic SHA-256 Envelope Digest]
    end

    subgraph Layer 2: Cryptographic Identity & KMS
        B1[Authorized Devices & Replicas] --> B2[Ed25519 Asymmetric Signatures]
        B2 --> B3[Cloud KMS / Hardware HSM Fail-Closed Driver]
        B3 --> B4[Dynamic QR Ephemeral Nonce Bootstrap]
    end

    subgraph Layer 3: Causal History & Replication
        C1[AccountingOperation Envelope] --> C2[Causal Directed Acyclic Graph DAG]
        C2 --> C3[Vector Clocks & Topological Sort]
        C3 --> C4[Double-Entry CRDT DE-CRDT Merge Engine]
    end

    subgraph Layer 4: Consensus & Handshake
        D1[2-Phase Commit 2PC Coordination] --> D2[13-State EdiStateMachine]
        D2 --> D3[Timeout Enforcement & Terminal Transitions]
    end

    subgraph Layer 5: Authoritative ERP Bridge
        E1[Distributed Idempotency Lock] --> E2[Entity / Company Membership Authorization]
        E2 --> E3[Vouch Double-Entry Voucher Generation]
        E3 --> E4[LedgerBalance & StockMovement Mutation]
    end

    subgraph Layer 6: Semantic Product Resolution
        F1[Foreign Catalog Lines] --> F2[Tiered Matching: SKU > Normalized > HSN > Jaccard]
        F2 --> F3[EntityMapping Approval Barriers]
    end

    Layer 1 --> Layer 2
    Layer 2 --> Layer 3
    Layer 3 --> Layer 4
    Layer 4 --> Layer 5
    Layer 6 --> Layer 5
```

---

## 3. Subsystem Deep-Dive

### 3.1 Layer 1: Canonical Serialization (`schema.py`, `canonical_json.py`)
- **Objective:** Ensure that regardless of programming language (Python, TypeScript, Go), operating system, or JSON key ordering, two independent peers generate the exact same byte-level SHA-256 digest for an invoice or operational envelope.
- **Specification:** Adheres to **RFC-8785 (JSON Canonicalization Scheme - JCS)**.
  - Keys sorted lexicographically by UTF-16 code units.
  - Numbers formatted without unnecessary trailing zeros or exponent notation.
  - Whitespace eliminated (`separators=(',', ':')`).
- **Empirical Evidence:**
  The protocol contains 50 rigorous test fixtures in `apps/protocol/test_canonical_vectors.py`. Execution against the live Django test runner confirms:
  ```text
  --> Running Cross-Language Verification across 50 fixtures...
    [PASSED] 100% Bit-for-Bit Equivalence across all 50 fixtures!
    [PASSED] TypeScript SHA-256 == Python SHA-256 verified without variance.
  ```

### 3.2 Layer 2: Cryptographic Identity & Hardware KMS (`crypto.py`, `kms.py`, `key_manager.py`)
- **Key Algorithms:** Asymmetric **Ed25519** (`nacl.signing.SigningKey` / `VerifyKey`).
- **Key Isolation:**
  - Production deployments require hardware-backed signing via AWS KMS (`ED25519_SHA_512`), Google Cloud KMS, or Azure Key Vault.
  - `CloudKMSProvider` enforces a strict **fail-closed** invariant: if cloud credentials fail or a key ARN is unconfigured, it immediately raises `KMSSigningError` with zero silent software fallback (`apps/protocol/kms.py:113-116`).
- **Binary Merkle Tree:**
  - Constructed via `MerkleTree` class (`crypto.py:100-165`).
  - Implements canonical leaf pairing, interior node hashing (`SHA-256(left + right)`), and logarithmic inclusion proofs (`get_proof()` and `verify_proof()`).

### 3.3 Layer 3: Causal DAG & Double-Entry CRDT (`causal_dag.py`, `crdt.py`, `operation.py`)
- **Causal DAG:**
  - Each `AccountingOperation` references its causal parents via `parents: List[str]`.
  - Operations without parents are roots (Genesis).
  - Out-of-order or network-delayed operations are placed into an in-memory orphan buffer (`orphans: Dict[str, AccountingOperation]`) until all antecedent parents arrive.
  - Causal order is resolved using Kahn's topological sort algorithm, breaking ties deterministically with `(logical_timestamp, operation_id)`.
- **Double-Entry CRDT (`DE_CRDT`):**
  - Projects the sorted DAG operations into four synchronized ledgers:
    1. `AccountsReceivable` (Asset: Dr balance)
    2. `SalesAccount` (Income: Cr balance)
    3. `TaxAccount` (Liability: Cr balance)
    4. `CashAccount` (Asset: Dr balance)
  - Reciprocal buyer ledgers are derived symmetrically (`AccountsPayable`, `PurchaseAccount`, `InputTaxAccount`).
  - Supports non-destructive state merges: `Merge(A, B) == Merge(B, A)` (Commutative, Associative, Idempotent).

### 3.4 Layer 4: 2-Phase Commit (2PC) Handshake (`handshake.py`, `views.py`)
- **State Machine Architecture:**
  - Defines 13 sequential states and 7 terminal states (`TERMINAL_STATES`):
    ```mermaid
    stateDiagram-v2
        [*] --> DISCOVER
        DISCOVER --> CAPABILITY_EXCHANGE
        DISCOVER --> REJECTED
        CAPABILITY_EXCHANGE --> AUTHENTICATE
        CAPABILITY_EXCHANGE --> REJECTED
        AUTHENTICATE --> PROPOSE
        AUTHENTICATE --> INVALID_SIGNATURE
        AUTHENTICATE --> REJECTED
        PROPOSE --> RECEIVE
        PROPOSE --> EXPIRED
        RECEIVE --> VALIDATE
        RECEIVE --> EXPIRED
        VALIDATE --> PREPARE
        VALIDATE --> VALIDATION_FAILED
        PREPARE --> READY
        PREPARE --> CONFLICT
        PREPARE --> EXPIRED
        READY --> ACCEPT
        READY --> REJECTED
        READY --> EXPIRED
        ACCEPT --> COMMIT
        ACCEPT --> ROLLBACK_REQUIRED
        COMMIT --> COMMITTED
        COMMIT --> ROLLBACK_REQUIRED
        COMMITTED --> [*]
        REJECTED --> [*]
        EXPIRED --> [*]
        INVALID_SIGNATURE --> [*]
        CONFLICT --> [*]
        VALIDATION_FAILED --> [*]
        ROLLBACK_REQUIRED --> [*]
    ```
- **Terminal Guarantees:** Once a session enters a terminal state (e.g. `COMMITTED`, `REJECTED`, `EXPIRED`), no further transitions can be triggered.
- **Architectural Flaw Identified:**
  While `EdiStateMachine` in `handshake.py` is implemented correctly, the HTTP controller `ProtocolHandshakeAPIView` in `views.py` calls nonexistent methods and crashes upon invocation (see **DEFECT-EDI-01**).

### 3.5 Layer 5: Authoritative ERP Ledger Bridge (`bridge.py`, `sync_service.py`)
- **Function:** Translates the converged CRDT operational state into real, auditable, persisted Django ORM accounting vouchers in the tenant's database (`Voucher`, `VoucherLineItem`, `LedgerEntry`, `StockMovement`).
- **Supported Operations:**
  - `TRANSACTION_ISSUED` / `INVOICE_ISSUED`: Generates `SALES` voucher on Seller, `PURCHASE` voucher on Buyer.
  - `ITEM_REJECTED` / `CREDIT_NOTE_ISSUED`: Generates `CREDIT_NOTE` on Seller (reversing accounts receivable, sales revenue, and tax liability) and reciprocal `DEBIT_NOTE` on Buyer (reversing purchase expense and input tax credit).
  - `PAYMENT_ALLOCATED`: Generates `RECEIPT` voucher on Seller, `PAYMENT` voucher on Buyer.
- **Idempotency Guarantees:**
  - Employs a two-tier idempotency barrier:
    1. Distributed database lock (`pg_advisory_xact_lock` / table-level lock on `ProtocolTransaction`).
    2. Idempotency cache table (`ProtocolBridgeExecution`) keyed on `SHA256(company_id + tx_id + converged_op_count)`.
  - High-concurrency stress testing with 8 parallel worker threads demonstrated 1 physical execution and 7 cached deduplications with zero duplicate vouchers.

### 3.6 Layer 6: Semantic Product Resolution (`mapping.py`)
- **Matching Pipeline:**
  1. *Tier 1 (Exact SKU):* Case-insensitive match on `sku` -> Score `1.0`, Confidence `HEURISTIC`.
  2. *Tier 2 (Normalized SKU):* Alphanumeric normalized SKU match -> Score `0.95`, Confidence `HEURISTIC`.
  3. *Tier 3 (HSM Match + Lexical Token Overlap):* Identical HSN code combined with Jaccard token overlap of product names -> Score `0.60 + 0.30 * Jaccard`.
  4. *Tier 4 (Token Similarity):* Pure Jaccard name token similarity >= 0.70.
- **Architectural Flaw Identified:**
  Ambiguous matches (0.70 <= score < 0.90) are correctly recorded with `approval_state = PENDING`. However, the downstream code in `bridge.py` does not halt execution; instead, it falls through to Tier 4 auto-provisioning, creating a new product and posting the invoice anyway (see **DEFECT-EDI-05**).

---

## 4. Architectural Sequence Flow

### 4.1 End-to-End Inter-Company Accounting Flow
The diagram below illustrates the exact runtime message exchange between Seller, Buyer, and the SriLekh EDI network:

```mermaid
sequenceDiagram
    autonumber
    actor Seller User
    participant Seller ERP as Seller Node (Replica 1)
    participant SriLekh EDI as Protocol Sync Service
    participant Buyer ERP as Buyer Node (Replica 2)
    actor Buyer User

    Note over Seller User, Buyer ERP: Phase 1: Invoice Issuance & Canonical Commitment
    Seller User->>Seller ERP: Create & Post Sales Invoice (₹11,800)
    Seller ERP->>Seller ERP: Generate CanonicalTransaction (SHA-256 Digest)
    Seller ERP->>Seller ERP: Sign OP-BASE with Seller Ed25519 Private Key
    Seller ERP->>SriLekh EDI: POST /api/v1/protocol/sync/ (Canonical Envelope + OP-BASE)
    SriLekh EDI->>SriLekh EDI: Verify Seller Signature & Invariants
    SriLekh EDI->>SriLekh EDI: Compute Merkle State Roots (L_seller, I_seller)
    SriLekh EDI-->>Seller ERP: HTTP 200 OK (State Commitment Stored)

    Note over Seller User, Buyer ERP: Phase 2: Buyer Sync & Inspection
    Buyer ERP->>SriLekh EDI: POST /api/v1/protocol/sync/ (Polling for New Transactions)
    SriLekh EDI-->>Buyer ERP: Deliver Canonical Transaction & OP-BASE
    Buyer ERP->>Buyer ERP: Verify Seller Identity & Digital Signature
    Buyer ERP->>Buyer ERP: Execute Semantic Product Mapping
    Buyer User->>Buyer ERP: Inspect Goods: Reject 2 Units (Damage)
    Buyer ERP->>Buyer ERP: Generate & Sign Compensation OP-REJECT (₹2,360 Reversal)
    Buyer ERP->>SriLekh EDI: POST /api/v1/protocol/sync/ (OP-REJECT)

    Note over Seller User, Buyer ERP: Phase 3: Reciprocal Compensation & ERP Ledger Posting
    SriLekh EDI->>SriLekh EDI: Ingest OP-REJECT into Causal DAG
    SriLekh EDI->>SriLekh EDI: Auto-generate Reciprocal Credit Note OP-RECIP-CN
    SriLekh EDI->>SriLekh EDI: Merge CRDT State (Net Receivable: ₹9,440)
    
    Buyer ERP->>Buyer ERP: LedgerBridge: Post Purchase Bill (₹11,800) & Debit Note (₹2,360)
    Seller ERP->>SriLekh EDI: POST /api/v1/protocol/sync/ (Fetch Converged Operations)
    SriLekh EDI-->>Seller ERP: Deliver OP-REJECT & OP-RECIP-CN
    Seller ERP->>Seller ERP: LedgerBridge: Post Credit Note (₹2,360)

    Note over Seller User, Buyer ERP: Phase 4: Payment Settlement & Reconciliation
    Seller User->>Seller ERP: Receive Bank Wire (₹5,900)
    Seller ERP->>Seller ERP: Sign OP-PAYMENT (₹5,900)
    Seller ERP->>SriLekh EDI: POST /api/v1/protocol/sync/ (OP-PAYMENT)
    SriLekh EDI->>SriLekh EDI: CRDT Merge & Invariant Validation
    Seller ERP->>Seller ERP: LedgerBridge: Post Receipt Voucher (₹5,900)
    Buyer ERP->>Buyer ERP: LedgerBridge: Post Payment Voucher (₹5,900)

    Note over Seller User, Buyer ERP: Phase 5: Cryptographic State Commitment
    SriLekh EDI->>SriLekh EDI: Generate Final 4-Way Cross-Ledger State Commitment
    SriLekh EDI-->>Seller ERP: Merkle Roots (Seller Net Rec: ₹3,540)
    SriLekh EDI-->>Buyer ERP: Merkle Roots (Buyer Net Pay: ₹3,540)
```

---

## 5. Architectural Findings & Defect Summary

The architectural verification uncovered 5 specific defects across the codebase:

```mermaid
pie title Architectural Defects by Severity
    "P0 - Critical (Blocker)" : 2
    "P1 - High (Protocol Flaw)" : 2
    "P2 - Medium (Architecture Disconnect)" : 1
```

1. **DEFECT-EDI-01 (Severity: P0): Handshake API Runtime Crash**
   - Location: `apps/protocol/views.py:163-167`
   - Description: Endpoint invokes nonexistent method `sm.transition_to()` instead of `sm.advance()`, passes strings to integer `auto()` Enum, treats boolean return value as Enum object (`new_state.value`), and accesses nonexistent property `sm.session`.
2. **DEFECT-EDI-02 (Severity: P1): QR Nonce Consumption Prior to Signature Verification**
   - Location: `apps/protocol/qr_bootstrap.py:80-133`
   - Description: Ephemeral nonces are marked consumed in Redis/DB *before* the Ed25519 signature is verified. A forged payload can consume a nonce, causing denial of service for genuine scans. Unsafe local memory fallback exists on DB error.
3. **DEFECT-EDI-03 (Severity: P1): Silent State Machine Persistence Swallowing**
   - Location: `apps/protocol/handshake.py:105-106, 138-139, 174-175`
   - Description: Database write errors to `EdiSession` are wrapped in bare `try ... except Exception: pass`, resulting in in-memory success return codes without durable database persistence.
4. **DEFECT-EDI-04 (Severity: P0): Operation Signature Metadata Truncation**
   - Location: `apps/protocol/operation.py:126-141`
   - Description: `payload_hash` excludes security-critical metadata: `mapping_version`, `schema_version`, `protocol_version`, `created_by`, and `physical_timestamp`. An attacker can mutate these fields on the wire without invalidating the cryptographic signature.
5. **DEFECT-EDI-05 (Severity: P1): Pending Semantic Mapping Auto-Provisioning Bypass**
   - Location: `apps/protocol/bridge.py:236-268`
   - Description: Products with ambiguous confidence (0.70 - 0.90) are marked `PENDING` review, but execution immediately falls through to Tier 4 auto-provisioning, creating a brand new SKU and posting the voucher without accountant approval.
   - Secondary Flaw: Jaccard token set intersection labeled as `ML_PREDICTED` without ML inference (`mapping.py:105, 111`).

---

## 6. Architectural Conclusion

The architectural foundations of the SriLekh EDI network—namely RFC-8785 canonical serialization, Ed25519 asymmetric identity, CRDT causal DAG convergence, and double-entry mathematical invariants—are **exceptionally solid and theoretically rigorous**.

However, **production deployment must be withheld** until the 5 identified defects are patched. The system cannot reliably service external ERP traffic while the handshake endpoint crashes upon invocation and operation signatures allow unhashed metadata manipulation.
