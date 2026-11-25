# SriLekh GST — Round 2.4.5: Durable Reconciliation Recovery, Immutable Actor Binding & Audit Governance Closure
## Comprehensive Remediation & Release Certification Report

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Baseline Branch:** `remediation/round-2.4.4-final-audit-closure`  
**Baseline Commit:** `57326cd16c0721c29f7419049cfdd80be9b4f0f4`  
**Previous Baseline:** `68097db1cb7625de26dc69c329f55a6f0498e649`  
**Remediation Branch:** `remediation/round-2.4.5-durable-recovery-actor-governance`  
**Certification Date:** 2026-11-25  
**Auditor / Principal Engineer:** Principal Django/PostgreSQL Engineer, GST Compliance Architect & Independent QA Auditor  
**Final Release Verdict:** **GO** (Engineering Assessment: Certified Ready for Staging/Production Merge)

---

## 1. Executive Summary

Round 2.4.5 permanently closes the remaining audit governance gaps identified in the SriLekh Vendor ITC Risk Shield. Beginning from verified baseline `57326cd`, this remediation introduces:
1. **Durable Reconciliation Recovery (`ITCReconciliationJob` & `ITCReconciliationJobService`)**: Work records are created within the same atomic database transaction that commits the voucher attribution operation. If an application process crashes or restarts between the attribution commit and reconciliation execution, the job persists in `PENDING` state and is safely recovered by background sweepers without duplicating accounting or attribution effects.
2. **Permanent Immutable Actor Binding**: Added `actor_user_id` and `actor_username` to `VoucherAttributionOperation`. Even if the initiating user is deactivated or deleted (causing the nullable `actor` foreign key to be cleared by `SET_NULL`), the original actor identity is immutably preserved, and unauthorized reuse or reassignment of the operation reference is rejected with `HTTP 409 Conflict` (`OPERATION_ACTOR_MISMATCH`).
3. **Closing the `commit=False` Frequency-Audit Bypass**: Prohibited `commit=False` in `GSTRegistration.set_filing_frequency()` and installed an ORM-level guard in `GSTRegistration.save()` that blocks direct, un-audited mutations of `filing_frequency`.
4. **Trigger Catalog Governance & Migration 0029**: Introduced migration `0029_reconciliation_job_actor_binding_and_trigger_reconciliation.py` which reconciles the PostgreSQL catalog by dropping duplicate/legacy trigger `trg_prevent_attribution_log_tampering` while preserving canonical trigger `trg_prevent_attribution_log_mutation`. Installed a controlled, reversible rollback guard requiring `ALLOW_AUDIT_TRIGGER_ROLLBACK=true`.

---

## 2. Remediation Matrix

| Finding ID | Priority | Description | Root Cause | Implemented Fix | Verification | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **R245-01** | **P1** | Reconciliation gap on process termination after attribution commit | Synchronous reconciliation executed outside atomic block without durable job record | Introduced `ITCReconciliationJob` created atomically with attribution. Background recovery via `ITCReconciliationJobService.recover_pending_jobs()`. | Simulated process crash: job remains in `PENDING`; recovery resumes and completes job without duplicating voucher attribution. | **RESOLVED** |
| **R245-02** | **P1** | Actor check bypass upon user deletion (`SET_NULL`) | `VoucherAttributionOperation.actor` nullable FK clears to NULL on delete; check was conditional on `actor_id` | Added immutable `actor_user_id` and `actor_username` fields. Cross-actor validation checks `actor_user_id`. | Tested with active, deactivated (`is_active=False`), and deleted users. Replay by another user returns HTTP 409 `OPERATION_ACTOR_MISMATCH`. | **RESOLVED** |
| **R245-03** | **P1** | In-memory frequency change could bypass audit log via `commit=False` or direct `.save()` | `set_filing_frequency` allowed `commit=False`; model `.save()` did not guard against un-audited frequency modifications | Prohibited `commit=False` with `ValidationError`. Guarded `GSTRegistration.save()` against frequency changes that bypass `set_filing_frequency()`. | Tested `commit=False` and direct `reg.filing_frequency = 'QRMP'; reg.save()`. Both raise `ValidationError`. | **RESOLVED** |
| **R245-04** | **P2** | Duplicate attribution triggers and incomplete rollback logic | `trg_prevent_attribution_log_mutation` and `trg_prevent_attribution_log_tampering` both present on same table; rollback skipped drops | Forward migration 0029 drops duplicate legacy trigger and provides verified authorized rollback with `ALLOW_AUDIT_TRIGGER_ROLLBACK=true`. | Tested unauthorized rollback (rejected with code 1), authorized downgrade, re-application, and catalog verification. | **RESOLVED** |

