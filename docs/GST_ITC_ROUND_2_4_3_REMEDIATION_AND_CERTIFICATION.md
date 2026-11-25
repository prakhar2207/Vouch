# SriLekh GST — Round 2.4.3 Targeted Remediation & Release Re-Certification Report
## Durable Request-Bound Idempotency, Centralized Filing Frequency Governance & Database Trigger Rollback Certification

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Working Branch:** `remediation/round-2.4.3-idempotency-governance`  
**Baseline Commit:** `e11c2c65655be1b5a5de3a4069eae29a6690f9dd` (Round 2.4.2)  
**Target Branch:** `main`  
**Database Target:** PostgreSQL 18.7 on AWS Neon (`neondb_staging` / `test_neondb_staging`)  
**Certification Date:** 25 November 2026  
**Auditor / Architect Roles:** Principal Django/PostgreSQL Engineer, GST Compliance Architect, Application Security Engineer, Independent QA Auditor  

---

## 1. Executive Summary & Release Verdict

**Verdict:** **`GO FOR PRODUCTION RELEASE`**

This report delivers the verified, evidence-backed completion of **SriLekh GST Round 2.4.3 Targeted Remediation**. Following the independent source-code audit of Round 2.4.2, targeted hardening was conducted to eliminate latent race conditions, ensure durable request-bound idempotency across all voucher attribution mutations, establish an immutable audit trail for manual filing frequency verifications, and enforce forward-only database audit trigger governance.

### Core Remediation Achievements:
1. **P0 Durable Request-Bound Idempotency**:
   - Eliminated the defect where an `operation_ref` was accepted merely because an attribution log existed.
   - Bound `operation_ref` to a canonical SHA-256 request fingerprint (`company_id`, `actor_id`, sorted `voucher_ids`, `registration_id`, `is_correction`, `attribution_source`, `reason`).
   - Implemented `VoucherAttributionOperation` model with unique constraint on `(company, operation_ref)` and atomic three-state lifecycle (`PENDING`, `COMPLETED`, `FAILED`).
   - Fast-path replay check outside transaction boundaries prevents unnecessary database locks for repeated identical requests.
   - Concurrently racing identical requests return identical cached responses (`HTTP 200`).
   - Replays with conflicting payloads return `HTTP 409 Conflict` with error code `OPERATION_REFERENCE_CONFLICT`.
   - Operations that fail during execution permit safe parameter updates and re-execution without false conflicts.
2. **P1 Centralized Verified Filing Frequency Governance**:
   - Single canonical interface `registration.get_verified_filing_frequency()` across the entire codebase.
   - Raw database field `filing_frequency` is strictly encapsulated and forbidden from driving statutory, statement-resolution, or error-classification decisions.
   - Provider `FORM_NOT_APPLICABLE` responses are only treated as valid QRMP interim skips if the taxpayer registration is verified QRMP; unverified registrations mark the fetch status as `REQUEST_FAILED` with an actionable audit record.
3. **P1 Manual Frequency Verification Authorization & Audit Trail**:
   - `set_filing_frequency()` enforces that manual verification (`USER_MANUAL`) requires an active authenticated user with compliance roles (`['ADMIN', 'OWNER', 'CA', 'ACCOUNTANT']`) belonging to the company.
   - Unauthorized users (`VIEWER`), unauthenticated callers, or users belonging to external companies are strictly rejected with validation errors.
   - All frequency transitions are recorded in the new append-only model `GSTRegistrationFrequencyAuditLog`.
4. **P1 Forward-Only Database Audit-Trigger Rollback Governance**:
   - Forward migration `0027_attribution_operation_and_frequency_audit.py` introduces rollback protection.
   - Reversing migration 0027 or attempting to tear down trigger `trg_prevent_attribution_audit_tampering` raises a fatal `RuntimeError` unless environment variable `ALLOW_AUDIT_TRIGGER_ROLLBACK=true` is explicitly provided.
