# SRI LEKH — STAGE 1.2.1: AUTHENTICATION & API E2E REPORT

**Verification Date:** 2026-11-12  
**Live Backend Under Test:** `https://vouch-u3u7.onrender.com` (commit `f8578a88`, `neondb_staging`)  
**Security Redaction Policy:** All JWTs and CSRF cookie strings were SHA-256 digested for comparison and redacted from all logs and reports (`<redacted len=...>`).

---

## 1. Live HTTPS Backend Auth & Cookie Protocol Checks (`https://vouch-u3u7.onrender.com`)

Executed directly over TLS against Render staging using `Origin: https://vouch-pi-one.vercel.app` and `X-Client-Type: web` (for browser-mode checks) or `X-Client-Type: capacitor` (for native Bearer checks).

| Check | Endpoint / Method | Observed Result | Status |
| :--- | :--- | :--- | :--- |
| **CSRF Initialization** | `GET /api/v1/auth/csrf/` | HTTP `200`; JSON returned `csrf_token`; `Set-Cookie: csrftoken=<redacted>; Path=/; SameSite=None; Secure` (cross-site origin, HTTPS). | **PASS** |
| **Browser Cookie Login & Payload Scrubbing** | `POST /api/v1/auth/login/` (`X-Client-Type: web`, `X-CSRFToken`) | HTTP `200`; `access` and `refresh` omitted from JSON body; `Set-Cookie` issued:<br>- `srilekh_access`: `HttpOnly; Max-Age=1800; Path=/; SameSite=None; Secure`<br>- `srilekh_refresh`: `HttpOnly; Max-Age=604800; Path=/api/v1/auth/; SameSite=None; Secure` | **PASS** |
| **Cookie-Only Authenticated Read** | `GET /api/v1/auth/me/` (cookies only, no `Authorization` header) | HTTP `200`, authenticated synthetic user returned cleanly. | **PASS** |
| **CSRF Enforcement — `PATCH`** | `PATCH /api/v1/auth/me/` (cookie auth) | Without `X-CSRFToken`: HTTP **`403`**.<br>With valid `X-CSRFToken` & `Origin`: HTTP **`200`**. | **PASS** |
| **CSRF Enforcement — `POST`** | `POST /api/v1/accounting/sales-invoice/` (draft invoice, cookie auth) | Without `X-CSRFToken`: HTTP **`403`**.<br>With valid `X-CSRFToken` & `Origin`: HTTP **`201`**. | **PASS** |
| **CSRF Enforcement — `DELETE`** | `DELETE /api/v1/accounting/vouchers/detail/<draft_vid>/` (cookie auth) | Without `X-CSRFToken`: HTTP **`403`**.<br>With valid `X-CSRFToken` & `Origin`: HTTP **`200`**. | **PASS** |
| **Refresh Token Rotation & Replay Rejection** | `POST /api/v1/auth/refresh/` (`X-Client-Type: web`, `X-CSRFToken`) | HTTP `200`, zero raw tokens in JSON; `srilekh_refresh` rotated (`sha256[:10]: 6686dc7526 -> 33a83acd66`). Replaying the pre-rotation refresh cookie returned HTTP **`401`**. | **PASS** |
| **Logout Cookie Clearing & Cross-Mechanism Revocation** | `POST /api/v1/auth/logout/` (`X-Client-Type: web`, `X-CSRFToken`) | HTTP `200`; cleared `srilekh_access`, `srilekh_refresh`, `access_token`, `refresh_token` (`Max-Age=0; Expires=Thu, 01 Jan 1970`); `neondb_staging` `accounts_user.token_version` incremented `0 -> 1`. Subsequent requests with:<br>- stale access cookie -> HTTP **`401`**<br>- stale refresh cookie -> HTTP **`401`**<br>- pre-logout `Authorization: Bearer` token -> HTTP **`401`** | **PASS** |
| **Password Reset Flow** | `POST /api/v1/auth/password/reset/request/` & `POST /api/v1/auth/password/reset/confirm/` | `/password/reset/confirm/` fail-closed validation rejected a cross-secret/untrusted reset token with HTTP **`400`** (`Invalid or expired password reset link.`). However, calling `POST /api/v1/auth/password/reset/request/` on an active staging account hit synchronous outbound SMTP socket timeouts (`TimeoutError` at both `45s` and `12s` timeouts on Render), and there is no mailbox / Render `SECRET_KEY` access to retrieve a live reset link. Full `PasswordResetConfirmView` `token_version` increment & token invalidation remained verified in Stage 1.2's local backend suite (`34/34` pass). | **PARTIALLY VERIFIED** |
| **CORS & Origin Policy** | `OPTIONS /api/v1/auth/login/` | - `https://vouch-pi-one.vercel.app` -> `200`, `ACAO=https://vouch-pi-one.vercel.app`, `ACAC=true`<br>- `https://staging.srilekh.com` -> `200`, `ACAO=https://staging.srilekh.com`, `ACAC=true`<br>- `https://evil-attacker.example` -> `200`, `ACAO=None`, `ACAC=None`<br>- `http://localhost:3000` -> `200`, `ACAO=None`, `ACAC=None`<br>- `https://vouch-git-fix-stage4-12-day6-remediation-trail-blazer.vercel.app` -> `200`, `ACAO=None`, `ACAC=None` | **PASS** |
| **Capacitor Native Bearer Compatibility** | `X-Client-Type: capacitor` across login, `PATCH /me/`, JSON refresh, logout | Login HTTP `200` (`auth_mode: "token"`, `access` & `refresh` returned); Bearer `PATCH /api/v1/auth/me/` without CSRF returned HTTP **`200`**; JSON `POST /api/v1/auth/refresh/` returned HTTP **`200`**; Bearer `POST /api/v1/auth/logout/` returned HTTP **`200`**, and subsequent Bearer `GET /api/v1/auth/me/` returned HTTP **`401`**. *(Note: `Set-Cookie` headers are also present on response headers per shared helper [`attach_auth_cookies`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/cookies.py#L135-L169), while Capacitor operates strictly via JSON Bearer storage in `@capacitor/preferences`.)* | **PASS** *(Backend API)* |

---

## 2. Live Staging Frontend & Cross-Origin Browser E2E Status

- **Live Deployed Staging Browser E2E (Vercel <-> Render):** **BLOCKED** — No unauthenticated staging frontend deployment pointing to `https://vouch-u3u7.onrender.com` is accessible (`staging.srilekh.com` has no DNS record; `vouch-git-fix-stage4-12-day6-remediation-trail-blazer.vercel.app` is gated behind Vercel SSO Login and not in Render `CORS_ALLOWED_ORIGINS`; `vouch-pi-one.vercel.app` targets production `main` and was intentionally excluded).
- **Post-Commit Local Backend Suite (`python manage.py test apps.accounts.tests apps.accounts.tests_auth_otp apps.accounts.tests_stage1_2_auth_cookies apps.companies.tests apps.audit.tests --verbosity=1`):** **PASS** (`34/34` tests passed in `47.223s`, exit `0`, isolated SQLite test DB).
- **Previously Reported Stage 1.2 Local Browser E2E (Playwright `msedge` + local `runserver` + local `next start`):** Documented separately in [`STAGE_1_2_TARGETED_REGRESSION_RESULTS.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_1_2_TARGETED_REGRESSION_RESULTS.md) — **NOT counted as live deployed staging browser E2E**.

---

## 3. Finding Raised During Staging Certification

- **Staging Outbound SMTP Blocking (`POST /api/v1/auth/password/reset/request/`):** Calling `/api/v1/auth/password/reset/request/` for an active user on Render staging (`vouch-u3u7.onrender.com`) causes the synchronous Django/SMTP request handler to block until TCP/socket timeout. Recommend configuring non-blocking/timeout-bounded email delivery or staging email backend (`console`/`locmem` or async Celery once Redis/Celery workers are provisioned) for staging password-reset verification.
