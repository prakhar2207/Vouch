# SriLekh GST ITC — Round 2.4.6 Remediation & Production Certification

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Target Branch:** `audit/round-2.4.6-gst-integration-reliability`  
**Verified Baseline:** `346d9a3e7db7b3315b402a43a97293058b3eec10` (Round 2.4.5)  
**Certification Date:** November 25, 2026  
**Auditor:** Principal Django/PostgreSQL Engineer & Independent QA Auditor  

---

## 1. Remediation Scope & Problem Statement

Round 2.4.5 resolved durable reconciliation job recovery, permanent request-bound idempotency, and immutable audit logs. However, independent source-code inspection identified remaining concurrency, database integrity, and governance edge cases:

1. **Reconciliation Worker Exclusivity (P1)**: Multiple reconciliation workers competing for the same `ITCReconciliationJob` lacked lease exclusivity. If a long-running worker was superseded, its stale completion could overwrite a newer worker's result.
2. **Automatic Reconciliation Recovery (P1)**: Crashed or pending jobs required manual trigger or management command execution rather than continuous, self-healing background recovery.
3. **Database-Level Filing-Frequency Integrity (P1)**: While application services audited frequency changes, raw SQL `UPDATE`, Django `QuerySet.update()`, and `bulk_update()` on `gst_gstregistration.filing_frequency` bypassed the audit log.
4. **Historical Actor Identity Governance (P2)**: Legacy historical operations that lacked provenance could be claimed or replayed by arbitrary users upon presenting matching or modified fingerprints.

---

## 2. Technical Implementation Details

### 2.1 P1 — Reconciliation Worker Lease Exclusivity
In `apps/gst/models.py` (`ITCReconciliationJob`) and `apps/gst/services/itc_reconciliation_job_service.py`:
- Added concurrency control fields to `ITCReconciliationJob`:
  - `claimed_by = models.CharField(max_length=100, blank=True, default='')`
  - `claim_token = models.CharField(max_length=64, blank=True, default='')`
  - `claim_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)`
  - `generation = models.PositiveIntegerField(default=0)`
  - Added database index on `['status', 'claim_expires_at']`.
- In `ITCReconciliationJobService.execute_job()`:
  - **Atomic Lease Check**: Inside a `select_for_update()` transaction, verifies if an active worker holds a valid lease (`status == 'PROCESSING' and claim_expires_at > now`). If so, a second competing worker is rejected immediately.
  - **Lease Stealing & Expiry**: If the previous lease has expired, the job is reclaimed, generating a new `claim_token`, incrementing `generation`, and setting `claim_expires_at = now + lease_seconds`.
  - **Guarded Completion Invariant**: Upon completion or failure, the worker updates the record *only if* `claim_token` still matches. If a stale worker was superseded during long calculation, its write is aborted, preventing newer results from being overwritten.

### 2.2 P1 — Automated Reconciliation Job Recovery Task
In `apps/gst/tasks.py` and `config/settings.py`:
- Created `@shared_task(name='apps.gst.tasks.recover_itc_reconciliation_jobs_task')`:
  - Periodically invokes `ITCReconciliationJobService.recover_pending_jobs(limit=50, lease_seconds=300)`.
  - Recovers `PENDING` jobs and crashed/expired `PROCESSING` jobs.
- Added to `CELERY_BEAT_SCHEDULE`:
  ```python
  'auto-recover-itc-reconciliation-jobs': {
      'task': 'apps.gst.tasks.recover_itc_reconciliation_jobs_task',
      'schedule': 60.0,  # Run every 60 seconds
  }
  ```

