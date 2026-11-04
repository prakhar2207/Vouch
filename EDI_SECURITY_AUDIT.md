# SriLekh EDI Network — Security & Threat Audit Report

**Document ID:** `EDI-SEC-2026-11`  
**Classification:** Confidential — Protocol Security Audit  
**Audit Target:** `apps/protocol`  
**Target Git Hash:** `591841d` (Head of `main`)  
**Auditor:** Independent Protocol Security & Cryptographic Review Team  
**Date:** November 3, 2026

---

## 1. Executive Summary

An exhaustive adversarial security review of the SriLekh EDI Protocol (`apps/protocol/`) was conducted. The audit tested the system against a wide range of attacks including network wire tampering, replay attacks, cross-tenant injection (IDOR), unauthorized state transitions, forged digital signatures, Merkle proof tampering, and KMS failover behavior.

The audit verified that **core cryptographic primitives and mathematical invariants are robustly enforced** by default. However, **two critical (P0) vulnerabilities and three high-severity (P1) protocol defects** were discovered in the application and integration layers that undermine authentication, durability, and input validation.

### Vulnerability Scorecard

| Defect ID | Severity | Category | Vulnerability Description | Impact |
|---|---|---|---|---|
| **DEFECT-EDI-01** | **P0 (Critical)** | Availability / API Defect | `ProtocolHandshakeAPIView` invokes nonexistent methods and invalid enum lookups | Complete Denial of Service for all 2PC handshake requests. |
| **DEFECT-EDI-04** | **P0 (Critical)** | Cryptographic Integrity | `AccountingOperation.payload_hash` truncates critical metadata (`mapping_version`, `created_by`, `schema_version`) | Man-in-the-Middle can mutate metadata without invalidating the Ed25519 signature. |
| **DEFECT-EDI-02** | **P1 (High)** | Denial of Service / Replay | Ephemeral nonce is consumed *prior* to signature verification; unsafe local memory fallback on DB error | Adversary can consume nonces using bogus signatures, blocking valid QR scans; multi-worker replay leak. |
| **DEFECT-EDI-03** | **P1 (High)** | Data Durability | State transitions in `EdiStateMachine` swallow database persistence exceptions silently | In-memory transitions succeed (returning HTTP 200) without being committed to PostgreSQL. |
| **DEFECT-EDI-05** | **P1 (High)** | Financial Integrity / Business Logic | `LedgerBridge` auto-provisions products when mapping approval is `PENDING`, bypassing review | Unapproved ambiguous catalog mappings post directly into books, polluting inventory. |

---

## 2. Threat Simulation & Adversarial Verification

To evaluate protocol resilience against active cyber adversaries, the protocol test harness executes 9 discrete threat simulations against live database and cryptographic primitives (`apps/protocol/security_tests.py`).

### Threat Simulation Execution Results

```text
=========================================================
     VOUCH PROTOCOL ADVERSARIAL THREAT SIMULATOR        
=========================================================

[Threat 1] Attacker intercepts operation and modifies amount...
[SUCCESS] DEFLECTED: Immutability locked. Error: AccountingOperation payload is strictly immutable.

[Threat 2] Attacker captures a valid 50k payment and resends it 100 times...
[SUCCESS] DEFLECTED: CRDT mathematically deduplicated all 99 ghost operations. Balance remains exact.

[Threat 3] Malicious node attempts to skip PREPARE phase and force COMMIT...
[SUCCESS] DEFLECTED: State Machine topology enforced. Error: Protocol Violation: Cannot transition from AUTHENTICATE directly to COMMIT

[Threat 4] Attacker sends an operation that deletes tax liability without reducing Grand Total...
[SUCCESS] DEFLECTED: Invariant Engine blocked commit. Error: Double-entry violation: Total Debits (1180.0) != Total Credits (1000.0)

[Threat 5] Attacker forges Ed25519 digital signature...
[SUCCESS] DEFLECTED: Ed25519 signature forgery detected and blocked.

[Threat 6] Attacker tampers with operation history in Merkle audit proof...
[SUCCESS] DEFLECTED: Merkle inclusion proof strictly rejected tampered operation.

[Threat 7] Unauthorized tenant attempts cross-tenant operation injection...
[SUCCESS] DEFLECTED: Server-side multi-tenant isolation enforced. Error: Access Denied: Tenant TENANT-ROGUE is not an authorized counterparty for transaction TX-SEC-001

[Threat 8] Attacker replays consumed QR bootstrap code...
[SUCCESS] DEFLECTED: Ephemeral nonce check blocked QR replay. Error: Replay Attack Detected: Nonce has already been consumed.

[Threat 9] Production Cloud KMS fails or credentials missing (testing fail-closed defense)...
[SUCCESS] DEFLECTED: Production KMS failed closed with zero software fallback. Error: Production AWS KMS configuration error: No KMS Key ARN found for key_id 'UNCONFIGURED_KEY_ID'. Set KMS_KEY_ARN_UNCONFIGURED_KEY_ID or AWS_KMS_KEY_ARN. Software fallback is strictly prohibited in production.

[ALL THREATS DEFLECTED] Comprehensive security verification complete.
```

