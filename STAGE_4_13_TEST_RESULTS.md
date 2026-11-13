# SRI LEKH — STAGE 4.13 TEST RESULTS

**Execution Date:** 2026-11-12  
**Branch / Commit Tested:** `fix/stage4-12-day6-remediation` (`2945375c2bec67a74ec9c14b075ef061b8082016`)  
**Backend Test Database:** `test_neondb_staging` on `ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech` (PostgreSQL, `config.settings_test_pg`)  
**Staging Cohort Verification DB:** `neondb_staging` (fingerprint `6f4741bdaaf4`)

---

## 1. PostgreSQL Backend Regression Suite

Command run (`ENVIRONMENT=staging`, `DATABASE_URL` & `TESTING_DATABASE_URL` pointing to Neon staging cluster):
```powershell
python manage.py test `
  apps.accounting.tests_stage4_13_stabilization `
  apps.accounting.tests_stage4_12_remediation `
  apps.common.tests_disaster_recovery `
  apps.common.tests_code_review_findings `
  apps.accounting.tests_voucher_occ `
  apps.accounting.tests_deduplication `
  apps.accounting.tests_financial_reports `
  apps.accounting.tests_master_stabilization `
  apps.ledgers.tests_opening_balance `
  --settings=config.settings_test_pg --keepdb --verbosity=2
```

- **Total Run:** **77 tests in 1147.171s**
- **Result:** **`OK`** (`77 passed`, `0 failed`, `0 errors`, `0 skipped`)

| Test Module | Tests Passed | Failures / Skips | Coverage Scope |
|---|---|---|---|
| `apps.accounting.tests_stage4_13_stabilization` | 4 | 0 / 0 | DR `AuditLog` + `SyncEvent` hash preservation & idempotent restore; reversed-invoice report + cache parity (TB/Period TB/Ledger/P&L/BS); outbox classification & duplicate-free recovery; single-query aging accuracy |
| `apps.accounting.tests_stage4_12_remediation` | 8 | 0 / 0 | DEF-01 duplicate payment protection & override RBAC; DEF-02 metadata PATCH OCC & all-voucher-type parity; concurrent OCC `200`/`409` race |
| `apps.common.tests_disaster_recovery` | 1 | 0 / 0 | Encrypted backup / restore DR sanity |
| `apps.common.tests_code_review_findings` | 12 | 0 / 0 | Security, concurrency, and accounting invariants |
| `apps.accounting.tests_voucher_occ` | 13 | 0 / 0 | ETag / `version` OCC serialization & concurrent non-blocking updates |
| `apps.accounting.tests_deduplication` | 11 | 0 / 0 | Client/server idempotency & deduplication guards |
| `apps.accounting.tests_financial_reports` | 6 | 0 / 0 | Trial Balance, P&L, Balance Sheet equilibrium & tax reports |
| `apps.accounting.tests_master_stabilization` | 10 | 0 / 0 | Posting, reversal, GST, and period lock invariants |
| `apps.ledgers.tests_opening_balance` | 12 | 0 / 0 | Opening balance carry-forward, FIFO allocation, credit limit, balance rebuild |
| **Total** | **77** | **0 / 0** | **PostgreSQL (`test_neondb_staging`)** |

---

## 2. Django Migration Schema Check

- Command: `python manage.py makemigrations --check --dry-run`
- Output: `No changes detected` (exit code `0`).

---

## 3. Frontend Test & TypeScript Verification

Commands run in `frontend/`:
- `npm test` (`node --import ./test-loader.mjs --test "src/**/*.test.ts"`):
  - **Suites:** `3` | **Tests:** `12` | **Pass:** `12` | **Fail:** `0` | **Skipped:** `0` | **Duration:** `943.0518ms` (exit code `0`)
  - Covered: Offline sales voucher queue + reconnect sync with `X-Idempotency-Key` & OCC version; `IN_FLIGHT` crash recovery + transient `503` backoff retry; multi-tenant IndexedDB isolation & push block on company switch; cross-user logout cache purge & push block; incremental pull OCC preservation; RBAC role capability matrix & auth permission utilities.
- `npx tsc --noEmit`:
  - **Result:** Exit code `0` (zero TypeScript errors).

---

## 4. Aging Query Performance Benchmark (5-Run Across `neondb_staging`)

Measured with `CaptureQueriesContext(connection)` over Neon WAN (`CUSTOMER` aging, `PaymentAllocationService.get_aging_analysis`):

