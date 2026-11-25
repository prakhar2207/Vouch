# SriLekh GST ITC Shield — Round 2.4.7
## Root Cause Analysis and Remediation Report: Multi-Period GSTR-2B Sync

**Target Branch:** `remediation/round-2.4.7-multi-period-gstr2b-sync`  
**Previous Baseline:** `audit/round-2.4.6-gst-integration-reliability` (`6df7dd3`)  
**Scope:** GSTR-2B Synchronization Engine & Database Column Capacity  
**Priority:** P0 Production Defect Remediation  
**Status:** Certified & Resolved  

---

### 1. Executive Summary & Defect Statement

In production environments running on PostgreSQL, initiating a multi-period GSTR-2B sync (such as the standard financial-year range **April 2026 to October 2026**) failed immediately with a database string truncation error:

```text
psycopg2.errors.StringDataRightTruncation:
value too long for type character varying(10)
```

The user-facing consequence was an immediate API `500 Internal Server Error` or a red error alert displayed in the GSTR-2B sync modal, preventing taxpayers from pulling and reconciling multiple months of auto-drafted ITC statements in one click.

---

### 2. Execution Path & Root Cause Analysis

#### 2.1 Traceback Execution Path
The execution path triggering this defect was confirmed as follows:
```text
POST /api/v1/gst/reconciliation/gstr2b/sync/<company_id>/
    apps/gst/views.py: GSTR2BSyncView.post()
        apps/gst/services/reconciliation_service.py: GSTReconciliationService.fetch_and_ingest_range()
            apps/gst/models.py: GSTR2BSyncAttempt.objects.create(return_period=range_key, ...)
```

#### 2.2 Range Key Formulation
In `apps/gst/services/reconciliation_service.py`, multi-period synchronization combines the normalized start and end period strings (`MMYYYY` format) into a compound range identifier:
```python
range_key = f"{period_infos[0].normalized_period}-{period_infos[-1].normalized_period}"
```
For April 2026 to October 2026:
- `period_infos[0].normalized_period`: `"042026"` (6 characters)
- `period_infos[-1].normalized_period`: `"102026"` (6 characters)
- Combined `range_key`: `"042026-102026"` (total length: **13 characters**).

#### 2.3 The Column Definition Discrepancy
In `apps/gst/models.py`, `GSTR2BSyncAttempt` previously defined:
```python
return_period = models.CharField(max_length=10, db_index=True)
```
While SQLite silently accepts strings exceeding declared `CharField` limits in development/testing, PostgreSQL strictly enforces `VARCHAR(10)`. Attempting to insert a 13-character string directly triggers `StringDataRightTruncation`, causing the database transaction to abort.

---

### 3. Remediation Architecture

#### 3.1 Model Schema Expansion
`GSTR2BSyncAttempt.return_period` was expanded from `max_length=10` to `max_length=32` to accommodate:
- Standard 6-character monthly periods (`"042026"`)
- Standard 13-character multi-period ranges (`"042026-102026"`)
- Cross-financial-year and extended multi-year ranges (`"042024-032027"`, 13–15 characters) with ample headroom.

#### 3.2 Ingestion Lock Isolation Invariant
Critically, `GSTR2BIngestionLock.return_period` was **deliberately preserved at `max_length=10`**. Ingestion locks serialize concurrent portal calls per individual calendar month (`MMYYYY`), ensuring that monthly locks and uniqueness constraints (`company`, `gst_registration`, `return_period`) remain atomic and cannot be corrupted by composite range strings.

#### 3.3 Database Migration: `0031_alter_gstr2bsyncattempt_return_period`
Django migration `apps/gst/migrations/0031_alter_gstr2bsyncattempt_return_period.py` was created:
```python
operations = [
    migrations.AlterField(
        model_name='gstr2bsyncattempt',
        name='return_period',
        field=models.CharField(
            db_index=True,
            help_text='Return period (MMYYYY, e.g. 102026) or period range (e.g. 042026-102026)',
            max_length=32,
        ),
    ),
]
```

#### 3.4 Migration Reversibility Certification
Reversibility was rigorously certified against the target PostgreSQL staging database (`neondb_staging`):
1. **Rollback to migration 0030:**
   ```powershell
   $env:ALLOW_AUDIT_TRIGGER_ROLLBACK="true" ; python manage.py migrate gst 0030
   ```
   *Result:* Reverted cleanly. Inspected PostgreSQL system catalog: `GSTR2BSyncAttempt.return_period` reverted to `character varying(10)`.
2. **Re-application of migration 0031:**
   ```powershell
   python manage.py migrate gst 0031
   ```
   *Result:* Applied cleanly. Inspected PostgreSQL system catalog: `GSTR2BSyncAttempt.return_period` altered to `character varying(32)`.

---

### 4. Service and API Layer Hardening

#### 4.1 Structured Contract Keys
`GSTReconciliationService.fetch_and_ingest_range()` and single-month ingestion now reliably return explicit structured contract keys:
- `from_period`: Normalized starting month (`"042026"`)
- `to_period`: Normalized ending month (`"102026"`)
- `range_identifier`: Consistent compound key (`"042026-102026"`)
- `display_label`: Human-readable format (`"April 2026 – October 2026"`)
- `periods_requested`, `periods_synced`, `periods_not_applicable`, `periods_failed`.

#### 4.2 Graceful Exception Handling
The execution block in `fetch_and_ingest_range` is wrapped in comprehensive exception guards:
- Any unexpected failure during reconciliation immediately updates `sync_attempt.status = 'FAILED'` and records the exact exception message.
- Ghost/orphaned records with status `'IN_PROGRESS'` are prevented.

#### 4.3 Default Active Registration Resolution
In `apps/gst/views.py`, if a client does not explicitly submit `registration_id`, the endpoint automatically resolves the company's primary active GST registration:
```python
if reg_id:
    registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()
else:
    registration = (
        GSTRegistration.objects.filter(company=company, is_primary=True, status='ACTIVE').first()
        or GSTRegistration.objects.filter(company=company, status='ACTIVE').first()
    )
```
This ensures QRMP filing-frequency verification rules and statement attributions evaluate against the verified primary GSTIN without failing closed.

---

### 5. Strict Accounting and Tenant Isolation Verification

1. **Mandatory Test Isolation**:
   - ALL tests executed strictly against sandbox company `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
   - Protected client tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) had **ZERO** modifications, sync attempts, imports, or vouchers touched.
2. **Double-Entry Equilibrium**:
   - Vouchers, ledger postings, and balance invariants remained completely untouched throughout sync attempt creation and range resolution.
