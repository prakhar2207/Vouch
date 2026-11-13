# SRI LEKH — STAGE 4.14 DEPLOYMENT & PRODUCTION RELEASE CERTIFICATION

**Environment:** Staging (`https://vouch-u3u7.onrender.com` / `neondb_staging`)  
**Audited Live Deployed Commit SHA:** `990a13bd516ea0d9a471839ee381888dead11d6b` (`990a13bd` on `fix/stage4-12-day6-remediation`)  
**Baseline Release Candidate (Untouched):** `release/stage4-final-rc-integration` (`4888e451c7155220527b47e6ba5c3f09f14ec61d`)  
**Production Branch (`origin/main`):** `d39d481ac2eb545d0436fafa9dd2c593ceb7e946` (`vouch-api-752s.onrender.com` restored to `d39d481`)  
**Database Fingerprint:** `6f4741bdaaf4` (`neondb_staging` on `ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`, `is_isolated=True`)  
**Execution Timestamp:** `2026-11-12 13:43–14:05 IST`

---

## Final Release Decision: **`NO-GO` FOR PRODUCTION PROMOTION**

*(Staging Web API & Accounting/Security Verification: **PASS**; Live Background Worker/Redis & 7-Day Soak: **BLOCKED / FAIL**; Native PostgreSQL DR CLI Tools: **UNVERIFIED / UNAVAILABLE**)*

Production promotion (`main` merge / deploy to `https://srilekh.com`) remains **strictly blocked (`NO-GO`)** because live Render staging currently has **no active Redis broker and zero online Celery worker or Beat scheduler processes** (`redis.status: "unreachable"`, `celery.workers_online: 0`, `beat_schedule_active: false`), native `pg_dump`/`pg_restore` binary backup/restore has not been executed in this environment, and the 7-day live operational soak with background workers active has not completed.

---

## Distinction Across Verification Layers

| Layer | Verdict | Observed Evidence | Remaining Limitation |
|---|---|---|---|
| **1. Code-Level Verification** | **PASS** | `fix/stage4-12-day6-remediation` (`2945375` + `47d340f` + `990a13b`) + [tests_stage4_14_certification.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/tests_stage4_14_certification.py): `11/11` Stage 4.14/4.13 PG tests `OK` (plus prior `77/77` PG & `12/12` FE checks). Celery autodiscovery (`7` tasks, `2` Beat schedules), `acks_late=True`, `reject_on_worker_lost=True`, `prefetch_multiplier=1`. | Local Celery suite used PostgreSQL `test_neondb_staging` + patched SMTP rather than live Render Redis worker dyno. |
| **2. Staging Database (`neondb_staging`)** | **PASS** | Host `ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`, DB `neondb_staging`, fingerprint `6f4741bdaaf4`, `is_isolated=True`. Protected `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) confirmed absent (`count=0`). `0/113` ledger drifts, `0` per-company `AuditLog` hash breaks, `0` pending outbox events, `0` invalid FIFO allocations. | Precision Agro synthetic stress-test SKUs show negative raw inventory (`-207,216.82` cost basis; Balance Sheet stock valuation safely clamps negatives). |
| **3. Live Render Deployment (`vouch-u3u7`)** | **PASS** | Live `GET /api/v1/health/environment/` returned `HTTP 200` (`358.4ms` warm) reporting `commit: "990a13bd"`, `environment: "staging"`, `neondb_staging`, `6f4741bdaaf4`, `is_isolated: true`, `unapplied_count: 0`, CORS `https://vouch-pi-one.vercel.app` verified, full sandboxed write/OCC/reversal/security lifecycle passed (`pilot_unchanged: true`). | Render Free tier spins down on idle (~44s cold wake). |
| **4. Background Worker & Redis (Live Render)** | **FAIL** | Live `/api/v1/health/environment/` on Render honestly reported `"redis": {"configured": true, "status": "unreachable"}` and `"celery": {"beat_schedule_active": false, "workers_online": 0}`. | No managed Redis instance or Render `worker`/`beat` services provisioned on staging (`vouch-u3u7` runs Free web dyno only). |
| **5. Disaster Recovery** | **CONDITIONAL (JSON PASS / Native N/A)** | Disposable PostgreSQL JSON backup & restore (`neondb_staging_dr_restore_s414`) passed (`28,985` records, `0` errors, RTO `240.468s`, `1,231/1,231` `AuditLog` PKs, `0` hash breaks, exact sequences & 5-tenant parity). | Local host lacks `pg_dump`, `pg_restore`, and `psql` (`shutil.which` -> `None`), and Docker daemon is stopped; native PG DR unverified. |
| **6. 7-Day Operational Soak** | **IN PROGRESS / BLOCKED** | Day 6/7 point-in-time cohort census on all 5 synthetic pilot tenants (`Garodia`, `Precision Agro`, `Shree Radhe`, `Beta`, `Alpha`) shows clean accounting parity and `0` backlog. | Full 7-day continuous live worker + uptime soak requires active Redis + Celery Worker/Beat services on Render. |
| **7. Production Promotion Readiness** | **NO-GO** | Blocked on Render Redis + Worker + Beat live verification, native `pg_dump`/`pg_restore` verification, and completed worker-enabled soak window. | `main` and `release/stage4-final-rc-integration` remain untouched (`fix/stage4-12-day6-remediation` only). |

---

## Production Render Incident Caught & Reverted During Rollout

- **Procedure & Observation:** During Render staging setup, commit `990a13b` was initially pushed to Render service **`vouch-api`** (`Vouch > Production > vouch-api`, `https://vouch-api-752s.onrender.com`, `srv-dabgvah5efls73ao02cg`). When `ENVIRONMENT=staging` was subsequently added to that service, [config/environment_guard.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/environment_guard.py) failed the `./build.sh` `collectstatic` step with `ImproperlyConfigured: FATAL ISOLATION DEFECT: Environment is configured as 'staging', but database name is 'neondb'`.
- **Expected Outcome:** Fail-closed guard must prevent a `staging` configuration from booting against `neondb`; production `vouch-api-752s` must run `origin/main` (`d39d481`) with `ENVIRONMENT=production`; staging `vouch-u3u7` must run `990a13b` with `ENVIRONMENT=staging` against `neondb_staging`.
- **Actual Outcome:** Fail-closed guard aborted the misconfigured build cleanly. Operator restored `vouch-api` (`Production`) to `d39d481` on `main` (verified via `/api/v1/health/environment/` returning `404` and `/api/health/` returning `HTTP 200` with `environment: "production"`), and deployed `990a13b` onto **`vouch-u3u7`** (`https://vouch-u3u7.onrender.com`).
- **Pass/Fail:** **PASS** (fail-closed guard prevented `staging`->`neondb` boot; staging and production Render services verified separated). *Note: Verify production `neondb` migration state (`showmigrations`) separately if `990a13b`'s initial `build.sh` ran `migrate` against `neondb`.*