| Tenant Tier | Company Name | Query Count | Samples (ms) | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|---|---|---|
| Small (46 vouchers) | `Staging Beta Engineering Supplies Ltd` | **1** | `76.88, 80.86, 81.39, 77.47, 77.93` | **77.93** | **81.28** | **81.37** |
| Medium (63 vouchers) | `Garodia Bearing & Power Transmission` | **1** | `79.15, 81.34, 79.94, 77.06, 79.72` | **79.72** | **81.06** | **81.28** |
| Large (543 vouchers) | `Staging MSME Alpha Belts Pvt Ltd` | **1** | `80.08, 85.25, 80.97, 90.00, 83.81` | **83.81** | **89.05** | **89.81** |
| Large (534 vouchers) | `Precision Agro Tools Pvt Ltd` | **1** | `81.99, 95.36, 83.06, 85.09, 82.65` | **83.06** | **93.31** | **94.95** |

*(Pre-optimization baseline on `neondb_staging`: `2` queries; `1091.19 ms` on Alpha Customer aging in `p5_out` and `941.42 ms` on Precision Agro -> ~`10x` improvement from Stage 4.12 `4,867ms` reported API latency down to `<95ms` p99).*

---

## 5. Non-Destructive WSGI Security & Statement Spot Verification (`neondb_staging`)

- **Period & Ledger Statements (`Alpha Belts` — `Customer Saksham Staging`):**
  - `GET /api/v1/accounting/period-statement/f1035785-402d-47fb-a4bd-b4edd804fde2/?date_from=2026-04-01&date_to=2027-03-31` -> `HTTP 200`, `closing_balance: 588658.26 DR` (`period_debit: 771180.00`, `period_credit: 182521.74`)
  - `GET /api/v1/accounting/reports/ledger-statement/75a4b5e7-d8af-4cca-905e-31817ba829ca/f1035785-402d-47fb-a4bd-b4edd804fde2/` -> `HTTP 200`, `closing_balance: 588658.26`
- **Period & Ledger Statements (`Beta Engineering` — `ICICI Bank Staging`):**
  - `GET /api/v1/accounting/period-statement/531f5486-2773-4721-973d-d87b9adc9d2e/?date_from=2026-04-01&date_to=2027-03-31` -> `HTTP 200`, `closing_balance: 12000.00 CR` (`period_debit: 444.00`, `period_credit: 12444.00`)
  - `GET /api/v1/accounting/reports/ledger-statement/434af258-8d98-4505-9d1b-65eb03c97cc7/531f5486-2773-4721-973d-d87b9adc9d2e/` -> `HTTP 200`, `closing_balance: 12000.00`
- **FIFO Allocation Sanity (`neondb_staging`):** `negative_or_zero_allocations: 0`, `over_allocated_invoices: []`.
- **RBAC / Tenant Isolation / Headers (`APIClient` against `neondb_staging`):**
  - Unauthenticated Aging GET -> `HTTP 401`
  - Cross-tenant Aging IDOR (Precision Agro -> Garodia) -> `HTTP 403`
  - Cross-tenant Trial Balance IDOR -> `HTTP 403`
  - `VIEWER` role Sales Invoice POST -> `HTTP 403`
  - Parameterized SQLi search probe (`' OR 1=1--`) -> `HTTP 200` (escaped safely)
  - Response security headers: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`

---

## 6. Live Hosting Probes (Render & Vercel)

- **Render (`https://vouch-u3u7.onrender.com`) — `scripts/test_live_render_staging.py`:**
  - `/api/v1/health/environment/`: `HTTP 200` in `44,076.5 ms` (Free-tier cold wake); reports `commit: "4888e451"`, `environment: "production"` (Render config gap!), `database.sanitized_target: "neondb_staging"`, `is_isolated: true`, `identity_fingerprint: "6f4741bdaaf4"`, `migrations.unapplied_count: 0`.
  - `/api/health/`: `HTTP 200` in `467.5 ms` warm.
  - `OPTIONS /api/v1/accounting/vouchers/`: `HTTP 200`, `Access-Control-Allow-Origin: https://vouch-pi-one.vercel.app`.
  - `POST /api/v1/auth/login/` (`owner_msme-plt-01@staging.srilekh.internal`): `HTTP 200`.
  - Precision Agro Balance Sheet: `HTTP 200` (`Assets Rs 1845954.26 == Liab Rs 1845954.26`, `Diff: Rs 0.00`).
  - Garodia Cross-Tenant Balance Sheet IDOR: `HTTP 403 Forbidden`.
- **Vercel (`https://vouch-pi-one.vercel.app`):**
  - `GET /`: `HTTP 200`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`, strict `Content-Security-Policy` with `frame-ancestors 'none'` and `connect-src` allowing `https://*.onrender.com`.
