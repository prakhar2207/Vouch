# SRI LEKH — STAGE 1.2.1: FINAL ACCEPTANCE REPORT

**Certification Date:** 2026-11-12  
**Branch:** `fix/stage4-12-day6-remediation`  
**Staging Commit SHA:** `f8578a88254f5d36f3cb3c5a1feed56f31ca1afe` (`f8578a88`)  
**Staging Backend URL:** `https://vouch-u3u7.onrender.com`  
**Staging Database:** `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`, fingerprint `6f4741bdaaf4`)  

---

## 1. Independent Workstream Separation & Safety Verification

- **Production Isolation:** `https://vouch-api-752s.onrender.com`, production `neondb`, branches `main` and `release/stage4-final-rc-integration`, and protected production tenant **`Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`)** remained **100% untouched** (`0` rows in `neondb_staging`).
- **Pre-Existing External Blockers Preserved (Out of Scope):**
  - Stage 4.15: Managed staging Redis (`status: "unreachable"`), Celery Worker/Beat (`workers_online: 0`), native `pg_dump`/`pg_restore`, and 7-day live operational soak.
  - Stage 1.1: Owner & legal sign-off on commercial/privacy disclosures and `/privacy-policy` Sections 7 & 9 cookie update.

---

## 2. Stage 1.2.1 Acceptance Matrix

Allowed statuses: `PASS`, `FAIL`, `BLOCKED`, `NOT RUN`, `PARTIALLY VERIFIED`.