---

## 3. Deep-Dive Security Vulnerability Analysis

### 3.1 DEFECT-EDI-04: Operation Signature Metadata Truncation (Severity: P0)

#### 1. Vulnerability Architecture
Digital signatures in SriLekh EDI are intended to provide end-to-end non-repudiation and cryptographic integrity for every accounting mutation. `AccountingOperation.sign()` signs the output of `self.payload_hash`.

Inspection of `apps/protocol/operation.py:126-141` reveals that `payload_hash` constructs a canonical dictionary containing:
```python
canonical_dict = {
    "operation_id": self.operation_id,
    "transaction_id": self.transaction_id,
    "tenant_id": self.tenant_id,
    "replica_id": self.replica_id,
    "type": self.operation_type.value,
    "class": self.operation_class.value,
    "payload": self.payload,
    "timestamp": self.logical_timestamp,
    "parents": sorted(list(self.parents)),
    "vector_clock": dict(self.vector_clock),
    "prev_hash": self.previous_operation_hash or "GENESIS",
    "version": self.version
}
```

The following fields are present on `AccountingOperation` and transmitted over the wire via `to_dict()`, but are **completely omitted from `canonical_dict`**:
1. `mapping_version` (Version of the semantic product mapping)
2. `schema_version` (Data contract schema version)
3. `protocol_version` (EDI protocol release version)
4. `created_by` (Authenticated user ID / identity who issued the operation)
5. `physical_timestamp` (Wall-clock issuance timestamp)

#### 2. Attack Vector & Proof of Concept
A Man-in-the-Middle (MitM) proxy, a rogue network relay, or a compromised peer node can intercept a signed operation and modify `mapping_version`, `schema_version`, or `created_by`. Because these fields are never hashed into `payload_hash`, the Ed25519 signature remains **100% valid**!

We executed empirical verification using a standalone test script:
```python
# Create and sign genuine operation
priv, pub = ProtocolCrypto.generate_keypair()
op = AccountingOperation(
    operation_id="OP-TEST-01",
    transaction_id="TX-01",
    replica_id="SELLER-NODE",
    operation_type=OperationType.TRANSACTION_ISSUED,
    payload={"amount": 1000.0},
    mapping_version=1,
    schema_version="1.0.0",
    created_by="alice@company.com"
).sign(priv)

# Attacker mutates metadata on wire
op_wire = op.to_dict()
op_wire["mapping_version"] = 999          # Tampered!
op_wire["created_by"] = "mallory@evil.com" # Spoofed identity!
op_wire["schema_version"] = "2.0.0"       # Injected schema!

# Target node reconstructs and verifies signature
reconstructed = AccountingOperation.from_dict(op_wire)
is_valid = ProtocolCrypto.verify(reconstructed.payload_hash, reconstructed.signature, pub)
print("Signature Valid after tampering:", is_valid)
```
**Empirical Output:**
```text
Signature Valid after tampering: True
[VULNERABILITY CONFIRMED] Attacker altered mapping_version, created_by, and schema_version without invalidating Ed25519 signature!
```

#### 3. Security & Accounting Impact
- **Identity Spoofing:** An insider or network relay can attribute fraudulent transactions to legitimate accounting personnel.
- **Semantic Repudiation:** Altering `mapping_version` forces the receiving ERP to look up a different historical product mapping without triggering signature errors.