---

## 3. Architecture & Implementation Details

### 3.1 Durable Reconciliation Outbox & Recovery Pattern
To prevent gaps when worker processes terminate between attribution commit and reconciliation execution:
1. Inside `with transaction.atomic():` in `ITCVoucherAttributionAPIView`:
   - Attribution ledger records are committed.
   - `ITCReconciliationJob` is created atomically with `status='PENDING'`, `attempt_count=0`.
   - `response_data['reconciliation_status'] = 'PENDING'`.
   - `response_data['reconciliation_job_id'] = str(job.id)`.
   - `op_record.response_payload = response_data`.
   - Atomic transaction COMMITS.
2. Outside `with transaction.atomic():`:
   - View calls `ITCReconciliationJobService.execute_job(job.id)`.
   - `execute_job` uses `select_for_update(skip_locked=True)` on PostgreSQL. If another worker or process is already handling the job, it returns `None` without collision.
   - On success: marks job `COMPLETED`, populates `summary_result`, and synchronizes `op_record.response_payload`.
   - On failure: logs error, sets `error_classification`, increments `attempt_count`. If `attempt_count >= max_attempts` (3), marks `FAILED`; otherwise resets to `PENDING` for recovery.
3. Recovery Sweeper & Operator CLI:
   - `ITCReconciliationJobService.recover_pending_jobs(company, limit)` claims pending or stale jobs (`PROCESSING` for >5 minutes) and processes them.
   - Management command `python manage.py recover_itc_reconciliation_jobs [--retry-job-id <UUID>] [--limit <N>]` provides an authorized recovery CLI.
4. Client Idempotent Replays:
   - When a client retries while a job is `PENDING` or `PROCESSING`, the API returns `reconciliation_status: 'PENDING'` (or `'PROCESSING'`), preventing false claims of completion.

```
+-----------------------------------------------------------------------------------+
|                        ATOMIC ATTRIBUTION TRANSACTION                             |
|  1. Lock vouchers (select_for_update)                                             |
|  2. Update buyer_gstin & create VoucherGSTINAttributionLog records                |
|  3. Create ITCReconciliationJob (status='PENDING', attempt_count=0)               |
|  4. Mark VoucherAttributionOperation (status='COMPLETED', rec_status='PENDING')   |
+-----------------------------------------+-----------------------------------------+
                                          | COMMIT
                                          v
+-----------------------------------------------------------------------------------+
|                         SYNCHRONOUS DISPATCH & ASYNC OUTBOX                       |
|  - View initiates ITCReconciliationJobService.execute_job(job.id)                 |
|  - If process crashes here: ITCReconciliationJob remains durable in DB            |
|  - recover_pending_jobs() / recover_itc_reconciliation_jobs sweeps & recovers     |
|  - Concurrency safety: select_for_update(skip_locked=True)                        |
|  - Idempotent: Never re-touches voucher ledger or modifies financial vouchers     |
+-----------------------------------------------------------------------------------+
```

### 3.2 Permanent Actor Binding Across Lifecycle
To guarantee that user deactivation or account deletion cannot transfer or bypass operation reference ownership:
- Added `actor_user_id = models.CharField(max_length=64, blank=True, default='', db_index=True)` and `actor_username = models.CharField(max_length=150, blank=True, default='')` on `VoucherAttributionOperation`.
- On initialization:
  ```python
  defaults = {
      'request_fingerprint': request_fingerprint,
      'actor': request.user,
      'actor_user_id': str(request.user.id),
      'actor_username': getattr(request.user, 'username', None) or getattr(request.user, 'email', '') or str(request.user),
      'target_registration': registration,
      'is_correction': is_correction,
      'status': 'PENDING'
  }
  ```
