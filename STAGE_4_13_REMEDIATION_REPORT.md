# SRI LEKH — STAGE 4.13 STABILIZATION, DEFECT REMEDIATION & PRODUCTION READINESS REPORT

**Date:** 2026-11-12  
**Branch:** `fix/stage4-12-day6-remediation` (`2945375c2bec67a74ec9c14b075ef061b8082016`, pushed to `origin/fix/stage4-12-day6-remediation`)  
**Baseline Release Candidate (Untouched):** `release/stage4-final-rc-integration` (`4888e451`)  
**Target Branch (Untouched):** `main`  
**Staging Database:** `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`, fingerprint `6f4741bdaaf4`, `is_isolated=True`, `prod_tenant_count=0`)  
**Protected Production Tenant Check:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) verified absent (`count=0`) and untouched across all runs.

---

## Executive Verdict

**VERDICT: `CONDITIONAL PASS` — Gated on Live Render Deployment of `2945375`, `ENVIRONMENT=staging`, and Dedicated Worker Process**

All application-level, database-level, accounting, disaster-recovery, outbox, and query-performance defects identified in Stage 4.12 have been root-caused, fixed, regression-tested (`77/77` PostgreSQL backend tests, `12/12` frontend tests, `tsc --noEmit` exit `0`), and verified on `neondb_staging` with zero ledger drift (`0/113`), zero `PENDING` outbox events (`0` remaining after idempotent classification and cleanup of all `170` historical rows), and a full disposable PostgreSQL Disaster Recovery drill (`28,815` records restored cleanly, `0` errors, RTO `228.441s`).

Production promotion and full live `PASS` remain **gated** because:
1. Live Render staging (`https://vouch-u3u7.onrender.com`) currently still runs baseline commit `4888e451` rather than `fix/stage4-12-day6-remediation` (`2945375`) and omits `ENVIRONMENT=staging` in its Render dashboard environment variables (no `RENDER_API_KEY` or Render dashboard access was available locally).
2. Render runs Free-tier idle spin-down (`44.1s` cold wake on `/api/v1/health/environment/`), which exceeds 25s health-probe timeouts unless cold-wake tolerance or an always-on plan is configured, and `Procfile` defines only `web:` with no `worker:`/`beat:` dyno active on Render.

---

## Summary of 7 Problem Areas Investigated & Remediated

### Problem 1 — Render Staging Availability, Cold-Start Timeouts, `ENVIRONMENT` & CORS
- **Root Causes Diagnosed:**
  1. Render Free tier sleeps when idle and took **`44,076.5 ms`** (`44.1s`) to wake during cold probe (`task-50020`), causing Stage 4.12's 25s timeout failure. Once warm, `/api/health/` responds in **`467.5 ms`** (HTTP 200).
  2. Live Render still serves commit `4888e451` (`origin/fix/stage4-final-hardening`) instead of `fix/stage4-12-day6-remediation` (`2945375`).
  3. Live `/api/v1/health/environment/` and `/api/health/` report `"environment": "production"` because Render's env omits `ENVIRONMENT=staging`, and `root_health_view` in `config/urls.py` previously hardcoded `"environment": "production"`.
- **Remediations Implemented:**
  - Updated `root_health_view` in [config/urls.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/urls.py) to read `getattr(settings, "ENVIRONMENT", "production" if not settings.DEBUG else "development")` instead of hardcoding `"production"`.
  - Hardened [scripts/test_live_render_staging.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/scripts/test_live_render_staging.py) with cold-wake retry handling (`--timeout 90`), latency telemetry, `--expected-commit` verification, fingerprint logging, and `OPTIONS` CORS preflight verification for `https://vouch-pi-one.vercel.app`.
- **Live Verification Evidence:**
  - Vercel frontend `https://vouch-pi-one.vercel.app`: HTTP `200`, strict CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security`.
  - Render `OPTIONS /api/v1/accounting/vouchers/`: HTTP `200` with `Access-Control-Allow-Origin: https://vouch-pi-one.vercel.app`.
  - Render login, Precision Agro Balance Sheet (`Rs 1845954.26 == Rs 1845954.26`, diff `Rs 0.00`), and Garodia cross-tenant IDOR (`HTTP 403`) passed cleanly.
- **Remaining Operational Action:** Switch Render service `vouch-u3u7` to branch `fix/stage4-12-day6-remediation`, set `ENVIRONMENT=staging`, redeploy, and re-run `python scripts/test_live_render_staging.py --base-url https://vouch-u3u7.onrender.com --expected-commit 2945375`.

---

