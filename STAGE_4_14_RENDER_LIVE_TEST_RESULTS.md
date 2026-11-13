# SRI LEKH — STAGE 4.14 RENDER LIVE TEST RESULTS

**Environment:** Live Render Staging Web Service (`https://vouch-u3u7.onrender.com`) + Vercel Frontend (`https://vouch-pi-one.vercel.app`)  
**Live Deployed Commit SHA:** `990a13bd` (`fix/stage4-12-day6-remediation`)  
**Database Fingerprint:** `6f4741bdaaf4` (`neondb_staging` on `ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`)  
**Execution Timestamp:** `2026-11-12 13:43–13:54 IST`

---

## Test Command / Procedure

1. `python scripts/test_live_render_staging.py --base-url https://vouch-u3u7.onrender.com --expected-commit 990a13bd --timeout 90` (`task-50149`)
2. Comprehensive live HTTPS certification script `stage4_14_live_render_audit.py` (`task-50242`) testing:
   - Health & Environment Identity (`/api/v1/health/environment/`, `/api/health/`)
   - Auth (`/api/v1/auth/login/` across Precision Agro, Garodia, Shree Radhe, plus dedicated sandbox OWNER/EMPLOYEE/CA/VIEWER)
   - Company selection (`/api/v1/companies/`)
   - Precision Agro live read-only reports (TB, BS, P&L, Ledger List, Party Ledger, Receivables Aging, Payables Aging)
   - Dedicated sandbox tenant (`Stage 4.14 Live Audit Sandbox`, `e09b235c-fffa-4410-a162-cb212fc4b3b6`) live HTTPS write lifecycle (`DRAFT -> POST -> OCC Edit -> Stale OCC 409 -> Payment Receipt / Duplicate 409 / EMPLOYEE 403 -> Reversal -> All Reports`)
   - Verification that all 5 canonical pilot tenants remained 100% unchanged (`pilot_unchanged == True`)

---

## Expected vs Actual Outcomes

| Check | Expected Outcome | Actual Outcome | Status |
|---|---|---|---|
| `GET /api/v1/health/environment/` | `HTTP 200`, `commit: 990a13bd`, `environment: staging`, `neondb_staging`, `6f4741bdaaf4`, `is_isolated: true`, `unapplied_count: 0`, no secrets | `HTTP 200` (`358.4ms`), exact JSON match: `commit: "990a13bd"`, `environment: "staging"`, `neondb_staging`, `6f4741bdaaf4`, `is_isolated: true`, `unapplied_count: 0`, `secret_leak_check: true`; `redis.status: "unreachable"`, `celery.workers_online: 0` | **PASS** (API); **FAIL** (Worker/Redis offline) |
| `GET /api/health/` | `HTTP 200`, `environment: staging` | `HTTP 200` (`212.6ms`), `environment: "staging"`, `commit: "protected"` | **PASS** |
| `POST /api/v1/auth/login/` | JWT access token issued (`200`) | Precision Agro Owner `200`, Garodia Owner `200`, Shree Radhe Owner `200` | **PASS** |
| `GET /api/v1/companies/` | `200` tenant company list | `HTTP 200` | **PASS** |
| Precision Agro Live Read-Only Reports | Balanced TB/BS/P&L, Party Ledger, Aging `200` | TB `200` (`279.2ms`, `balanced: true`, `1694738.70`), BS `200` (`359.5ms`, `balanced: true`, `diff: "0.00"`), P&L `200` (`276.2ms`, `1116043.40`), Ledgers `200`, Party Ledger `200` (`277.7ms`), Rec Aging `200` (`246.5ms`, `1331995.10`), Pay Aging `200` (`260.7ms`, `4725.74`) | **PASS** |
| Sandbox Draft -> Post -> OCC Edit -> Stale `409` | `201 DRAFT` -> `200 POSTED` -> `200` OCC edit -> `409` stale OCC | `draft_create_status: 201` (`DRAFT`), `post_patch_status: 200` (`POSTED`), `occ_edit_status: 200`, `occ_stale_conflict_status: 409` | **PASS** |
| Sandbox Payment Duplicate & `EMPLOYEE` Override | First `201`, repeat `409`, `EMPLOYEE` override `403` | Initial receipt `201` (Run 1) / duplicate `409` (`duplicate_receipt_block_status: 409`), `EMPLOYEE allow_duplicate=True`: `403` | **PASS** |
| Sandbox Reversal & Live Reports | Original `REVERSED`, Reversal `POSTED` (`REV-*`), TB/BS/PTB balanced, `drifts: 0` | `original_after_reversal`: `200 REVERSED`; `REV-INV/26-27/0002`: `200 POSTED`; TB `200` (`balanced: true`, `500.0 == 500.0`, `drifts: 0`), BS `200` (`balanced: true`, `diff: "0.00"`), P&L `200` (`0.00`), Period TB `200` (`balanced: true`), Period Statement `200` (`500.00 CR`), Ledger Statement `200` (`500.00`), Rec/Pay Aging `200` (`0.0` / `0.0`) | **PASS** |
| CORS Preflight (`vouch-pi-one.vercel.app`) | `200` + matching ACAO header | `HTTP 200`, `Access-Control-Allow-Origin: https://vouch-pi-one.vercel.app` | **PASS** |
| 5 Canonical Pilot Tenants Unchanged | Zero count/TB delta before vs after | `pilot_unchanged: true` | **PASS** |

---

## Remaining Limitations

1. Live Render `vouch-u3u7` serves only the Django/Gunicorn `web` process on Free tier (~44s cold start when spun down); background Celery worker/beat processes and Redis are unreachable live.
2. Canonical pilot accounts tested via API login were Precision Agro, Garodia, and Shree Radhe owners plus sandbox accounts (Alpha/Beta admin passwords were not modified).