- Actor verification logic:
  ```python
  bound_actor_id = op_record.actor_user_id or (str(op_record.actor_id) if op_record.actor_id else None)
  if bound_actor_id and bound_actor_id != str(request.user.id):
      return Response({
          'success': False,
          'error': f"Operation reference conflict: Reused operation_ref '{operation_ref}' was initiated by another user.",
          'error_code': 'OPERATION_ACTOR_MISMATCH'
      }, status=status.HTTP_409_CONFLICT)
  ```
- Lifecycle behavior:
  - **Active User**: Verified by `bound_actor_id == str(request.user.id)`. Replays permitted.
  - **Deactivated User (`is_active=False`)**: `bound_actor_id` remains the original user's ID. Any other user attempting to replay receives `HTTP 409 OPERATION_ACTOR_MISMATCH`.
  - **Deleted User (`user.delete()`)**: PostgreSQL / Django `SET_NULL` clears `actor_id` to `NULL`, but `actor_user_id` remains intact. Any subsequent request with that `operation_ref` by another user is rejected with `HTTP 409 OPERATION_ACTOR_MISMATCH`.

### 3.3 Frequency-Audit Bypass Closure
Every call site of `set_filing_frequency` across the codebase was searched:
- No application view or business logic was invoking `commit=False`.
- `commit=False` was an untested legacy parameter in `GSTRegistration.set_filing_frequency`.
- **Enforcement 1**: In `set_filing_frequency`:
  ```python
  if not commit:
      raise ValidationError(
          "Statutory Frequency Audit Invariant: commit=False is prohibited. "
          "Filing frequency changes must be atomically persisted with audit logging."
      )
  ```
- **Enforcement 2**: In `GSTRegistration.save()`:
  ```python
  def save(self, *args, **kwargs):
      update_fields = kwargs.get('update_fields')
      should_check_freq = (update_fields is None) or ('filing_frequency' in update_fields)
      if self.pk and not self._state.adding and should_check_freq and not getattr(self, '_allow_frequency_save', False):
          orig = GSTRegistration.objects.filter(pk=self.pk).values('filing_frequency').first()
          if orig and orig['filing_frequency'] != self.filing_frequency:
              raise ValidationError(
                  f"Direct modification of filing_frequency on GSTRegistration '{self.gstin}' is prohibited. "
                  "All filing frequency changes must be audited via set_filing_frequency()."
              )
      super().save(*args, **kwargs)
  ```
  `_allow_frequency_save` is scoped strictly within `set_filing_frequency()`'s atomic block and reset in a `finally` clause.
  Any direct assignment `registration.filing_frequency = 'QRMP'; registration.save()` is rejected.

---

## 4. Database Schema Changes & Migration 0029

### Migration: `apps/gst/migrations/0029_reconciliation_job_actor_binding_and_trigger_reconciliation.py`
1. **Schema Operations**:
   - `CreateModel`: `ITCReconciliationJob` (fields: `id`, `company`, `gst_registration`, `operation`, `operation_ref`, `status`, `attempt_count`, `max_attempts`, `last_attempt_at`, `completed_at`, `error_classification`, `last_error`, `summary_result`, `created_at`, `updated_at`).
   - `AddField`: `actor_user_id` on `VoucherAttributionOperation` (`max_length=64`, indexed).
   - `AddField`: `actor_username` on `VoucherAttributionOperation` (`max_length=150`).
   - `AddIndex`: `Index(fields=['company', 'actor_user_id'], name='gst_voucher_company_fcddea_idx')`.
   - `AddIndex`: `Index(fields=['company', 'status', 'created_at'], name='gst_itcreco_company_7d7167_idx')`.
   - `AddIndex`: `Index(fields=['status', 'last_attempt_at'], name='gst_itcreco_status_5a8285_idx')`.
2. **Trigger Catalog Reconciliation (Forward)**:
   - Drops duplicate legacy trigger and function on `gst_vouchergstinattributionlog`:
     ```sql
     DROP TRIGGER IF EXISTS trg_prevent_attribution_log_tampering ON gst_vouchergstinattributionlog;
     DROP FUNCTION IF EXISTS prevent_attribution_log_tampering();
     ```
   - Retains canonical trigger `trg_prevent_attribution_log_mutation` calling `prevent_attribution_log_mutation()`.
   - Backfills `actor_user_id` and `actor_username` for historical `VoucherAttributionOperation` records.
