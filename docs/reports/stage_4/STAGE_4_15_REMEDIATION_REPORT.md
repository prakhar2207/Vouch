# SRI LEKH — STAGE 4.15 REMEDIATION & PRODUCTION READINESS REPORT

**Date:** 2026-11-12  
**Branch:** `fix/stage4-12-day6-remediation` (`c15a64fb2793a8d1abc762997a1202d73b4b92ae`, pushed to `origin/fix/stage4-12-day6-remediation`)  
**Protected Branches (Untouched):** `main` (`origin/main` `d39d481ac2eb545d0436fafa9dd2c593ceb7e946`, local `f09087fa`), `release/stage4-final-rc-integration` (`4888e451c7155220527b47e6ba5c3f09f14ec61d`)  
**Staging Deployment:** `https://vouch-u3u7.onrender.com` (Live commit verified: `c15a64fb`, `environment: "staging"`)  
**Staging Database:** `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`, fingerprint `6f4741bdaaf4`, `is_isolated=True`)  
**Protected Production Tenant Check:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) absent (`count=0`) and untouched across all runs.

---

## Executive Summary & Release Verdict

### **Final Production Release Decision: `NO-GO`**

All application-level security, inventory, accounting, and read-only production migration audit objectives for Stage 4.15 have been completed and verified on live Render staging (`c15a64fb`) and PostgreSQL `test_neondb_staging` (**`126 / 126` tests `OK`**). However, **production promotion remains strictly blocked (`NO-GO`)** under Stage 4.15 acceptance criteria because three external infrastructure/time gates remain unprovisioned:

1. **Managed Staging Redis & Live Celery Worker / Beat Services (Priorities 1 & 2):** Live Render staging (`vouch-u3u7`) runs a Free-tier web dyno without a reachable Redis instance (`redis.status: "unreachable"`) or background worker/scheduler dynos (`workers_online: 0`, `beat_schedule_active: false`). Paid Starter+ Render instances (or equivalent worker hosting + managed TLS Redis) require external account/payment provisioning.
2. **Native PostgreSQL Binary DR (`pg_dump` / `pg_restore`, Priority 6):** `pg_dump`, `pg_restore`, and `psql` are absent from the Windows host (`shutil.which` -> `None`, `C:\Program Files\PostgreSQL` -> `False`), and the local Docker service (`com.docker.service`) is stopped. Native `PGDMP` DR therefore remains unverified on a binary-capable host (Encrypted JSON DR previously passed).
3. **Seven-Day Live Operational Soak (Priority 8):** Per Stage 4.15 rules, the 7-day continuous soak cannot begin until Redis, Celery Worker, and Celery Beat are live and processing scheduled tasks continuously.

---

## Baseline & Priority Findings Summary

| Priority | Area | Root Cause / Finding | Outcome |
|---|---|---|---|
| **Priority 1** | Live Redis Provisioning | `REDIS_URL` defaults to unreachable `127.0.0.1:6379`; no managed Redis provisioned for `vouch-u3u7`; local `com.docker.service` is stopped | **BLOCKED (External Paid/Provisioning Gate)** |
| **Priority 2** | Live Celery Worker & Beat | [Procfile](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/Procfile) & [render.yaml](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/render.yaml) configured (`acks_late=True`, `reject_on_worker_lost=True`, `prefetch=1`), but Render runs web-only (`workers_online: 0`) | **BLOCKED (External Paid Render Worker Gate)** |
| **Priority 3** | Transactional Outbox Reliability | Outbox queue clean (`0 PENDING`, `9` historical `DEAD_LETTER`, `0` duplicate sends); `7/7` Stage 4.14 & `16/16` notification PG tests pass | **PASS (Code/DB) / BLOCKED ON LIVE WORKER** |
| **Priority 4** | Notification Log Tenant Auth | `_get_target_company()` in [views.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/views.py) fell back silently on unauthorized `company_id`; replaced with strict `_resolve_authorized_company()` (`403`/`404`/`400`), verified `6/6` PG + live on `c15a64fb` | **PASS (Verified Live on `c15a64fb`)** |
| **Priority 5** | Precision Agro Negative Inventory | Forensic audit traced all 3 negative SKUs (`-474`, `-194`, `-4` totaling `-₹207,216.82` raw cost) to Stage 4.6–4.11 synthetic load tests under default `allow_negative_stock=True` (`0` orphan `InventoryEntry` rows); added [tests_stage4_15_inventory.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/inventory/tests_stage4_15_inventory.py) (`3/3 OK`) | **PASS (Root-Caused & Guarded; No Blind Manipulation)** |
| **Priority 6** | Native PostgreSQL DR | Encrypted JSON DR passed (`28,985` records, `0` errors, RTO `240.468s`), but host lacks `pg_dump`/`pg_restore`/`psql` CLI binaries | **UNVERIFIED (No PostgreSQL CLI Host)** |
| **Priority 7** | Production DB Migration Audit | Strictly read-only (`transaction_read_only=on`) audit of `neondb` (`1f2263fa6ab9`, PostgreSQL `18.6`): **`145 / 145`** migrations match identically (`[]` missing, `[]` extra); zero migrations executed on `2026-11-12` | **PASS (Zero Schema Mismatch)** |
| **Priority 8** | Seven-Day Operational Soak | Day 6/7 point-in-time cohort census healthy across all 5 pilot tenants, but 7-day continuous worker soak cannot start until Redis+Worker+Beat are live | **NOT STARTED (Gated on Worker)** |

---

## Stage 4.15 Code & Test Files Added / Modified

- Modified: [apps/notifications/views.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/views.py) (`_resolve_authorized_company` fail-closed `403`/`404`/`400` + header/query conflict guard)
- Added: [apps/notifications/tests_stage4_15_auth.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/tests_stage4_15_auth.py) (`6` tests covering cross-tenant, unknown UUID, invalid UUID, multi-tenant, roles `OWNER`/`ADMIN`/`EMPLOYEE`/`VIEWER`/`CA`, and retry auth)
- Added: [apps/inventory/tests_stage4_15_inventory.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/inventory/tests_stage4_15_inventory.py) (`3` tests covering `allow_negative_stock` policies, partial stock, purchase recovery, FIFO lot exhaustion, credit note acquisition cost, debit note, voucher reversal, and concurrent PostgreSQL sales deductions)

---

## Remaining Risks & Limitations

1. **No Active Background Worker / Beat on Render Staging:** Outbox retries, 60-second sweeps, and nightly automated backups do not run automatically on Render until Redis + Starter Worker/Beat services are provisioned.
2. **Pre-Existing Frontend ESLint Debt:** `npm run lint` in `frontend/` reports `3077 problems (1084 errors, 1993 warnings)` (though `tsc --noEmit`, `npm test` `18/18`, and `next build` `54/54` pages exit `0`).
3. **Seeded Opening Stock vs `rebuild_company_stock()`:** Forensic audit observed that products seeded with `Product.stock_quantity > 0` at creation time without initial `'IN'` `InventoryEntry` rows (e.g., `SKU-8483-18` `150.00`, `SKU-0601-EXM` `50.00`, `SKU-4016-12` `120.00`, `SKU-5208-05` `80.00`, `SKU-8708-28` `40.00`) would lose un-entered opening balances if `StockService.rebuild_company_stock()` were executed blindly (`rebuild_stock_logs: []`, so never executed on Precision Agro).
