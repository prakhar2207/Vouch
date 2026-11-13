# SRI LEKH — STAGE 4.14 LIVE SECURITY & TENANT ISOLATION CERTIFICATION

**Environment:** Live Render Staging (`https://vouch-u3u7.onrender.com`) + Vercel (`https://vouch-pi-one.vercel.app`)  
**Commit SHA:** `990a13bd` (`fix/stage4-12-day6-remediation`)  
**Database Fingerprint:** `6f4741bdaaf4` (`neondb_staging`, `is_isolated=True`, `Maa Annapurna Belting Store` absent)  
**Execution Timestamp:** `2026-11-12 13:53–13:54 IST`

---

## Test Command / Procedure

Executed live HTTPS probes via `stage4_14_live_render_audit.py` (`task-50242`) directly against `https://vouch-u3u7.onrender.com` using synthetic staging accounts across `Precision Agro Tools Pvt Ltd` (`c2771ca4-31bd-47d2-b98c-c1be119f40a1`), `Garodia Bearing & Power Transmission` (`cd788d07-ae29-4af9-89d2-c5a4f32378cf`), and `Stage 4.14 Live Audit Sandbox` (`e09b235c-fffa-4410-a162-cb212fc4b3b6`).

---

## Live Security Verification Matrix

| Security Vector | Expected Outcome | Actual Outcome | Status |
|---|---|---|---|
| Unauthenticated `GET /api/v1/accounting/vouchers/{id}/` | `HTTP 401` | `HTTP 401` | **PASS** |
| Cross-Tenant Voucher Detail (Agro Owner -> Garodia Voucher) | `HTTP 403` / `404` | `HTTP 403` | **PASS** |
| Cross-Tenant Trial Balance (`Garodia`) | `HTTP 403` | `HTTP 403` | **PASS** |
| Cross-Tenant Balance Sheet (`Garodia`) | `HTTP 403` | `HTTP 403` | **PASS** |
| Cross-Tenant Profit & Loss (`Garodia`) | `HTTP 403` | `HTTP 403` | **PASS** |
| Cross-Tenant Aging (`Garodia`) | `HTTP 403` | `HTTP 403` | **PASS** |
| Cross-Tenant Period Statement (`Garodia` Ledger) | `HTTP 403` / `404` | `HTTP 404` | **PASS** |
| Cross-Tenant Ledger Statement (`Garodia` Ledger) | `HTTP 403` | `HTTP 403` | **PASS** |
| Cross-Tenant Notification Log Retry (`POST /api/v1/notifications/logs/{other_id}/retry/`) | `HTTP 403` / `404` | `HTTP 404` | **PASS** |
| Cross-Tenant Notification Logs List (`?company_id={garodia_id}`) | Zero cross-tenant leakage (`403` or caller's own only) | `HTTP 200` with **`0` Garodia logs** (falls back via `_get_target_company`) | **PASS (No Leakage)** *(Note)* |
| `VIEWER` Write Restriction (`POST /api/v1/accounting/sales-invoice/`) | `HTTP 403` | `HTTP 403` | **PASS** |
| `EMPLOYEE` Duplicate Payment Override (`allow_duplicate=True`) | `HTTP 403` | `HTTP 403` | **PASS** |
| `CA` Role Report Read Access | `HTTP 200` | `HTTP 200` | **PASS** |
| `OWNER` Authorized Accounting Writes & Reads | `HTTP 200` / `201` | `HTTP 200` / `201` | **PASS** |
| OCC Stale-Write Conflict (`PATCH` with stale `version` / `If-Match`) | `HTTP 409 Conflict` | `HTTP 409` | **PASS** |
| Duplicate Payment Protection (Repeat `RECEIPT` without override) | `HTTP 409 Conflict` | `HTTP 409` | **PASS** |
| CORS Preflight Authorized Origin (`https://vouch-pi-one.vercel.app`) | `HTTP 200`, `ACAO=https://vouch-pi-one.vercel.app` | `HTTP 200`, `ACAO=https://vouch-pi-one.vercel.app` | **PASS** |
| CORS Preflight Unauthorized Origin (`https://evil.example.com`) | `Access-Control-Allow-Origin` omitted | `Access-Control-Allow-Origin: null` (absent) | **PASS** |
| Response Security Headers (`Balance Sheet` HTTPS response) | `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `HSTS` | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` | **PASS** |
| SQL Injection Probe (`?search=' OR 1=1--`) | Safe handling, zero SQL error/trace leakage | `HTTP 403` (edge/WAF blocked `' OR 1=1--`), `has_sql_error: false` | **PASS** |
| Health Endpoints Sensitive Data Exposure Check | Zero `password`/`secret`/`postgres://`/`redis://` in responses | `secret_leak_check: true` (clean) | **PASS** |
| Staging Database Isolation Guard (`validate_environment_database_isolation`) | Fail-closed when `ENVIRONMENT=staging` targets `neondb` | Observed live in Render build log blocking `ENVIRONMENT=staging` against `neondb` (`ImproperlyConfigured`) | **PASS** |

---

## Remaining Limitations & Hardening Notes

1. `EmailDeliveryLogListView` uses `_get_target_company()` in [apps/notifications/views.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/views.py), which silently falls back to the caller's first company when an unauthorized `company_id` query param is supplied rather than returning `403`. Zero cross-tenant records leak, though strict `403` rejection on explicit unauthorized `company_id` is recommended polish.
2. API authentication relies on `Authorization: Bearer <JWT>` (`SimpleJWT`), so CSRF cookies are not used for API token calls.
