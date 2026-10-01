# Protocol Implementation Map & Verification Evidence

This document provides direct mapping from theoretical mechanisms to concrete source code files, classes, methods, database models, and test suites within the repository.

---

## 1. Concrete Implementation Map

| Technical Mechanism | Implementation File | Primary Classes & Types | Key Functions & Methods | Database Models | Test Suites & Verification |
|---------------------|---------------------|-------------------------|--------------------------|-----------------|-----------------------------|
| **1. Canonical Transaction Model** | `apps/protocol/schema.py` | `CanonicalTransaction`, `TransactionLine`, `TaxSummary`, `TransactionTotals` | `validate_invariants()`, `validate()` | `ProtocolTransaction` (`apps/protocol/models.py`) | `apps/protocol/test_e2e.py` |
| **2. Immutable Operation Model & Taxonomy** | `apps/protocol/operation.py` | `AccountingOperation`, `OperationType`, `OperationClass`, `ReadOnlyDict` | `payload_hash`, `to_dict()`, `_freeze()` | `ProtocolOperation` (`apps/protocol/models.py`) | `apps/protocol/security_tests.py` (Threat 1) |
| **3. Causal Operation DAG** | `apps/protocol/causal_dag.py` | `CausalDAG`, `CausalViolationError` | `add_operation()`, `topological_sort()`, `_resolve_orphans()` | `ProtocolOperation.parents` | `apps/protocol/simulator.py` (Kahn's Sort) |
| **4. Accounting CRDT (DE-CRDT)** | `apps/protocol/crdt.py` | `DE_CRDT` | `merge()`, `evaluate_state()`, `validate_convergence()`, `compute_merkle_state_roots()` | `ProtocolTransaction`, `ProtocolOperation` | `apps/protocol/fuzzer.py` (2,500+ permutations) |
| **5. Semantic Delta Engine** | `apps/protocol/semantic_delta.py` | `SemanticDelta`, `SemanticDeltaEngine` | `compute_state_delta()`, `has_divergence`, `summary()` | N/A (In-memory evaluation) | `apps/protocol/simulator.py` (Step 6) |
| **6. Deterministic & Reciprocal Compensation** | `apps/protocol/compensation.py` | `CompensationEngine` | `generate_item_rejection()`, `generate_price_adjustment()`, `generate_reciprocal_seller_credit_note()` | `ProtocolOperation` | `apps/protocol/test_e2e.py` (Phase 2 & 5) |
| **7. Multi-Variable Invariant Engine** | `apps/protocol/invariants.py` | `InvariantEngine`, `AccountingInvariantViolation` | `validate_double_entry()`, `validate_invoice_totals()`, `validate_tax_components()`, `validate_inventory_conservation()` | N/A (Enforced prior to SQL commit) | `apps/protocol/security_tests.py` (Threat 4) |
| **8. Real Asymmetric Crypto & Merkle Trees** | `apps/protocol/crypto.py` | `ProtocolCrypto`, `MerkleTree`, `CrossLedgerCommitment` | `generate_keypair()`, `sign()`, `verify()`, `get_proof()`, `verify_proof()`, `calculate_hash()` | `CryptographicCommitment` (`apps/protocol/models.py`) | `apps/protocol/security_tests.py` (Threat 5 & 6) |
| **9. Ephemeral Dynamic QR Bootstrap** | `apps/protocol/qr_bootstrap.py` | `QRBootstrapPayload`, `QRSessionManager` | `encode_to_qr_string()`, `decode_from_qr_string()`, `initiate_session_from_scan()` | Django Cache (Redis atomic test-and-set) | `apps/protocol/security_tests.py` (Threat 8) |
| **10. 11-State Handshake State Machine** | `apps/protocol/handshake.py` | `EdiStateMachine`, `EdiState` | `advance()`, `is_expired`, `is_terminal` | `ProtocolTransaction.state_version` | `apps/protocol/security_tests.py` (Threat 3) |
| **11. Multi-Tenant 2-Way Sync Engine** | `apps/protocol/sync_service.py` | `SyncService`, `MultiTenantSecurityError` | `process_sync_payload()` | `ProtocolTransaction`, `ProtocolOperation`, `CryptographicCommitment` | `apps/protocol/security_tests.py` (Threat 7) |
| **12. Versioned Semantic Entity Mapping** | `apps/protocol/mapping.py` | `MappingResolutionEngine`, `ProductMapping` | `resolve_product()`, `register_mapping()` | `EntityMapping` (`apps/protocol/models.py`) | `apps/protocol/test_e2e.py` (Phase 8 & 10) |

---

## 2. Experimental Verification Summary

1. **Property-Based Fuzzing (`apps/protocol/fuzzer.py`):**
   * 500 transaction cycles, >2,500 random merge permutations across 3 replicas.
   * **Result:** 0% divergence. Commutativity confirmed: $\text{Merge}(A, B) == \text{Merge}(B, A)$.

2. **Master Scenario Simulation (`apps/protocol/simulator.py`):**
   * Section 45 scenario executed end-to-end through network partition, out-of-order packet delivery, and duplicate injection.
   * **Result:** Replicas converged to exact net receivables and dual Ed25519 signatures verified.

3. **Empirical Benchmarks (`docs/benchmarks/sync_benchmark_report.md`):**
   * Measured 89.6% network bandwidth savings over conventional full-state sync.
   * Measured 30.80 microseconds per CRDT merge.

4. **Adversarial Threat Testing (`apps/protocol/security_tests.py`):**
   * 8 distinct attack vectors (tampering, replay, state-skip, unbalanced math, signature forgery, Merkle forgery, cross-tenant IDOR, QR replay) tested and 100% deflected.

5. **Legacy Vouch Regression Suite (`python manage.py test apps/`):**
   * 240 existing Django tests passed with zero regressions.