### Problem 2 — Disaster Recovery & `AuditLog` Backup/Restore Completeness
- **Root Causes Diagnosed (`apps/common/services/backup_service.py`):**
  1. JSON fallback hardcoded exclusions for `auditlog`, `syncevent`, and `permission` (`_EXCLUDED_MODELS`).
  2. `_log_audit_event` passed invalid kwarg `details=...` rather than `AuditLog`'s actual fields (`action='RESOLVE'`, `model_name='DatabaseBackup'`, `changes=...`).
  3. `AuditLog.save()` intentionally recomputes hash chains and blocks updates to PK-existing rows; restoring via `.save()` would rewrite hashes or fail, while `Voucher.reversal_voucher` <-> `REV-*` mutual FKs require deferred constraints inside `transaction.atomic()`.
  4. PostgreSQL `BigAutoField` sequences (e.g., `AuditLog`, `SyncEvent`, `ProtocolTransaction`, `ProtocolOperation`) needed explicit `sequence_reset_sql` after PK-preserving restores.
- **Remediations Implemented ([backup_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/common/services/backup_service.py)):**
  - Added `--format=custom` + `PGSSLMODE` support for native `pg_dump` / `PGDMP` `pg_restore`.
  - Removed exclusions for `auditlog`, `syncevent`, and `permission`; expanded `MODEL_DEPENDENCY_ORDER` and deterministic ordering (`('sequence', 'created_at', pk_name)` for `AuditLog`, `pk_name` for others), plus manifest `model_counts`.
  - Wrapped JSON restore in `transaction.atomic()` with `SET CONSTRAINTS ALL DEFERRED`, per-item savepoints, hash-preserving `bulk_create` + idempotent re-restore check via `_save_item_preserving_immutability`, and PostgreSQL `sequence_reset_sql`.
- **Verification:** Full disposable PostgreSQL DR drill (`neondb_staging_dr_restore_s413`) completed in **RTO `228.441s`** (`0` errors, `28,815` records, `1221/1221` snapshot `AuditLog` PKs, `15,198/15,198` `SyncEvent`s, exact financial & sequence parity), and disposable DB was dropped afterward. See [STAGE_4_13_DR_CERTIFICATION.md](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_4_13_DR_CERTIFICATION.md).

---

