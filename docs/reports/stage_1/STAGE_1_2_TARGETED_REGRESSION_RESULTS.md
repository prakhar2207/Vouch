# SRI LEKH — STAGE 1.2: TARGETED REGRESSION RESULTS

**Verification Date:** 2026-11-12  
**Branch:** `fix/stage4-12-day6-remediation`  
**Database Safety:** All backend Django tests ran in isolated SQLite test databases (`'file:memorydb_default?mode=memory&cache=shared'` or temporary scratch SQLite file); zero production/staging records or protected tenant accounts were modified.

---

## 1. Targeted Tests Executed & Results

| Suite / Command | Scope | Pass / Total | Duration | Exit Code | Key Evidence Observed |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `python manage.py test apps.accounts.tests apps.accounts.tests_auth_otp apps.accounts.tests_stage1_2_auth_cookies apps.companies.tests apps.audit.tests --verbosity=1` | Backend auth, OTP, HttpOnly cookies, CSRF, refresh rotation, `token_version` revocation, Capacitor Bearer compatibility, company RBAC, audit integrity | **34 / 34 passed** (0 fail, 0 skip) | `15.379s` | `0` | Verified `srilekh_access` & `srilekh_refresh` `HttpOnly` attributes; `X-Client-Type: web` strips JSON `access`/`refresh`; missing CSRF returns `403`, valid `X-CSRFToken` returns `200`; replaying rotated refresh token returns `401`; logout + `token_version` bump rejects stale Bearer & cookie tokens (`401`); Capacitor `Authorization: Bearer` PATCH succeeds without CSRF. |
| `python manage.py makemigrations --check --dry-run` | Django migration consistency for `accounts.0007_user_token_version` | **Consistent** | `< 2s` | `0` | Output: `No changes detected`. |
| `npm test` (`frontend/`) | Contact form validation (`6`), SW cache isolation (`3`), Stage 4.12 offline sync (`5`), Stage 1.2 offline auth/privacy (`5`), Role capabilities (`4`), Auth utils (`3`) | **28 / 28 passed** (0 fail, 0 skip) | `951ms` | `0` | Verified browser mode leaves zero JWTs in `localStorage`/`document.cookie` (`getAccessToken() === undefined`); Capacitor `Preferences` mode works & wipes on logout; User B sees `0` pending count for User A and pushes `0` records; logout aborts in-flight `fetch` (`AbortSignal.aborted === true`) and discards late response (`0` rows written); secure shared-device logout wipes `VouchOfflineDB`, `VouchSecurityVault`, and `vouch_device_id`/`vouch_ed25519_*`. |
| `npx tsc --noEmit` (`frontend/`) | Full frontend TypeScript type-check across Stage 1.2 edits | **0 errors** | ~12s | `0` | `TSC_EXIT=0` after final repository type fixes. |
| `npx eslint src/utils/auth.ts src/utils/api.ts src/lib/sync/stage1_2_offline_auth_privacy.test.ts src/components/modals/LogoutConfirmModal.tsx` | New/rewritten core Stage 1.2 frontend modules | **0 errors, 0 warnings** | ~5s | `0` | `ESLINT_STAGE12_EXIT=0`. *(Pre-existing `: any` lint debt in untouched lines of `clientKeyManager.ts` / `clientOperationManager.ts` flagged separately as 9 errors, 3 warnings when checked alongside untouched files.)* |
| `npm run build` (`frontend/`) | Webpack production build + Serwist Service Worker bundle (`56/56` static pages) | **Succeeded** | ~15s | `0` | `BUILD_EXIT=0`. Stage 1.1 `/sw.js`, `/robots.txt`, `/sitemap.xml`, and all 5 public compliance pages preserved cleanly. |
| Live E2E (`verify_stage1_2_browser_e2e.py`, Playwright `msedge` + Django `runserver` + Next.js `next start`) | Real headless Microsoft Edge browser session lifecycle (`/login` -> `/dashboard` -> CSRF write -> `/refresh/` -> `<LogoutConfirmModal />` -> post-logout `/me/` `401` + Stage 1.1 public routes `200`) | **All assertions passed** | ~25s | `0` | `srilekh_access` `httpOnly=true`, `sameSite=Lax`, `path=/`; `documentCookie` contained only `csrftoken=...`; `localStorage` & `sessionStorage` had zero `eyJ` JWTs; un-headered `PATCH /me/` returned `403`, with `X-CSRFToken` returned `200`; `POST /refresh/` returned `200` with `refreshReturnedAccess=false`; `<LogoutConfirmModal />` opened and signed out cleanly clearing cookies & returning `401` on subsequent `/me/`. |