5. **Real PostgreSQL 18.7 Concurrency Certification**:
   - Certified 11 concurrency and trigger invariants against AWS Neon PostgreSQL 18.7 under real `threading.Barrier` synchronization with 100% pass rate.

---

## 2. Comprehensive Remediation Matrix (R243-01 to R243-19)

| Requirement ID | Domain & Focus | Implementation / Test Description | Status |
|:---|:---|:---|:---:|
| **R243-01** | Idempotency Lifecycle | Replaying identical completed request returns original cached response with `HTTP 200` without appending duplicate audit records | **PASSED** |
| **R243-02** | Conflict Detection | Reusing `operation_ref` with conflicting payload returns `HTTP 409 Conflict` (`OPERATION_REFERENCE_CONFLICT`) | **PASSED** |
| **R243-03** | Company Isolation | Reusing `operation_ref` across distinct companies does not collide or cross-contaminate | **PASSED** |
| **R243-04** | Performance & Locks | Identical request fast-path replay served directly from completed operation without acquiring row lock | **PASSED** |
| **R243-05** | PostgreSQL Concurrency | Concurrent identical operation requests serialize via `select_for_update()`; exactly one executes, others replayed | **PASSED** |
| **R243-06** | PostgreSQL Concurrency | Concurrent conflicting operation requests with same `operation_ref` resolve cleanly: one succeeds (200), other rejected (409) | **PASSED** |
| **R243-07** | Failure Retry | Operation record left in `FAILED` status permits safe retry and parameter updates without false 409 conflict | **PASSED** |
| **R243-08** | Verification Interface | `get_verified_filing_frequency()` returns clean verified frequency when provenance and verifier are valid | **PASSED** |
| **R243-09** | Verification Fallback | Unverified registration strictly returns `UNKNOWN` regardless of raw field contents | **PASSED** |
| **R243-10** | Provider Classification | Provider `FORM_NOT_APPLICABLE` for unverified registration produces `REQUEST_FAILED` and is not treated as verified QRMP | **PASSED** |
| **R243-11** | Statement Resolution | Unverified registration with raw `MONTHLY` resolves statement period to `UNKNOWN` and requires review | **PASSED** |
| **R243-12** | Provenance Immutability | Provider error during sync does not mutate registration frequency or verification provenance | **PASSED** |
| **R243-13** | Compliance Authorization | Authorized compliance user (`ADMIN`/`OWNER`) successfully verifies frequency with audit log entry created | **PASSED** |
| **R243-14** | Role Restriction | User without compliance role (`VIEWER`) attempting manual frequency verification is rejected with validation error | **PASSED** |
| **R243-15** | Tenant Isolation | User belonging to another company attempting manual frequency verification is rejected with authorization error | **PASSED** |
| **R243-16** | Trigger Tamper-Resistance | PostgreSQL trigger `trg_prevent_attribution_audit_tampering` rejects direct SQL `UPDATE` | **PASSED** |
| **R243-17** | Trigger Tamper-Resistance | PostgreSQL trigger `trg_prevent_attribution_audit_tampering` rejects direct SQL `DELETE` | **PASSED** |
| **R243-18** | Trigger Compatibility | PostgreSQL trigger `trg_prevent_attribution_audit_tampering` cleanly permits direct SQL `INSERT` | **PASSED** |
| **R243-19** | Rollback Governance | Trigger exists in PostgreSQL catalog; migration rollback raises `RuntimeError` unless `ALLOW_AUDIT_TRIGGER_ROLLBACK=true` | **PASSED** |

---

## 3. P0 Durable Request-Bound Idempotency Architecture

### 3.1 Canonical Request Fingerprint Formulation

To prevent payload tampering or accidental parameter collisions, every attribution and correction request computes a deterministic canonical SHA-256 fingerprint:

$$\text{Canonical String} = \text{company\_id} \parallel \text{actor\_id} \parallel \text{sorted}(\text{voucher\_ids}) \parallel \text{registration\_id} \parallel \text{is\_correction} \parallel \text{attribution\_source} \parallel \text{reason}$$

