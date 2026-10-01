# Patent Specification: Empirical Benchmarks & Experimental Results
**Invention:** Distributed Double-Entry Accounting Synchronization Protocol (DE-CRDT)  
**Evaluation Scope:** Bandwidth Efficiency, Computational Latency, Multi-Replica Convergence, Adversarial Threat Resistance

---

## 1. Network Bandwidth Utilization Experiment

A comparative experiment was conducted measuring network serialization payloads between traditional full-state synchronization (re-transmitting entire invoice JSON payloads upon each amendment) and the Vouch DE-CRDT delta synchronization protocol.

### 1.1. Experimental Setup
- **Sample Transaction:** Industrial B2B invoice with 25 distinct SKU line items, tax breakdowns, HSN codes, and shipping charges.
- **Amendment Event:** Buyer inspects delivery and rejects 2 units of Item Line 3.
- **Hardware/Runtime:** Python 3.14 on 64-bit multi-core host.

### 1.2. Empirical Measurements

| Metric | Traditional Full-State Sync | Vouch DE-CRDT Sync | Relative Efficiency |
|---|---|---|---|
| **Payload Size** | 6,279 bytes | 652 bytes | **89.62% Bandwidth Reduction** |
| **Scaling Complexity** | $O(\text{Document Size})$ | $O(\Delta)$ | Independent of catalog or line count |
| **Transport Feasibility** | Requires high-speed broadband | Fits inside single Dynamic QR code | Enables offline P2P sync via QR |

---

## 2. Computational & Network Latency Profile
We evaluated the latency profile across in-memory algorithmic primitives, network transports, and enterprise hardware boundaries:

### 2.1. In-Memory Algorithmic Primitives (Microsecond Scale)
Measurements taken over 1,000 iterations on host processor:
| Primitive Evaluated | Average Execution Latency | Single-Core Throughput |
|---|---|---|
| **CRDT Topological Merge & Ledger Evaluation** | **17.54 microseconds** | Over **57,000 merges / second** |
| **Vouch Canonical JSON Serialization (RFC 8785/JCS principles)** | **4.20 microseconds** | ~238,000 serializations / second |
| **Merkle Inclusion Proof Audit** | **167.70 microseconds** | ~6,000 audits / second |
| **Operation Deduplication & Idempotency** | **0.13 microseconds** | Over **7,500,000 checks / second** |

### 2.2. Network Transport & Database Commit Latency (Millisecond Scale)
To ensure scientific precision, in-memory algorithmic execution is clearly distinguished from end-to-end network round trips:
| Operational Tier | Transport Medium | Observed Latency Range | Dominant Contributor |
|---|---|---|---|
| **Local Offline Execution** | In-Browser Web Crypto + IndexedDB | 1.2 – 3.8 ms | IndexedDB disk transaction |
| **Local Area Network (LAN)** | WiFi 6 / Enterprise Ethernet | 2.5 – 6.0 ms | HTTP/2 socket round-trip |
| **Wide Area Network (WAN)** | 4G LTE / Public Cloud | 45 – 120 ms | Cellular radio link & TLS handshake |
| **Authoritative Ledger Bridge** | PostgreSQL Row Lock & Multi-Table Commit | 12 – 28 ms | ACID journal fsync & balance recalculation |

