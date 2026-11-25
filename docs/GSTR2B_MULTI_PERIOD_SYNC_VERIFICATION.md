# SriLekh GST ITC Shield — Round 2.4.8
## GSTR-2B Multi-Period Synchronization & Invariant Verification

**Target Endpoint:** `POST /api/v1/gst/reconciliation/gstr2b/sync/<company_id>/`  
**Target Commit:** `1ddb70f77639ef80eed576f4f62a8e64528048bb`  
**Database Verified:** PostgreSQL 18.7 on AWS Neon (`neondb_staging` / `test_neondb_staging`)  

---

### 1. End-to-End Execution Path Verification

The full execution path from HTTP request to database persistence was traced and verified:

```text
1. Client POST request
   ├── Payload: { from_period: "042026", to_period: "102026", registration_id: "<uuid>" }
   └── Header: HTTP_X_COMPANY_ID: "<company_uuid>"
       ▼
2. Request Validation (apps/gst/views.py: GSTR2BSyncView)
   ├── get_company_or_404(request.user, company_id)
   ├── Parse & validate from_period / to_period format via GSTPeriodService.parse_return_period()
   ├── Guard: from_period.start_date <= to_period.start_date (rejects reversed ranges with HTTP 400 INVALID_PERIOD_RANGE)
   └── Registration resolution:
       └── If registration_id provided: validates company ownership and ACTIVE status.
       └── If registration_id omitted: falls back to company's active primary GSTRegistration.
       ▼
3. Multi-Period Ingestion Dispatch (apps/gst/services/reconciliation_service.py: fetch_and_ingest_range)
   ├── GSTPeriodService.resolve_period_range("042026", "102026") -> 7 PeriodInfo objects
   ├── Formulation of range key:
   │   └── range_key = "042026-102026" (13 chars)
   │   └── display_label = "April 2026 – October 2026"
   ├── Insertion of GSTR2BSyncAttempt:
   │   └── GSTR2BSyncAttempt.objects.create(return_period="042026-102026", status="IN_PROGRESS", ...)
   │   └── [VERIFIED]: Column capacity is VARCHAR(32); 13-character string persists without truncation.
   ├── Sequential Period Fetch Loop:
   │   ├── Acquires GSTR2BIngestionLock(return_period="042026") [VARCHAR(10)]
   │   ├── Invokes sandbox/portal fetch for "042026"
   │   ├── Ingests GSTR-2B JSON payload into GSTR2BImport & GSTR2BRecord
   │   └── Releases GSTR2BIngestionLock in finally block.
   ├── Period-Isolated Reconciliation:
   │   └── ITCReconciliationService.reconcile_period(periods=["042026", ..., "102026"])
   └── Terminal Status Update:
       └── sync_attempt.status = "SUCCESS" | "PARTIAL_SUCCESS" | "FAILED"
       └── sync_attempt.save(update_fields=[...])
```

---

### 2. Period Semantics & Ingestion Lock Isolation

A critical architectural invariant verified in Round 2.4.8 is the separation of **Range Identifiers** from **Individual Return Periods**:

1. **`GSTR2BSyncAttempt.return_period` (`VARCHAR(32)`)**:
   - Stores user-facing or job-level scope identifiers (e.g., `"042026-102026"`, `"042025-032027"`).
   - Tracks the lifecycle of the multi-month sync batch.
2. **`GSTR2BIngestionLock.return_period` (`VARCHAR(10)`)**:
   - Strictly preserves 6-character monthly periods (`"042026"`).
   - Ensures concurrency serialization operates at the granular calendar month level. Two simultaneous sync jobs for overlapping ranges serialize correctly on the common months without lock collisions.
3. **`GSTR2BImport.return_period` (`VARCHAR(10)`)**:
   - Associates ingested portal records with their authoritative statutory statement period.

---

### 3. Resilience, Retry & Idempotency Guarantees

#### 3.1 Try/Except Failure State Update
The sync engine wraps range execution in explicit exception guards:
```python
try:
    # multi-period fetch & reconciliation loop
except Exception as exc:
    sync_attempt.status = 'FAILED'
    sync_attempt.error_message = f"Synchronization aborted due to unexpected error: {str(exc)}"
    sync_attempt.save(update_fields=['status', 'error_message'])
    raise
```
**Verification Evidence:** Tested by `test_12_unexpected_reconciliation_error_marks_attempt_failed`. When a mock `RuntimeError` was injected during reconciliation, `sync_attempt.status` transitioned to `'FAILED'` with the exact error message recorded. No orphaned `'IN_PROGRESS'` attempts remain.

#### 3.2 Idempotent Ingestion & Duplicate Protection
- Re-running a sync for the same period updates existing `GSTR2BImport` records rather than duplicating invoices.
- `records_created`, `records_updated`, and `records_unchanged` counters accurately reflect idempotency.

---

### 4. Accounting Invariants & Tenant Isolation

#### 4.1 Double-Entry & Voucher Preservation
- `test_13_accounting_voucher_and_ledger_invariants_preserved` certified that creating `GSTR2BSyncAttempt` and resolving period ranges causes **zero modifications** to `Voucher` totals, statuses, dates, or ledger balances.
- Equilibrium `Total Debits == Total Credits` is strictly maintained.

#### 4.2 QRMP Interim Month Classification
- In `test_11_qrmp_interim_months_handled_non_fatally`, verified that under verified QRMP, interim months (April M1 and May M2) returning `FORM_NOT_APPLICABLE` are bucketed into `not_applicable_periods` rather than `failed_periods`.
- The overall sync completes as `SUCCESS` with explicit explanatory messaging.