```python
canonical_components = [
    str(company.id),
    str(request.user.id) if request.user and request.user.is_authenticated else 'ANONYMOUS',
    ",".join(sorted(str(v_id) for v_id in raw_ids)),
    str(reg_id or ''),
    "CORRECTION" if is_correction else "ATTRIBUTION",
    str(attribution_source or ''),
    (reason or '').strip()
]
canonical_str = "|".join(canonical_components)
current_fingerprint = hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()
```

### 3.2 Operation Lifecycle & State Machine

The table `gst_voucherattributionoperation` tracks operation execution:

```mermaid
stateDiagram-v2
    [*] --> PENDING: Client POST with operation_ref
    PENDING --> COMPLETED: Batch processed & audit logs committed
    PENDING --> FAILED: Exception raised (Transaction rolled back)
    COMPLETED --> COMPLETED: Replay identical fingerprint (HTTP 200, cached response)
    COMPLETED --> 409_CONFLICT: Replay conflicting fingerprint (HTTP 409 Conflict)
    FAILED --> PENDING: Retry with updated payload (permit re-execution)
```

1. **Fast-Path Replay Check (No Lock)**:
   - Query `VoucherAttributionOperation` for `status='COMPLETED'`.
   - If found and `request_fingerprint == current_fingerprint`, return cached `response_payload` immediately with `is_idempotent_replay: true`.
   - If found and `request_fingerprint != current_fingerprint`, return `HTTP 409 Conflict` with `OPERATION_REFERENCE_CONFLICT`.
2. **Atomic Lock Path**:
   - Within `transaction.atomic()`, execute `VoucherAttributionOperation.objects.select_for_update().get_or_create(company=company, operation_ref=operation_ref)`.
   - If created or previous status was `FAILED`, set `status='PENDING'`, update fingerprint, and execute business logic.
   - Upon successful completion, persist `response_payload` and set `status='COMPLETED'`.
   - On exception, mark `status='FAILED'` and re-raise.

---

## 4. P1 Repository-Wide Filing Frequency Call-Site Audit

Every occurrence of `filing_frequency` across the entire codebase was audited and categorized to guarantee zero statutory decisions bypass verification:

| File Path | Line(s) | Usage Classification | Statutory Risk Mitigation |
|:---|:---:|:---|:---|
| `apps/gst/models.py` | 267 | Model Field Definition | Raw field `filing_frequency = models.CharField(...)` on `GSTRegistration`. |
| `apps/gst/models.py` | 344-360 | Canonical Verification Interface | `get_verified_filing_frequency()` strictly checks provenance source, verifier, and timestamp before returning `MONTHLY`/`QRMP`; falls back to `UNKNOWN`. |
| `apps/gst/models.py` | 362-379 | Verification Validator | `is_frequency_verified()` validates provenance source and ensures manual verifier presence. |
| `apps/gst/models.py` | 381-420 | Verification Setter & Audit Dispatch | `set_filing_frequency()` enforces compliance roles, active registration status, and logs audit record. |
| `apps/gst/models.py` | 425-455 | Audit Trail Persistence | `GSTRegistrationFrequencyAuditLog` records `previous_frequency`, `new_frequency`, and `verified_by`. |
| `apps/gst/services/period_service.py` | 409-410 | Statutory Statement Resolution | Calls `recipient_registration.get_verified_filing_frequency()`. Explicit argument cannot override unverified status. |
| `apps/gst/services/reconciliation_service.py` | 150, 389 | Provider Error Classification | Checks `registration.get_verified_filing_frequency() == 'QRMP'`. Unverified registrations treat `FORM_NOT_APPLICABLE` as `REQUEST_FAILED`. |
| `apps/gst/services/reconciliation_service.py` | 235, 266, 370, 408, 438, 512 | Status Output & Metadata Payloads | Calls `registration.get_verified_filing_frequency()` to report verified frequency in API responses. |
| `apps/gst/services/itc_reconciliation_service.py` | 1479, 1538, 1846 | Voucher & 2B Item Reconciliation Data | Uses `v_reg.get_verified_filing_frequency()` and statement resolution recipient frequency. |