---

## 2. Targeted Requirement Coverage & Evidence Summary

### Authentication Matrix
- **Browser refresh cookie is not JavaScript-readable:** **PASS** — Verified in Django `tests_stage1_2_auth_cookies` (`refresh_cookie['httponly'] == True`, `path='/api/v1/auth/'`) and proven functional in live Edge E2E where `POST /api/v1/auth/refresh/` succeeded (`200`) with `{}` body while `document.cookie` contained zero JWTs. *(Note: Edge `context.cookies(["http://localhost:8000"])` path-filtering did not list path-scoped `/api/v1/auth/` cookie at `/` root query, confirming narrow path scoping.)*
- **Access-token refresh works & rotation works:** **PASS** — Verified in Django unit tests (`test_cookie_refresh_rotation_and_replay_rejection`) and live Edge E2E (`refreshStatus: 200`, zero raw JWTs in JSON).
- **Revoked refresh & access tokens rejected (including stale tabs):** **PASS** — Verified in `test_logout_revokes_cookies_refresh_and_stale_tab_access_token` (`401` on prior Bearer `PATCH /me/`, `401` on prior `srilekh_access` cookie `GET /me/`, `401` on prior `refresh` replay) and live Edge E2E (`post_logout_me_status: 401`).
- **CSRF protection works for cookie-authenticated writes:** **PASS** — Verified `403` without `X-CSRFToken` and `200` with `X-CSRFToken` in both Django `APIClient(enforce_csrf_checks=True)` and live Edge browser E2E (`blockedPatchStatus: 403`, `allowedPatchStatus: 200`).
- **Capacitor authentication remains compatible:** **PASS** — Verified in `test_capacitor_native_bearer_auth_compatible` and `stage1_2_offline_auth_privacy.test.ts` Test 2.

### Offline Privacy Matrix
- **User A pending records unreadable / unsyncable by User B:** **PASS** — Verified in `offline-sync.test.ts` Test 4 & `stage1_2_offline_auth_privacy.test.ts` Test 3 (`pendingMutationsCount: 0` for User B, `networkCalls: 0`).
- **Company A pending records blocked under Company B:** **PASS** — Verified in `offline-sync.test.ts` Test 3 (`pushedUrls.length === 0`).
- **Logout stops background sync & aborts/discards in-flight writes:** **PASS** — Verified in `stage1_2_offline_auth_privacy.test.ts` Test 4 (`AbortSignal.aborted === true`, `0` records written from late server response, `callsAfterLogout === 0`).
- **Ordinary logout preserves pending work; Secure shared-device logout wipes sensitive local data:** **PASS** — Verified in `stage1_2_offline_auth_privacy.test.ts` Tests 3 & 5 plus live Edge verification of `LogoutConfirmModal`.

---

## 3. Failures & Tests Intentionally Not Run

- **Failures Observed:** **None** in any Stage 1.2 targeted backend, frontend, build, or live Edge E2E run after final edits. *(One pre-existing backend inventory thread-concurrency test error observed during Stage 1.1 under SQLite `test_db.sqlite3` was already known to be a SQLite lock limitation unrelated to auth/offline changes.)*
- **Intentionally Not Run (Per Stage 1.2 Non-Duplication Boundary):**
  - Full Stage 4.15 accounting/inventory/GST/Redis/Celery/PG-restore/7-day soak suites (unchanged by Stage 1.2; PostgreSQL-backed staging infrastructure was not touched).
  - Real physical Android/iOS Capacitor native binary build (`npx cap build` / physical WebView device test) — Capacitor behavior was verified via backend `X-Client-Type: capacitor` tests and mocked JS `Capacitor.Plugins.Preferences` unit tests, **not** on a physical Android/iOS device.
  - Cross-origin live browser run between separate production domains (`vercel.app` <-> `onrender.com`) — verified via unit `resolve_cookie_samesite` tests (`SameSite=None; Secure`) and local same-site Edge E2E (`SameSite=Lax`), **not** deployed live to production.