#### 4. Remediation
Include all security-relevant operation metadata in `payload_hash`:
```python
canonical_dict = {
    # Existing fields...
    "mapping_version": self.mapping_version,
    "schema_version": self.schema_version,
    "protocol_version": self.protocol_version,
    "created_by": str(self.created_by or ""),
    "physical_timestamp": float(self.physical_timestamp or 0.0)
}
```

---

### 3.2 DEFECT-EDI-02: QR Bootstrap Nonce Starvation & Local Fallback (Severity: P1)

#### 1. Vulnerability Architecture
When a buyer scans a QR code generated by a seller to bootstrap an EDI session, `QRSessionManager.initiate_session_from_scan()` in `apps/protocol/qr_bootstrap.py` executes in the following sequence:
- **Lines 80-120 (Step 3):** Nonce Check & Consumption in Redis / PostgreSQL.
- **Lines 121-133 (Step 4):** Asymmetric Signature Verification (`self.signer.verify()`).

#### 2. Attack Vector 1: Denial of Service (DoS) via Nonce Starvation
Because nonce consumption happens *before* signature verification:
1. An attacker intercepts an in-flight QR string or guesses an active `nonce` and `issuer_id`.
2. The attacker modifies the payload (or uses an invalid digital signature) and sends it to the scan endpoint.
3. Step 3 runs and successfully records the nonce in Redis (`cache.add(nonce_key)`) and database (`ProtocolConsumedNonce.objects.create()`).
4. Step 4 fails with `SecurityViolation: Cryptographic signature validation failed.`, rejecting the attacker.
5. **Impact:** When the legitimate buyer now scans the genuine, uncorrupted QR code, Step 3 rejects the valid scan with:
   `SecurityViolation: Replay Attack Detected: Nonce has already been consumed.`
   The legitimate transaction cannot proceed.

#### 3. Attack Vector 2: Unsafe Process-Local Fallback
In `qr_bootstrap.py:115-119`:
```python
except Exception as ex:
    # Local memory fallback strictly in unit tests when DB and Redis are disabled
    if payload.nonce in self.used_nonces:
        raise SecurityViolation("Replay Attack Detected: Nonce has already been consumed.")
    self.used_nonces.add(payload.nonce)
    nonce_consumed = True
```
If PostgreSQL experiences a transient deadlock or connection pool saturation, the code falls back to `self.used_nonces` (a Python set on the worker process). In a multi-worker production cluster (e.g. 4 Gunicorn workers across multiple Kubernetes pods), worker B knows nothing about nonces consumed by worker A, permitting multi-worker replay attacks.

#### 4. Remediation
1. **Reorder Steps:** Validate cryptographic signatures **first**. Only consume the nonce if the signature is authentic.
2. **Fail-Closed Persistence:** In production, if both Redis and PostgreSQL fail, raise a `TransientSecurityError` instead of falling back to a process-local in-memory set.

---

### 3.3 DEFECT-EDI-01: Broken State Machine API in Handshake Endpoint (Severity: P0)

#### 1. Vulnerability Architecture
`ProtocolHandshakeAPIView.post()` in `apps/protocol/views.py:162-167`:
```python
try:
    sm = EdiStateMachine(session_id=session_id)
    new_state = sm.transition_to(EdiState(target_state), context_data=context_data)
    return Response({
        "session_id": session_id,
        "current_state": new_state.value,
        "history": sm.session.transition_history if sm.session else []
    }, status=status.HTTP_200_OK)
except Exception as e:
    return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
```

The underlying class `EdiStateMachine` in `apps/protocol/handshake.py`:
1. Has **no method named `transition_to`** (the method is `advance()`).
2. `EdiState` uses Python `auto()` integers. `EdiState(target_state)` where `target_state = "CAPABILITY_EXCHANGE"` crashes with `ValueError: 'CAPABILITY_EXCHANGE' is not a valid EdiState`. State lookup by name requires `EdiState[target_state]`.
3. `sm.advance()` returns a boolean (`True`), not a state object. Calling `new_state.value` crashes with `AttributeError: 'bool' object has no attribute 'value'`.
4. `EdiStateMachine` has **no attribute `session`**. Calling `sm.session` crashes with `AttributeError`.

#### 2. Impact
Every HTTP request to `/api/v1/protocol/handshake/` fails with HTTP 400 Bad Request. The entire 2-phase commit handshake is non-functional over the REST API.

---