### Problem 3 — MSME Alpha Belts Ledger Balance Drift & Full Cohort Audit
- **Root Causes Diagnosed:**
  1. **Reversed-Voucher Filter Divergence:** `VoucherService.create_reversal_voucher()` keeps entries on `status='REVERSED'` vouchers and adds counter entries on `REV-*` (`status='POSTED'`). Reports and rebalancing must aggregate `EffectiveVoucherService.ACCOUNTING_STATUSES` (`('POSTED', 'REVERSED', 'CORRECTED')`), whereas `ReportService.generate_trial_balance`, `PeriodBalanceService`, `PeriodLedgerStatementAPIView`, and `SalesInvoiceService.rebalance` filtered `voucher__status='POSTED'` only — causing systematic reversal drift (and `auto_reconcile=True` overwrote Alpha's cached balances with wrong `POSTED`-only totals!).
  2. **Stale Credit-Note Cache (`Garodia` & `Precision Agro`):** Historical Stage 4.10/4.11 scripts updated `CN/26-27/0003` status via `.save()` bypassing `post_voucher()`, leaving 8 ledgers' `current_balance` stale pre-credit-note.
- **Remediations & Controlled Reconciliation:**
  - Updated [report_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/report_service.py), [period_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/period_service.py), [period_views.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/period_views.py), and [sales_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/sales_service.py) to use `EffectiveVoucherService.ACCOUNTING_STATUSES`.
  - Reconciled all **12 drifted ledgers** (`4` Alpha Belts, `4` Garodia, `4` Precision Agro) inside `transaction.atomic()` with `'RECONCILE'` `AuditLog` entries; `Staging Beta Engineering Supplies Ltd`'s 2 previously reported ledgers (`ICICI Bank Staging`, `Interstate Dealer Gujarat`) were already exact (`-12,000.00` and `27,661.00`).
  - Post-fix cohort verification shows **`0` discrepancies** across all 113 ledgers and all 5 tenants (`per_company_hash_breaks: 0` across all `1,222` `AuditLog` rows). See [STAGE_4_13_LEDGER_RECONCILIATION.md](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_4_13_LEDGER_RECONCILIATION.md).

---

### Problem 4 — Transactional Outbox (`170` Historical `PENDING` Events)
- **Root Causes Diagnosed:** All `170 / 170` `PENDING` events belonged to `Precision Agro Tools Pvt Ltd` (`INVOICE_POSTED`, `retry_count=0`, `claimed_at=None`, created `2026-11-06` on synthetic `POSTED` invoices with `recipient_resolved=None`), left unprocessed due to absent live Celery worker dyno in Render `Procfile` and non-deterministic `[:50]` slicing in `tasks.py`. All `9` `DEAD_LETTER` events were pre-existing test artifacts (`2` missing referenced vouchers, `7` `"Simulated Fatal Delivery Error"`).
- **Remediations Implemented:**
  - Updated [tasks.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/tasks.py) to fetch backlog deterministically with `.order_by('created_at', 'id')[:100]`.
  - Added malformed non-dict payload `DEAD_LETTER` protection, read-only `OutboxService.classify_pending_events`, and idempotent `OutboxService.recover_pending_outbox_events` in [outbox_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/outbox_service.py).
  - Recovered all `170` events safely on `neondb_staging`: `170` transitioned to `SKIPPED`, **`0` remaining `PENDING`**, `EmailDeliveryLog` `SENT` count unchanged at `621` (`0` duplicate or spurious emails). See [STAGE_4_13_OUTBOX_RECOVERY.md](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_4_13_OUTBOX_RECOVERY.md).

---

### Problem 5 — Receivables Aging Query Optimization
- **Root Cause Diagnosed ([allocation_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/allocation_service.py)):** Over Neon WAN (`~76ms` RTT), `get_aging_analysis` previously fetched all full ORM `Voucher` + `Ledger` + `LedgerGroup` rows plus executed a second large UUID `IN (...)` query on `PaymentAllocation` (~700 KB payload, ~4,867ms under load / ~465–941ms isolated).
- **Remediation Implemented:** Refactored `get_aging_analysis` to a **single-query `.values(...)` projection + `Coalesce(Sum('allocations_received__allocated_amount', ...))` annotation**, reducing SQL queries from `2` to **`1`**.
- **Verified Performance (5-run benchmark across Neon WAN):**
  - `small_beta` (Beta Engineering): `1` query | p50 `77.93ms` | p95 `81.28ms` | p99 `81.37ms`
  - `medium_garodia` (Garodia Bearing): `1` query | p50 `79.72ms` | p95 `81.06ms` | p99 `81.28ms`
  - `large_alpha` (MSME Alpha Belts): `1` query | p50 `83.81ms` | p95 `89.05ms` | p99 `89.81ms`
  - `large_agro` (Precision Agro Tools): `1` query | p50 `83.06ms` | p95 `93.31ms` | p99 `94.95ms`
  - **Numeric Parity:** 100% exact party, bucket, and total outstanding parity across all 5 companies (`CUSTOMER` and `SUPPLIER`).

---

### Problems 6 & 7 — Regression Suite, Security Verification & 5-Tenant Pilot Census
- **Backend PostgreSQL Regression Suite (`test_neondb_staging`):** **77 / 77 `OK`** (`0` failures, `0` skipped, `1147.171s`) including `apps.accounting.tests_stage4_13_stabilization` (4 new tests), Stage 4.12 remediation/OCC tests, DR tests, deduplication, financial reports, master stabilization, and opening balance tests.
- **Django Schema Check:** `python manage.py makemigrations --check --dry-run` -> `No changes detected`.
- **Frontend Verification (`cd frontend`):** `npm test` -> `12/12 pass` (`0` fail, `0` skipped across `3` suites in `943.05ms`); `npx tsc --noEmit` -> exit `0`.
- **Global `neondb_staging` Invariants & Security Check:**
  - `1,246` vouchers (`1,131` `POSTED`, `104` `DRAFT`, `11` `REVERSED`), `0` zero-entry posted vouchers, `0` unbalanced posted vouchers, `0` orphan `LedgerEntry` rows, `113` ledgers (`0` drift), `1,222` `AuditLog` entries (`0` per-company hash breaks), `1,131` `ProtocolOperation` rows, `0` invalid/over-allocated FIFO invoices.
  - Non-destructive WSGI security checks: unauthenticated `401`, cross-tenant Aging/TB IDOR `403`, VIEWER write mutation `403`, parameterized SQLi probe `200`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`.

---

## Modified / Added Repository Files (Commit `2945375`)

1. [config/urls.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/urls.py)
2. [scripts/test_live_render_staging.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/scripts/test_live_render_staging.py)
3. [apps/common/services/backup_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/common/services/backup_service.py)
4. [apps/accounting/services/report_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/report_service.py)
5. [apps/accounting/services/period_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/period_service.py)
6. [apps/accounting/period_views.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/period_views.py)
7. [apps/accounting/services/sales_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/sales_service.py)
8. [apps/accounting/services/allocation_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/allocation_service.py)
9. [apps/notifications/tasks.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/tasks.py)
10. [apps/notifications/outbox_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/outbox_service.py)
11. [apps/accounting/tests_stage4_13_stabilization.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/tests_stage4_13_stabilization.py)