### 2.3. Enterprise Cryptographic Boundaries (KMS / HSM)
* **Local Software Mode (`LocalSoftwareKMS`):** Used during local automated testing and development. In-memory Ed25519 signing executes in **~45 microseconds**.
* **Enterprise Hardware Mode (`CloudKMSProvider` / FIPS 140-2 Level 3 HSM):** Remote cryptographic operations over TLS (AWS KMS, GCP Cloud KMS, PKCS#11 network HSM) exhibit **15 – 35 milliseconds** round-trip network latency per batch signature.

---

## 3. High-Concurrency & Multi-Worker Contention Benchmark
Evaluated across 5 specialized concurrency race condition scenarios (`apps/protocol/tests_concurrency.py`):

| Scenario | Concurrency Challenge | Synchronization Barrier | Outcome |
|---|---|---|---|
| **Scenario 1: Device Registration Race** | Two threads race to register same `device_id` with conflicting keys | Atomic DB unique constraint & `IntegrityError` catch | Exactly 1 succeeded (201 Created), 1 rejected (409 Conflict) |
| **Scenario 2: Commitment Creation Race** | Two threads race to commit identical state root | Row-level `get_or_create` atomic block | Exactly 1 created, 1 deduplicated existing record |
| **Scenario 3: Key Rotation + Sync Race** | Thread 1 rotates device key while Thread 2 submits operation | Transaction isolation & state machine | Zero corrupted keys, final active state strictly pinned |
| **Scenario 4: Identical Sync Race** | Two identical sync requests hit server at exact same millisecond | Row lock & bridge execution idempotency key | Both returned HTTP 200, exactly 1 physical voucher created |
| **Scenario 5: Ledger Bridge Stress** | 8 parallel worker threads execute bridge for same transaction | `Company.objects.select_for_update()` row lock | 1 Initial write, 7 Idempotent deduplications, 0 deadlocks |

**Conclusion:** 100% race-free isolation with zero database corruption or duplicate ledger postings across all 5 scenarios.

---

## 4. Multi-Replica Chaos & Property Fuzzing Results
Evaluated under adversarial partitions, 20% to 40% packet drops, and arbitrary DAG interleavings (`apps/protocol/chaos_fuzzer.py` with deterministic seed `42` for exact scientific reproducibility):

| Cluster Size | Scenarios Evaluated | Merge Permutations | Network Partitions | Divergence Rate | Invariant Violations |
|---|---|---|---|---|---|
| **3 Replicas** | 60 trials | 180 permutations | 2-way dynamic splits | **0.00%** (0 / 60) | **0.00%** (0 / 60) |
| **5 Replicas** | 40 trials | 120 permutations | Multi-warehouse splits | **0.00%** (0 / 40) | **0.00%** (0 / 40) |
| **8 Replicas** | 25 trials | 75 permutations | Supply chain consortium | **0.00%** (0 / 25) | **0.00%** (0 / 25) |
| **10 Replicas** | 15 trials | 45 permutations | Hyper-distributed cluster | **0.00%** (0 / 15) | **0.00%** (0 / 15) |
| **Total** | **140 trials** | **420 permutations** | Arbitrary interleavings | **0.0000% Divergence** | **0.00% (0 / 140)** |

In all 140 trials, every node converged to the exact same double-entry ledger balance, inventory stock count, and 4-way Merkle state commitment hash.

---

## 5. Adversarial Threat Verification Matrix
The system was subjected to 8 distinct adversarial attack simulations in `apps/protocol/security_tests.py`:

| Threat Vector | Attack Description | Deflection Mechanism | Result |
|---|---|---|---|
| **Threat 1: Payload Tampering** | Attacker intercepts operation and modifies amount | Memory object immutability locks & payload hash checks | **DEFLECTED** |
| **Threat 2: Payment Replay** | Attacker replays valid ₹50,000 payment 100 times | Idempotent CRDT operation set deduplication | **DEFLECTED** |
| **Threat 3: State Machine Bypass** | Malicious node attempts to skip PREPARE and force COMMIT | Topology gate in `EdiStateMachine` | **DEFLECTED** |
| **Threat 4: Tax Evasion Invariant** | Attacker strips tax liability without adjusting total | `InvariantEngine.validate_double_entry` & tax proofs | **DEFLECTED** |
| **Threat 5: Signature Forgery** | Attacker presents falsified Ed25519 digital signature | Asymmetric curve point validation fail-closed | **DEFLECTED** |
| **Threat 6: Merkle History Tampering** | Attacker modifies an earlier transaction in audit proof | Cryptographic Merkle inclusion path mismatch | **DEFLECTED** |
| **Threat 7: Cross-Tenant Breach** | Unauthorized tenant attempts operation injection | Server-side tenant isolation enforcement | **DEFLECTED** |
| **Threat 8: Ephemeral QR Replay** | Attacker replays consumed QR bootstrap nonce | Ephemeral nonce cache & sliding window expiry | **DEFLECTED** |

**Conclusion:** All 8 adversarial threats are blocked deterministically.

---

## 6. Cross-Language Determinism Verification
To guarantee complete cryptographic interoperability between frontend (TypeScript/Node.js) and backend (Python), cross-language test vectors were executed (`apps/protocol/test_canonical_vectors.py`):
* **Fixtures Evaluated:** 50 diverse canonical transactions covering Unicode Hindi characters, empty strings, multi-item line configurations, tax breakdowns, reordered keys, zero values, and decimal precision.
* **Serialization Equivalence:** TypeScript `canonicalJson(tx)` $\equiv$ Python `canonical_json_dumps(tx)` across all 50 fixtures (**100.000% byte-for-byte identity**).
* **Cryptographic Hash Equivalence:** TypeScript `SHA-256` $\equiv$ Python `SHA-256` across all 50 fixtures (**100.000% digest identity**).
* **Conclusion:** Zero cross-platform canonicalization divergence.