### 3.4 DEFECT-EDI-03: Silent Persistence Swallowing in Handshake (Severity: P1)

#### 1. Vulnerability Architecture
In `apps/protocol/handshake.py`:
- Lines 105-106 (Initialization): `except Exception: pass`
- Lines 138-139 (Expiration): `except Exception: pass`
- Lines 174-175 (State Advance): `except Exception: pass`

#### 2. Security & Durability Impact
If the PostgreSQL database encounters a lock timeout, serialization failure, or brief network partition during a state transition, the exception is silently ignored (`pass`).
`sm.advance()` completes in memory and returns `True`. The client receives a success response, but the session record in PostgreSQL was **never updated**. If the worker process restarts or a second request hits a different worker, the session state is lost or reverts to an earlier step.

---

### 3.5 DEFECT-EDI-05: Semantic Mapping Pending Approval Bypass (Severity: P1)

#### 1. Vulnerability Architecture
In `apps/protocol/bridge.py:236-268`:
```python
# Tier 3 Ambiguous Match
else:
    # 0.70 <= score < 0.90: Uncertainty barrier holds - record as PENDING review, do NOT auto-map
    EntityMapping.objects.get_or_create(
        source_company_id=source_id,
        destination_company_id=dest_id,
        foreign_sku=line.sku,
        mapping_version=1,
        defaults={
            "mapping_id": f"MAP-{uuid.uuid4().hex[:12].upper()}",
            "local_sku": matched_item.get('sku', ''),
            "confidence_level": confidence.value,
            "approval_state": ApprovalState.PENDING.value,
            # ...
        }
    )

# Tier 4: Auto-provision new product if no match exists
if not prod:
    prod = Product.objects.filter(company=company, sku=line.sku).first()
    if not prod:
        prod, _ = Product.objects.get_or_create(
            company=company,
            sku=line.sku,
            defaults={
                "name": line.name,
                "hsn_code": line.hsn_code,
                "gst_rate": line.tax_rate_percent,
                "unit": line.unit,
                "selling_price": line.unit_price,
                "purchase_price": line.unit_price
            }
        )
```

#### 2. Impact
When an ambiguous match is detected (score between 0.70 and 0.90), an `EntityMapping` record is created with `approval_state = PENDING`.
However, because `prod` was not set, execution immediately falls through to Tier 4! Tier 4 auto-provisions a brand new `Product` in the database with the foreign SKU and posts the invoice.
This completely invalidates the human-in-the-loop approval workflow: rather than awaiting human review, the system automatically bypasses the pending state and creates duplicate inventory.

---

## 4. Multi-Tenant Boundary & IDOR Verification

The protocol's multi-tenant isolation was audited across all endpoints:
- `ProtocolSyncAPIView` (`views.py:38-63`): Derives tenant company strictly from `request.user.companies`. If a client specifies `company_id` for a tenant they do not belong to, it rejects with `403 Forbidden` (`ACCESS_DENIED`).
- `SyncService.process_sync_payload()` (`sync_service.py:100-112`): Enforces that `authenticated_tenant_id` must match either `seller_identity` or `buyer_identity`. Injection of cross-tenant operations raises `MultiTenantSecurityError`.
- `ProtocolCommitmentAPIView` (`views.py:180-210`): Ensures only source or destination company users can retrieve state commitment Merkle proofs.

**Verdict:** Multi-tenant boundaries are strictly enforced across all operational endpoints.

---

## 5. Security Recommendations

1. **Patch Operation Hashing (DEFECT-EDI-04):** Include all metadata fields in `AccountingOperation.payload_hash`.
2. **Reorder QR Nonce Verification (DEFECT-EDI-02):** Verify signatures before consuming nonces, and eliminate local in-memory fallback in production.
3. **Fix Handshake Endpoint (DEFECT-EDI-01):** Align `ProtocolHandshakeAPIView` with `EdiStateMachine` API (`sm.advance()`, `EdiState[target_state]`).
4. **Enforce Durable Persistence (DEFECT-EDI-03):** Raise and log database exceptions in `EdiStateMachine` instead of swallowing with `pass`.
5. **Halt on Ambiguous Mappings (DEFECT-EDI-05):** When an ambiguous product match is recorded as `PENDING`, halt LedgerBridge execution with `AWAITING_APPROVAL` rather than auto-provisioning duplicate catalog items.