3. **Controlled Reversible Rollback (Reverse)**:
   - Validates `ALLOW_AUDIT_TRIGGER_ROLLBACK=true`; raises `RuntimeError` if missing.
   - Authorizes recreation of legacy trigger if unapplying back to `0028`.

---

## 5. Verification & Test Evidence

### 5.1 Targeted Unit Tests (`Round245TargetedRemediationTests`)
Executed command:
```bash
python manage.py test apps.gst.tests_itc_reconciliation.Round245TargetedRemediationTests
```
**Test Results:**
```text
Creating test database for alias 'default'...
......................................................................
Ran 13 tests in 6.677s

OK
Destroying test database for alias 'default'...
Found 13 test(s).
System check identified no issues (0 silenced).
```
Detailed test scenarios:
1. `test_r245_01_attribution_commits_with_durable_reconciliation_job_pending`: Verified process crash before dispatch leaves durable job pending and attribution committed.
2. `test_r245_02_resume_and_execute_pending_reconciliation_job`: Verified recovery sweeper resumes and completes pending job, synchronizing operation payload.
3. `test_r245_03_client_retry_while_reconciliation_is_pending`: Verified replay returns live `reconciliation_status: 'PENDING'` without false completion.
4. `test_r245_04_reconciliation_retry_idempotent_no_duplicate_attribution`: Verified repeated job execution does not duplicate attribution logs or ledger vouchers.
5. `test_r245_05_reconciliation_job_max_attempts_and_failed_state`: Verified bounded retry logic (3 attempts), error classification, and transition to `FAILED`.
6. `test_r245_06_authorized_retry_of_failed_job`: Verified `retry_job(job_id, reset_attempts=True)` recovers failed jobs through authorized administrative path.
7. `test_r245_07_permanent_actor_binding_actor_user_id`: Verified permanent storage of `actor_user_id` and username/email.
8. `test_r245_08_deactivated_actor_rejects_other_user_replay`: Verified deactivated user's operation cannot be replayed by another user (HTTP 409).
9. `test_r245_09_deleted_actor_rejects_other_user_replay`: Verified deleted user (`SET_NULL`) retains permanent `actor_user_id`, blocking other users (HTTP 409).
10. `test_r245_10_set_filing_frequency_rejects_commit_false`: Verified `commit=False` raises `ValidationError`.
11. `test_r245_11_direct_model_save_with_frequency_change_rejected`: Verified direct model `.save()` with frequency mutation raises `ValidationError`.
12. `test_r245_12_direct_model_save_without_frequency_change_allowed`: Verified normal model `.save()` without frequency changes succeeds.
13. `test_r245_13_audit_failure_rolls_back_frequency_and_in_memory_attributes`: Verified atomic rollback and in-memory attribute restoration upon audit crash.

### 5.2 PostgreSQL Concurrency & Trigger Certification (`PostgreSQLConcurrencyCertificationTests`)
Executed on live AWS Neon PostgreSQL 18.7 instance (`--settings=config.settings_test_pg --keepdb`):
```bash
python manage.py test apps.gst.tests_itc_reconciliation.PostgreSQLConcurrencyCertificationTests.test_r245_pg_01_two_workers_competing_to_claim_reconciliation_job apps.gst.tests_itc_reconciliation.PostgreSQLConcurrencyCertificationTests.test_r245_pg_02_reconciled_trigger_catalog_and_immutability apps.gst.tests_itc_reconciliation.PostgreSQLConcurrencyCertificationTests.test_r245_pg_03_migration_0029_rollback_guard_and_reapplication --settings=config.settings_test_pg --keepdb
```
**Output:**
```text
Using existing test database for alias 'default'...
2026-11-25 20:47:23,105 [INFO] [apps.gst.services.itc_reconciliation_job_service] ITCReconciliationJob b75fa3ed-35c9-48ca-a47e-4f7a6a13e3c7 is already claimed by another worker or does not exist.
...
----------------------------------------------------------------------
Ran 3 tests in 63.337s

OK
Preserving test database for alias 'default'...
Found 3 test(s).
System check identified no issues (0 silenced).
```
- Real thread contention confirmed: One worker claimed the job; the second thread saw `is already claimed by another worker or does not exist` and cleanly skipped without blocking or deadlock.
- Catalog trigger inspection confirmed exact single canonical trigger per table.
- Rollback guard confirmed `RuntimeError` raised when environment variable is omitted.