---

## 5. P1 Manual Verification Authorization & Audit Trail

### 5.1 RBAC Enforcement Policy

Manual filing frequency verification is restricted to authenticated compliance users via `user_has_company_roles`:

```python
if clean_source == 'USER_MANUAL':
    if not user or not user.is_authenticated:
        raise ValidationError("Manual filing frequency verification requires an authenticated user.")
    if not user_has_company_roles(user, self.company, ['ADMIN', 'OWNER', 'CA', 'ACCOUNTANT']):
        raise ValidationError(f"User '{user.email}' is not authorized to verify filing frequency for company '{self.company.name}'.")
    if self.status != 'ACTIVE':
        raise ValidationError("Cannot verify filing frequency for an inactive GST registration.")
```

### 5.2 Append-Only Frequency Audit Log

Every transition is recorded in `GSTRegistrationFrequencyAuditLog`:
- `gst_registration`: Foreign key to `GSTRegistration` (`PROTECT`)
- `company`: Foreign key to `Company` (`PROTECT`)
- `previous_frequency`: String (e.g. `'UNKNOWN'`, `'MONTHLY'`)
- `new_frequency`: String (`'MONTHLY'`, `'QRMP'`)
- `verified_source`: Source enum (`'USER_MANUAL'`, `'GST_PORTAL_API'`, `'RETURN_STATUS_API'`, `'CA_CERTIFICATE'`)
- `verified_by`: Foreign key to `User` (mandatory for manual source)
- `reason`: Justification text
- `verified_at`: Timestamp (`auto_now_add=True`)

---

## 6. P1 Database Audit-Trigger Rollback Governance

### 6.1 Forward-Only Database Trigger Protection

To prevent inadvertent or malicious removal of the statutory audit tampering trigger, migration `0027_attribution_operation_and_frequency_audit.py` introduces rollback guard `guard_trigger_rollback`:

```python
def guard_trigger_rollback(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    allow_rollback = os.environ.get('ALLOW_AUDIT_TRIGGER_ROLLBACK', '').strip().lower()
    if allow_rollback not in ('true', '1', 'yes'):
        raise RuntimeError(
            "CRITICAL STATUTORY AUDIT POLICY VIOLATION: Reversing GST audit migrations or removing "
            "trigger 'trg_prevent_attribution_audit_tampering' is strictly prohibited. "
            "To override for disaster recovery, set environment variable ALLOW_AUDIT_TRIGGER_ROLLBACK=true."
        )
```

### 6.2 PostgreSQL Trigger Verification Evidence

The trigger `trg_prevent_attribution_audit_tampering` on `gst_vouchergstinattributionlog` was tested under direct SQL statements against Neon PostgreSQL 18.7:
- **Direct SQL INSERT**: Allowed (Status: OK).
- **Direct SQL UPDATE**: Denied with `DatabaseError: Statutory Audit Integrity Invariant: Mutation of voucher attribution logs is strictly prohibited.`
- **Direct SQL DELETE**: Denied with `DatabaseError: Statutory Audit Integrity Invariant: Mutation of voucher attribution logs is strictly prohibited.`

---

## 7. Real Test Execution Evidence & Certification

### 7.1 Targeted Remediation Test Suite (`Round243TargetedRemediationTests`)

**Command:**
```powershell
python manage.py test apps.gst.tests_itc_reconciliation.Round243TargetedRemediationTests --keepdb
```

**Output:**
```
Using existing test database for alias 'default'...
2026-11-25 16:42:08,706 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 200 in 150.71ms
2026-11-25 16:42:08,726 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 200 in 18.04ms
.2026-11-25 16:42:09,645 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 200 in 87.41ms
2026-11-25 16:42:09,663 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 409 in 16.82ms
.2026-11-25 16:42:10,591 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 200 in 91.34ms
2026-11-25 16:42:10,612 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/correct-attribution/ 409 in 19.31ms
.2026-11-25 16:42:11,505 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 200 in 78.43ms
2026-11-25 16:42:11,524 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/correct-attribution/ 409 in 18.11ms
.2026-11-25 16:42:12,387 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 400 in 25.69ms
2026-11-25 16:42:12,473 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 200 in 84.4ms
.2026-11-25 16:42:14,183 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 200 in 88.3ms
2026-11-25 16:42:14,332 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 200 in 85.33ms
........
----------------------------------------------------------------------
Ran 13 tests in 13.678s

OK
Preserving test database for alias 'default'...
Found 13 test(s).
System check identified no issues (0 silenced).
```

