# SRI LEKH — STAGE 4.15 TEST RESULTS

**Environment:** PostgreSQL `test_neondb_staging`, Live Render Staging (`https://vouch-u3u7.onrender.com`), Read-Only `neondb`, & Local Node/Next.js  
**Commit SHA Verified:** `c15a64fb2793a8d1abc762997a1202d73b4b92ae` (`fix/stage4-12-day6-remediation`)  
**Staging Database Fingerprint:** `6f4741bdaaf4` (`neondb_staging`, `Maa Annapurna Belting Store` absent)  
**Execution Timestamps:** `2026-11-12 14:15–15:10 IST`

---

## 1. Full PostgreSQL Backend Regression Suite (`test_neondb_staging`, `task-50430`)

**Command:**
```powershell
python manage.py test `
  apps.notifications.tests_stage4_15_auth `
  apps.notifications.tests `
  apps.inventory.tests_stage4_15_inventory `
  apps.inventory.tests `
  apps.accounting.tests_sales_stock_audit `
  apps.accounting.tests_stage4_14_certification `
  apps.accounting.tests_stage4_13_stabilization `
  apps.accounting.tests_stage4_12_remediation `
  apps.accounting.tests_staging_isolation `
  apps.common.tests_disaster_recovery `
  apps.common.tests_code_review_findings `
  apps.accounting.tests_voucher_occ `
  apps.accounting.tests_deduplication `
  apps.accounting.tests_financial_reports `
  apps.accounting.tests_master_stabilization `
  apps.ledgers.tests_opening_balance `
  --settings=config.settings_test_pg --keepdb --verbosity=2
```

- **Expected Result:** All tests pass with `0` failures, `0` errors, `0` skipped tests.
- **Actual Result:** **`Ran 126 tests in 1585.417s -> OK`** (`126 passed`, `0 failed`, `0 errors`, `0 skipped`).

| Test Module | Count | Result | Scope Verified |
|---|---:|---|---|
| `apps.notifications.tests_stage4_15_auth` | 6 | **OK** | Priority 4 strict 403/404/400 tenant auth, multi-tenant, RBAC, retry isolation |
| `apps.notifications.tests` | 16 | **OK** | Outbox lifecycle, lease crash recovery, public token headers & expiry, RBAC |
| `apps.inventory.tests_stage4_15_inventory` | 3 | **OK** | Priority 5 negative-stock policy, FIFO lots, CN/DN cost, reversal, 2-thread PG race |
| `apps.inventory.tests` | 2 | **OK** | Category filtering & reorder analytics |
| `apps.accounting.tests_sales_stock_audit` | 3 | **OK** | Draft/posted/deleted sales stock parity |
| `apps.accounting.tests_stage4_14_certification` | 7 | **OK** | Celery autodiscovery/settings & Outbox Scenarios 1–10 (incl. 2-thread PG concurrency) |
| `apps.accounting.tests_stage4_13_stabilization` | 4 | **OK** | DR `AuditLog`/`SyncEvent` hash restore, reversal report parity, outbox recovery, single-query aging |
| `apps.accounting.tests_stage4_12_remediation` | 8 | **OK** | DEF-01 duplicate payment override RBAC, DEF-02 metadata OCC concurrency (`200`/`409`) |
| `apps.accounting.tests_staging_isolation` | 12 | **OK** | Fail-closed DB isolation guard & health endpoint secret hygiene |
| `apps.common.tests_disaster_recovery` | 1 | **OK** | Encrypted backup & restore DR check |
| `apps.common.tests_code_review_findings` | 12 | **OK** | Security, concurrency, and accounting invariants |
| `apps.accounting.tests_voucher_occ` | 13 | **OK** | OCC version enforcement & concurrent updates |
| `apps.accounting.tests_deduplication` | 11 | **OK** | Idempotency & duplicate protection |
| `apps.accounting.tests_financial_reports` | 6 | **OK** | TB, P&L, Balance Sheet, GST equilibrium |
| `apps.accounting.tests_master_stabilization` | 10 | **OK** | Posting, reversal, period lock invariants |
| `apps.ledgers.tests_opening_balance` | 12 | **OK** | Opening balances, FIFO allocation, credit limit, balance rebuild |
| **Total (PostgreSQL)** | **126** | **OK** | **16 modules, `0` failures, `0` skipped** |

---

## 2. Live Render (`c15a64fb`) & Read-Only Checks

| Test / Probe | Environment | Expected Result | Actual Result | Pass/Fail |
|---|---|---|---|---|
| `python manage.py makemigrations --check --dry-run` | Local codebase (`c15a64fb`) | `No changes detected` | `No changes detected` (`exit 0`) | **PASS** |
| Live Staging Health (`GET /api/v1/health/environment/`) | `https://vouch-u3u7.onrender.com` | `commit: "c15a64fb"`, `environment: "staging"`, `neondb_staging`, `6f4741bdaaf4` | Exact match (`commit: "c15a64fb"`, `environment: "staging"`, `unapplied_count: 0`, `redis.status: "unreachable"`, `workers_online: 0`) | **PASS** (API/DB) / **FAIL** (Redis/Worker) |
| Live Notification Auth Probes (`task-50435`) | `https://vouch-u3u7.onrender.com` (`c15a64fb`) | Own `200`, cross-tenant `403`, unknown `404`, bad UUID `400`, `VIEWER` `403` | Exact match (`own_200: 200 (50)`, `unauth_403: 403`, `unknown_404: 404`, `bad_uuid_400: 400`, `viewer_403: 403`) | **PASS** |
| Live Production Health Check (Read-Only) | `https://vouch-api-752s.onrender.com/api/health/` | `HTTP 200`, `environment: "production"` | `HTTP 200`, `environment: "production"` | **PASS** |
| Read-Only Production Migration Audit | `neondb` (`1f2263fa6ab9`, `READ ONLY`) | `0` mismatch, `0` 2026-11-12 migrations | `145/145` exact match (`[]` missing, `[]` extra, latest applied `2026-11-04`) | **PASS** |
| Native PostgreSQL `pg_dump` / `pg_restore` | Local Windows Host | Native binary DR verification | `pg_dump: None`, `pg_restore: None`, `psql: None` | **UNVERIFIED (No PG CLI)** |

---

## 3. Frontend Verification (`cd frontend`, `task-50403`)

| Command | Expected | Actual Output | Pass/Fail |
|---|---|---|---|
| `npm test` (`node --import ./test-loader.mjs --test "src/**/*.test.ts"`) | All unit tests pass | **`18 / 18 pass`** across `3` suites (`0` fail, `0` skipped, `1943.6312ms`) | **PASS** |
| `npx tsc --noEmit` | Exit `0` | Exit `0` (zero TS errors) | **PASS** |
| `npm run build` (`next build --webpack`) | Clean Next.js production build | Compiled in `12.0s`, **`54/54` static/app routes built**, Serwist `sw.js` bundled (`exit 0`) | **PASS** |
| `npm run lint` (`eslint`) | Zero lint errors | `3077 problems (1084 errors, 1993 warnings)` (pre-existing repo lint debt, exit non-zero) | **FAIL (Pre-existing Lint Debt)** |
