# SriLekh GST ITC Shield — Round 2.4.7
## Production Release Readiness Certification

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Active Remediation Branch:** `remediation/round-2.4.7-multi-period-gstr2b-sync`  
**Previous Baseline:** `audit/round-2.4.6-gst-integration-reliability` (`6df7dd3`)  
**Target Release:** SriLekh GST ITC Shield v2.4.7  
**Sign-off Date:** 2026-11-25  

---

### 1. Release Objective & Resolution Verification

| Defect / Requirement | Status | Verification Evidence |
| :--- | :---: | :--- |
| **P0: PostgreSQL String Truncation on Multi-Period Sync** | **RESOLVED** | Migration `0031` expanded `GSTR2BSyncAttempt.return_period` to `VARCHAR(32)`. Verified on PostgreSQL `test_neondb_staging`. |
| **Ingestion Lock Isolation** | **VERIFIED** | `GSTR2BIngestionLock.return_period` kept strictly at `VARCHAR(10)`. Confirmed atomic per-month serialization. |
| **Migration Reversibility** | **VERIFIED** | Rollback to `0030` and re-application to `0031` tested on PostgreSQL staging with `$env:ALLOW_AUDIT_TRIGGER_ROLLBACK="true"`. |
| **Period Selector UX Overhaul** | **RESOLVED** | Built `MonthPickerInput.tsx` supporting keyboard typing, month/year grid popup, and range validation. |
| **Structured API Contract** | **RESOLVED** | `fetch_and_ingest_range` returns `from_period`, `to_period`, `range_identifier`, `display_label`, `periods_requested`, `periods_synced`. |
| **Graceful Failure Handling** | **RESOLVED** | Wrapped in try/except; `sync_attempt.status = 'FAILED'` with exact error message upon downstream reconciliation exceptions. |
| **QRMP Interim Month Handling** | **VERIFIED** | Under verified QRMP, interim months (M1/M2) are categorized as `not_applicable_periods` without triggering job failure. |
| **Production Tenant Protection** | **CERTIFIED** | Protected tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) had 0 modifications. |
| **Double-Entry Equilibrium** | **CERTIFIED** | Total debits equal total credits; voucher amounts and ledger balances strictly preserved. |

---

### 2. Code Changes Summary

- `apps/gst/models.py`:
  - `GSTR2BSyncAttempt.return_period`: Altered from `CharField(max_length=10)` to `CharField(max_length=32)`.
  - `GSTR2BIngestionLock.return_period`: Retained at `CharField(max_length=10)`.
- `apps/gst/migrations/0031_alter_gstr2bsyncattempt_return_period.py`:
  - Generated and applied to PostgreSQL.
- `apps/gst/services/reconciliation_service.py`:
  - Structured contract fields exposed (`from_period`, `to_period`, `range_identifier`, `display_label`).
  - Robust exception handling for `sync_attempt` failure state.
- `apps/gst/views.py`:
  - Automatic fallback to active primary GST registration when `registration_id` is omitted.
- `frontend/src/components/ui/MonthPickerInput.tsx`:
  - Created accessible month picker component with direct typing, calendar picker, and `MMYYYY` normalization.
- `frontend/src/app/gst/itc-shield/page.tsx`:
  - Integrated `MonthPickerInput` in GSTR-2B sync modal.
  - Added live range indicator and inverted range guard.
- `apps/gst/tests_round2_4_7_gstr2b_sync.py`:
  - 14 targeted regression tests certified on PostgreSQL.
- `frontend/src/components/ui/month-picker-input.test.ts`:
  - Unit tests for month picker input.

---

### 3. Deployment Procedure for Production

When deploying this remediation to staging or production:

1. **Deploy Backend Migration**:
   ```bash
   python manage.py migrate gst 0031
   ```
   *Note: This `ALTER TABLE` statement on `gst_gstr2bsyncattempt` expands a `VARCHAR` column length from 10 to 32, which is an instant metadata change in PostgreSQL without table lock or rewrite.*

2. **Deploy Frontend Build**:
   ```bash
   cd frontend && npm run build
   ```

3. **Post-Deployment Smoke Test**:
   - Navigate to **GST ITC Shield** -> **Sync GSTR-2B**.
   - Select **FY 2026–27 (April to October 2026)**.
   - Confirm that the sync executes smoothly without string truncation errors.

---

### 4. Release Sign-Off
- **Architectural & Security Sign-Off**: Certified.
- **Database Schema Sign-Off**: Certified.
- **Accounting & Tenant Protection Sign-Off**: 100% Zero-Touch Certified.