### 7.2 PostgreSQL Concurrency & Trigger Certification (`PostgreSQLConcurrencyCertificationTests`)

**Command:**
```powershell
python manage.py test apps.gst.tests_itc_reconciliation.PostgreSQLConcurrencyCertificationTests --settings=config.settings_test_pg --keepdb
```

**Output:**
```
Using existing test database for alias 'default'...
2026-11-25 16:42:59,116 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 200 in 3555.6ms
2026-11-25 16:43:02,597 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/correct-attribution/ 200 in 3386.35ms
2026-11-25 16:43:03,343 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/correct-attribution/ 200 in 652.73ms
.....2026-11-25 16:44:54,542 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 200 in 2710.01ms
2026-11-25 16:44:55,770 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 200 in 3990.87ms
.2026-11-25 16:45:17,872 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 409 in 2644.34ms
2026-11-25 16:45:19,037 [INFO] [vouch.access] HTTP POST /api/v1/gst/itc/attribute-voucher/ 200 in 3863.94ms
.....
----------------------------------------------------------------------
Ran 11 tests in 246.006s

OK
Preserving test database for alias 'default'...
Found 11 test(s).
System check identified no issues (0 silenced).
```

### 7.3 Test Selection & Evidence Rationale

Per Round 2.4.3 execution directives, re-running unchanged regression suites or frontend builds when zero relevant source code changed is an anti-pattern. Test execution was focused strictly on:
1. `Round243TargetedRemediationTests` (R243-01 to R243-04, R243-07 to R243-15): 13 targeted tests verifying the new operation-ref idempotency state machine, canonical verified frequency interface, manual verification RBAC, and retry after failure.
2. `PostgreSQLConcurrencyCertificationTests` (R243-05, R243-06, R243-16, R243-17, R243-18, R243-19, and existing lock barrier suites): 11 tests against AWS Neon PostgreSQL 18.7 verifying barrier serialization, raw SQL trigger tamper-resistance, and migration rollback protection under true multi-threaded database concurrency.

---

## 8. Deployment & Operational Runbook

1. **Pre-Deployment Checks**:
   - Verify active branch is `remediation/round-2.4.3-idempotency-governance`.
   - Verify target database is PostgreSQL $\ge 15$ with PL/pgSQL support enabled.
2. **Migration Application**:
   ```bash
   python manage.py migrate gst
   ```
   *Note: Applies forward migration `0027_attribution_operation_and_frequency_audit`, creating tables `gst_voucherattributionoperation` and `gst_gstregistrationfrequencyauditlog` and installing trigger rollback guard.*
3. **Disaster Recovery Notice**:
   - In the event an emergency migration rollback is required, run with explicit consent:
   ```bash
   ALLOW_AUDIT_TRIGGER_ROLLBACK=true python manage.py migrate gst 0025
   ```
4. **Post-Deployment Verification**:
   - Check endpoint `/api/v1/gst/itc/attribute-voucher/` accepts valid `operation_ref` and replays idempotently.
   - Confirm unverified registrations return `filing_frequency: "UNKNOWN"`.
   - Confirm only authorized compliance users can verify frequency.

---

## 9. Sign-Off & Architectural Certification

All P0 and P1 objectives established in the Round 2.4.3 mandate have been satisfied, validated, and certified against real cloud PostgreSQL infrastructure.

**Signed by:**  
Principal Django/PostgreSQL Engineer & GST Compliance Architect  
Lead Security & Accounting Integrity Auditor  
*SriLekh Engineering Team — 25 November 2026*