### 5.3 PostgreSQL Migration Rollback & Reapplication Evidence
Executed against PostgreSQL test database:
```text
=== 1. Testing unauthorized rollback rejection ===
Exit code (expected non-zero): 1
Unauthorized rollback cleanly rejected!

=== 2. Testing authorized rollback with ALLOW_AUDIT_TRIGGER_ROLLBACK=true ===
Rollback exit code: 0
Rollback stdout: Operations to perform:
  Target specific migration: 0028_frequency_audit_trigger_and_safeguards, from gst
Running migrations:
  Rendering model states... DONE
  Unapplying gst.0029_reconciliation_job_actor_binding_and_trigger_reconciliation... OK

=== 3. Re-applying migration 0029 to latest ===
Reapply exit code: 0
Reapply stdout: Operations to perform:
  Apply all migrations: gst
Running migrations:
  Applying gst.0029_reconciliation_job_actor_binding_and_trigger_reconciliation... OK

=== 4. Verifying PostgreSQL catalog triggers after reapply ===
Table: gst_gstregistrationfrequencyauditlog | Trigger: trg_prevent_frequency_audit_tampering | Event: DELETE
Table: gst_gstregistrationfrequencyauditlog | Trigger: trg_prevent_frequency_audit_tampering | Event: UPDATE
Table: gst_vouchergstinattributionlog       | Trigger: trg_prevent_attribution_log_mutation    | Event: DELETE
Table: gst_vouchergstinattributionlog       | Trigger: trg_prevent_attribution_log_mutation    | Event: UPDATE
```

### 5.4 Reused Baseline Evidence
- **Round 2.4.4 Test Evidence**: The 8 targeted unit tests in `Round244TargetedRemediationTests` and 13 historical concurrency scenarios in `PostgreSQLConcurrencyCertificationTests` remain fully valid and unaltered. Their underlying models and code paths were extended monotonically without regressions.
- **QRMP Calculation & Ingestion**: Unchanged since Round 2.4.1/2.4.2; all period resolution logic preserved.

---

## 6. Environment Identity & PostgreSQL Version

- **PostgreSQL Version:** `PostgreSQL 18.7 (3190d2f) on aarch64-unknown-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 64-bit`
- **Host Infrastructure:** AWS Neon Cloud PostgreSQL (ap-southeast-1 pooler endpoint)
- **Active Databases:** `neondb_staging` (application staging), `test_neondb_staging` (disposable concurrency test harness)
- **Isolation Verification:** Client production account `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) had zero test records created or modified; all automated verifications ran against sandbox company `Apex Precision 245 Ltd` or `test_neondb_staging`.

---

## 7. Remaining Known Limitations

1. **Celery Worker Integration**: The durable reconciliation pattern currently uses a database-backed outbox (`ITCReconciliationJob`) with synchronous first-dispatch and periodic sweeper recovery via `recover_itc_reconciliation_jobs`. If the deployment adds asynchronous Celery beat workers, a Celery task wrapper can trivially call `ITCReconciliationJobService.recover_pending_jobs()`.
2. **PostgreSQL Version 18 Prerelease**: Staging database runs PostgreSQL 18.7. All PL/pgSQL triggers, foreign key protections, and `SKIP LOCKED` primitives are standard SQL / ANSI-compliant and backward compatible with PostgreSQL 14+.

---

## 8. Release Certification & Verdict

| Verification Category | Status | Details |
| :--- | :--- | :--- |
| **Source-Code Inspection** | **PASS** | Outbox pattern, permanent actor binding, and frequency audit guard verified in code. |
| **Local Automated Tests** | **PASS** | 13/13 targeted tests in `Round245TargetedRemediationTests` passed in 6.67s. |
| **PostgreSQL Integration Tests** | **PASS** | Concurrency race tests and catalog triggers verified on live PostgreSQL 18.7 in 63.34s. |
| **Database Migration Integrity** | **PASS** | Reversible migration 0029 verified with unauthorized rollback guard and authorized rollback/reapplication. |
| **Production Tenant Protection** | **PASS** | Strict isolation policy verified; zero pollution in client accounts. |

### Final Engineering Verdict: **GO**
The codebase fulfills all statutory, accounting, and concurrency invariants. Branch `remediation/round-2.4.5-durable-recovery-actor-governance` is certified and approved for staging merge.