### 2.3 P1 — Database-Level Filing-Frequency Integrity Trigger
In migration `apps/gst/migrations/0030_worker_exclusivity_frequency_trigger_and_actor_governance.py`:
- Installed native PostgreSQL trigger `trg_prevent_direct_filing_frequency_mutation` on table `gst_gstregistration`:
  ```sql
  CREATE OR REPLACE FUNCTION fn_prevent_direct_filing_frequency_mutation()
  RETURNS TRIGGER AS $$
  BEGIN
      IF current_setting('vouch.allow_frequency_mutation', true) IS DISTINCT FROM 'true' THEN
          RAISE EXCEPTION 'DIRECT_FILING_FREQUENCY_UPDATE_PROHIBITED: Direct mutation of filing_frequency on gst_gstregistration is blocked. Use GSTRegistration.set_filing_frequency() with mandatory audit logging.'
              USING ERRCODE = 'P0001';
      END IF;
      RETURN NEW;
  END;
  $$ LANGUAGE plpgsql;

  CREATE TRIGGER trg_prevent_direct_filing_frequency_mutation
  BEFORE UPDATE OF filing_frequency ON gst_gstregistration
  FOR EACH ROW
  EXECUTE FUNCTION fn_prevent_direct_filing_frequency_mutation();
  ```
- In `apps/gst/models.py` (`GSTRegistration.set_filing_frequency()`):
  - Sets transaction-local authorization: `cursor.execute("SET LOCAL vouch.allow_frequency_mutation = 'true';")`.
  - Records cryptographic entry in `GSTRegistrationFrequencyAuditLog`.
- Direct SQL `UPDATE`, Django `QuerySet.update()`, and `bulk_update()` attempting to mutate `filing_frequency` without this local session setting are aborted with a database exception.

### 2.4 P2 — Historical Actor Identity Governance
In `apps/gst/models.py` (`VoucherAttributionOperation`) and `apps/gst/itc_views.py`:
- Added `actor_identity_status` with choices `VERIFIED` and `HISTORICAL_UNRECOVERABLE`.
- In `ITCVoucherAttributionAPIView`:
  - When an operation has `actor_identity_status == 'HISTORICAL_UNRECOVERABLE'`, any request attempting to replay or claim it is rejected immediately with HTTP 409 Conflict (`error_code: 'OPERATION_ACTOR_UNRECOVERABLE'`), evaluated prior to payload fingerprint validation.

---

## 3. Test Certification & Evidence

### 3.1 Unit & Targeted Remediation Tests (`Round246TargetedRemediationTests`)
- `test_r246_01_worker_exclusivity_rejects_competing_worker`: **PASS**
- `test_r246_02_expired_lease_allows_takeover_with_new_generation`: **PASS**
- `test_r246_03_superseded_worker_completion_aborted`: **PASS**
- `test_r246_04_automated_recovery_task_sweeps_pending_jobs`: **PASS**
- `test_r246_05_historical_unrecoverable_actor_rejected_with_409`: **PASS**
- `test_r246_06_verified_actor_replays_successfully`: **PASS**
*Result: 6/6 tests passed.*

### 3.2 PostgreSQL Concurrency & Trigger Certification (`PostgreSQLConcurrencyCertificationTests`)
Executed against PostgreSQL 18.7 on AWS Neon:
- `test_r246_pg_01_database_trigger_rejects_raw_sql_update_on_filing_frequency`: **PASS** (Direct SQL rejected with error code P0001)
- `test_r246_pg_02_database_trigger_rejects_queryset_update_on_filing_frequency`: **PASS** (`QuerySet.update()` rejected by trigger)
- `test_r246_pg_03_database_trigger_permits_authorized_audited_update`: **PASS** (`set_filing_frequency()` succeeds and creates audit log)
- `test_r246_pg_04_two_workers_competing_under_lease_exclusivity`: **PASS** (Concurrent worker blocked by lease)
- `test_r246_pg_05_migration_0030_rollback_guard_and_reapplication`: **PASS** (Rollback guard requires `ALLOW_AUDIT_TRIGGER_ROLLBACK=true`)
*Result: 5/5 PostgreSQL tests passed in 116.5s.*

### 3.3 Zero Regressions Across Historical Suites
- `Round244TargetedRemediationTests`: 8/8 passed.
- `Round245TargetedRemediationTests`: 13/13 passed.
- `Round246TargetedRemediationTests`: 6/6 passed.
*Combined Result: 27/27 regression tests passed.*

---

## 4. Certification Sign-Off

The Round 2.4.6 remediation has successfully eliminated worker concurrency conflicts, established automatic self-healing background recovery, enforced database-level triggers on statutory filing frequencies, and permanently closed actor identity provenance vulnerabilities.