| Verification Area | Status | Evidence Summary & Exact Distinction (Live Staging vs Local / Blocked) |
| :--- | :--- | :--- |
| Staging backend deploy & DB isolation (`vouch-u3u7` -> `neondb_staging`, commit `f8578a88`) | **PASS** | `/api/v1/health/environment/` returned `healthy`, `commit: f8578a88`, `sanitized_target: neondb_staging`, `identity_fingerprint: 6f4741bdaaf4`, `is_isolated: true`, `unapplied_count: 0`; [`verify_staging_identity.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/scripts/verify_staging_identity.py) confirmed 146 migrations and 0 prod tenant rows. |
| Migration `accounts.0007_user_token_version` & column backfill | **PASS** | `showmigrations accounts` showed `[X] 0007_user_token_version`; `makemigrations --check --dry-run` -> `No changes detected`; `accounts_user.token_version` verified `integer NOT NULL` with all 12 existing staging users backfilled to `0`. |
| CORS & credentialed cross-origin policy (`https://vouch-u3u7.onrender.com`) | **PASS** | Live `OPTIONS`: `vouch-pi-one.vercel.app` & `staging.srilekh.com` -> `200`, exact `ACAO`, `ACAC=true`; `evil-attacker.example`, `localhost:3000`, and un-whitelisted Vercel preview URL -> `ACAO=None`, `ACAC=None`. |
| Browser cookie login (`X-Client-Type: web`), `HttpOnly`/`Secure`/`SameSite=None`, zero JSON JWTs | **PASS** | Live `POST /api/v1/auth/login/` (`X-Client-Type: web`, `Origin: https://vouch-pi-one.vercel.app`) returned `200`, omitted `access`/`refresh` from JSON, set `srilekh_access` (`HttpOnly; Secure; SameSite=None; Path=/`) & `srilekh_refresh` (`HttpOnly; Secure; SameSite=None; Path=/api/v1/auth/`); `GET /api/v1/auth/me/` via cookies returned `200`. |
| CSRF protection across `PATCH`, `POST`, `DELETE` | **PASS** | Live requests via cookie auth returned `403` without `X-CSRFToken` and `200`/`201` with `X-CSRFToken` across `PATCH /auth/me/`, `POST /accounting/sales-invoice/`, and `DELETE /accounting/vouchers/detail/<id>/`. |
| Refresh-token rotation & replay rejection | **PASS** | Live `POST /api/v1/auth/refresh/` rotated `srilekh_refresh` (`200`), and replaying the pre-rotation refresh cookie failed with `401`. |
| Logout cookie clearing & `User.token_version` revocation | **PASS** | Live `POST /api/v1/auth/logout/` cleared auth cookies (`Max-Age=0`), incremented `token_version` (`0 -> 1` in `neondb_staging`), and caused stale access cookie, stale refresh cookie, and pre-logout Bearer token to return `401`. |
| Password reset revocation E2E on live staging | **PARTIALLY VERIFIED** | Live `/api/v1/auth/password/reset/confirm/` fail-closed check rejected cross-secret token (`400`); however `POST /api/v1/auth/password/reset/request/` on active synthetic account hit synchronous outbound SMTP timeout (`TimeoutError`) on Render without staging mailbox access. Full `PasswordResetConfirmView` `token_version` revocation (`401`) verified in isolated local backend suite (`34/34` pass). |
| Stage 4.15 API compatibility under HttpOnly cookie auth | **PASS** | Live cookie session passed `companies`, Balance Sheet (`diff: 0.00`), cross-tenant IDOR (`403`), Trial Balance, P&L, Vouchers list, Ledger Statement, Notifications, posted Sales Invoice creation (`201`, `INV/26-27/0008`), voucher detail (`200`), and post-write Balance Sheet (`diff: 0.00`). Baseline `test_live_render_staging.py` passed `100%`. |
| Capacitor compatibility (`X-Client-Type: capacitor`) | **PARTIALLY VERIFIED** | Live staging API (`auth_mode=token`, Bearer `PATCH` without CSRF `200`, JSON refresh `200`, Bearer logout `200` -> `401`) and local unit mocks (`28/28`) passed; physical Android/iOS binary execution **NOT RUN**. |
| Live deployed staging frontend UI, browser storage DOM, multi-tab UI logout, offline `VouchOfflineDB`/`LogoutConfirmModal` E2E & deployed public routes | **BLOCKED** | `staging.srilekh.com` has no DNS record; `vouch-git-fix-stage4-12-day6-remediation-trail-blazer.vercel.app` is gated behind Vercel Deployment Protection (`Title: Login – Vercel`) and lacks Render CORS + verified `NEXT_PUBLIC_API_URL=https://vouch-u3u7.onrender.com`; `vouch-pi-one.vercel.app` & `srilekh.com` serve `main` (`404` on `/pricing`). *(Post-commit local frontend suite: `28/28` `npm test`, `0` `tsc` errors, `56/56` `npm run build`.)* |
| Targeted backend regression (`accounts`, `companies`, `audit`) | **PASS** | Re-executed post-commit on isolated SQLite DB: `34 / 34` tests passed (`47.223s`, `exit 0`). |

---

## 3. Two Required Final Verdicts

### Verdict 1 — Stage 1.2.1 (Staging Deployment & Integration Certification)
**PARTIALLY CERTIFIED — STAGING BACKEND & API INTEGRATION PASSED; STAGING FRONTEND BROWSER E2E BLOCKED ON VERCEL/DNS/CORS ACCESS**

- The Stage 1.2 authentication and cookie/CSRF/revocation engine is **live on Render staging (`vouch-u3u7.onrender.com`, commit `f8578a88`)** and **migrated on `neondb_staging` (`0007_user_token_version`)**, with every HTTP/TLS security and Stage 4.15 accounting equilibrium check passing live.
- Remaining live staging verification items (deployed cross-origin browser DOM/cookie E2E, live multi-tab browser UI logout, live deployed offline IndexedDB & Shared-Device logout E2E, deployed public routes, and live SMTP password-reset inbox completion) require external infrastructure configuration outside repository/agent access:
  1. Provision a publicly reachable staging frontend domain/bypass (`staging.srilekh.com` DNS or Vercel Deployment Protection bypass) configured with `NEXT_PUBLIC_API_URL=https://vouch-u3u7.onrender.com`.
  2. Add that exact staging frontend origin to Render `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`.
  3. Configure non-blocking or test-accessible staging email delivery for `/api/v1/auth/password/reset/request/`.

### Verdict 2 — Production Promotion Readiness
**NO-GO (HOLD)**

Production promotion remains **strictly blocked** until ALL of the following external & remaining gates are closed:
1. Completion of **Stage 1.2.1 live deployed staging frontend browser E2E** (Vercel staging deployment <-> Render staging backend) + resolution of staging SMTP timeout risk.
2. **Stage 4.15 external infrastructure blockers:** Managed Redis + Celery Worker/Beat, native PostgreSQL `pg_dump`/`pg_restore` certification, and 7-day operational soak.
3. **Stage 1.1 owner & legal sign-off:** Commercial pricing/entity disclosures and updating `/privacy-policy` Sections 7 & 9 for HttpOnly cookie storage.
