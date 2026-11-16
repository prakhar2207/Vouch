# SRI LEKH — STAGE 1.2: FINAL ACCEPTANCE REPORT

**Date:** 2026-11-12  
**Branch:** `fix/stage4-12-day6-remediation`  
**Audit & Remediation Scope:** Authentication & Offline Privacy Gap Closure (P0 JWT JS Exposure + P1 Post-Logout Offline Privacy + `VouchSecurityVault` Encryption Assessment).

---

## 1. Remediation Summary

1. **Eliminated Browser JWT Storage Exposure (P0):**
   - Migrated browser authentication from `document.cookie` (`js-cookie`) and `localStorage` (`vouch_access_token` / `vouch_refresh_token`) to server-issued **`HttpOnly`, `Secure` (on HTTPS / non-`DEBUG`) cookies** (`srilekh_access` on `/`, `srilekh_refresh` on `/api/v1/auth/`), origin-aware **`SameSite`** policy (`Lax` for first-party/same-site origins like `srilekh.com` <-> `api.srilekh.com`; `None; Secure` for cross-site hosting), and **omission of raw JWTs from JSON responses for `X-Client-Type: web` browser clients**.
   - Enabled **CSRF enforcement** (`enforce_cookie_csrf` via Django `CSRFCheck` + `GET /api/v1/auth/csrf/` + automatic frontend `X-CSRFToken` injection) on all cookie-authenticated writes, refreshes, and logouts.
   - Added atomic **`User.token_version` revocation** paired with refresh token blacklisting on `POST /api/v1/auth/logout/` and password resets so stale tabs and previously issued access/refresh tokens fail immediately (`401`).
   - Preserved **Capacitor native** authentication separately (`X-Client-Type: capacitor`, stored in `@capacitor/preferences` rather than web storage).

2. **Closed Post-Logout Offline Privacy & Stale-Sync Risks (P1):**
   - Scoped `SyncRepository.getSyncStatus` and `hasPendingOfflineTransactions` strictly by `userId` and `companyId` so User B never sees or pushes User A's queued counts/records.
   - Added monotonic `authEpoch`, shared `AbortController`, and post-response session/tenant verification across `sync-worker.ts`, `ClientOperationManager`, and data repositories (`ledgers`, `products`, `vouchers`, `bank-transactions`) so logging out or switching companies immediately cancels sync and discards late-arriving responses without writing to IndexedDB.
   - Added multi-tab logout coordination (`BroadcastChannel` + `storage` fallback) so stale tabs abort active work, clear local session/forecast caches, and return to `/login`.
   - Implemented [`LogoutConfirmModal.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/modals/LogoutConfirmModal.tsx) distinguishing **Standard Logout** (preserves unsynchronized outbox safely locked to `userId`/`companyId` after clearing caches) from **Secure Shared-Device Logout** (explicit pending-record warning + confirmation checkbox, closing and deleting `VouchOfflineDB`, `VouchSecurityVault`, all `vouch_*` storage keys, and Service Worker caches).

3. **Assessed Client Encryption (`VouchSecurityVault` & `VouchOfflineDB`):**
   - Confirmed `VouchSecurityVault` holds a non-extractable Ed25519 operation-signing key (integrity custody per browser profile), whereas all financial tables in `VouchOfflineDB` remain plaintext at rest (not rebuilt in this stage).

---

## 2. Acceptance Criteria Evaluation

| Requirement | Status | Evidence / Notes |
| :--- | :--- | :--- |
| Browser JWT exposure (no unnecessary JS-readable token copies) | **PASS** | `X-Client-Type: web` omits JWTs from JSON; Edge DOM verified 0 `eyJ` JWTs in `localStorage`, `sessionStorage`, and `document.cookie`. |
| HttpOnly cookie verified in browser | **PASS** | Verified in live Edge `context.cookies()` (`srilekh_access` `httpOnly: true`) + live cookie-only `/auth/refresh/` (`200`) + Django `tests_stage1_2_auth_cookies`. |
| CSRF verified for cookie-authenticated writes | **PASS** | Verified `403` without `X-CSRFToken` & `200` with `X-CSRFToken` in both Edge E2E and Django `APIClient(enforce_csrf_checks=True)`. |
| Refresh rotation | **PASS** | `ROTATE_REFRESH_TOKENS=True` & `BLACKLIST_AFTER_ROTATION=True` preserved; old rotated refresh token rejected (`401`). |
| Revocation (revoked sessions rejected) | **PASS** | Logout increments `User.token_version` + blacklists refresh tokens; subsequent cookie & Bearer attempts return `401`. |
| Native compatibility | **PARTIALLY VERIFIED** | Backend Bearer flow & mocked `Capacitor.Plugins.Preferences` tests pass; **not** executed on a physical Android/iOS device binary. |
| Offline ownership (user/company isolation) | **PASS** | Unit & sync tests (`28/28` pass) verify User A/B and Company A/B isolation across `outboxQueue`, `syncRepository`, and sync workers. |
| Logout stops background sync | **PASS** | `triggerFullSync`, `triggerOutboxSync`, `executeClientOutboxSync`, and `pullIncrementalChanges` abort via `AbortSignal` & exit cleanly on logout. |
| Tenant switching prevents cross-tenant replay | **PASS** | Strict positive `activeCompanyId` checks + epoch/company re-check before writes prevent cross-company replay. |
| Stale tabs cannot write after revocation | **PASS** | Server `User.token_version` (`401`) + client `BroadcastChannel`/`storage` logout listener & `AbortSignal`. *(Cross-tab JS `BroadcastChannel` behavior verified by code inspection & backend `401` token test rather than multi-tab Playwright runner.)* |
| Pending work (no silent deletion) | **PASS** | Standard logout preserves pending `QUEUED`/`IN_FLIGHT`/`FAILED` outbox rows isolated by `userId`/`companyId` and displays count in logout dialog. |
| Secure-device logout removes sensitive local data | **PASS** | Explicit confirmation wipes `VouchOfflineDB`, `VouchSecurityVault`, `vouch_*` storage keys, and SW caches cleanly. |
| Existing Stage 1.1 fixes preserved | **PASS** | Public pages, `/sw.js`, `/robots.txt`, `/sitemap.xml` built (`npm run build` `exit 0`) and returned HTTP 200 in Edge E2E. |
| Existing Stage 4.15 fixes preserved | **PASS** | Existing account, OTP (`21/21`), company & audit suites (`34/34` combined backend pass) remain green. |

---

## 3. Outstanding Risks & Compatibility Assessment

1. **Capacitor Hardware Keystore Gap:** `@capacitor/preferences` (`SharedPreferences` / `UserDefaults`) provides OS app-sandbox isolation rather than hardware Keychain/Keystore encryption. Tracked as a future native mobile plugin upgrade.
2. **IndexedDB Plaintext at Rest During Standard Logout:** On untrusted kiosk browsers, users must select **Secure Shared-Device Logout**; full AES-GCM encryption of `VouchOfflineDB` requires a future key-management & recovery design.
3. **Production Deployment Prerequisite (Database Migration):** Deploying Stage 1.2 backend code requires running `python manage.py migrate accounts` to apply `0007_user_token_version` before WSGI/worker boot.
4. **Cross-Site Cookie Dependency on Dual-Domain Previews:** Separate preview domains (`*.vercel.app` -> `*.onrender.com`) depend on `SameSite=None; Secure`, whereas same-site custom domain routing (`srilekh.com` <-> `api.srilekh.com`) uses first-party `SameSite=Lax; Secure`.
5. **Privacy Policy Text Sync (Stage 1.1):** `/privacy-policy` Sections 7 & 9 should be updated alongside Stage 1.1 owner sign-off to reflect that browser JWTs now reside in `HttpOnly` cookies.

---

## 4. Stage 1.2 Verdicts (Section 8)

| Domain | Verdict | Basis |
| :--- | :--- | :--- |
| **Browser authentication** | **PASS** | Real Edge + Django E2E (`HttpOnly` cookies, `/login`, `/dashboard`, `/refresh/`, `/logout/`) & Django cookie test suite passed. |
| **Token storage** | **CONDITIONAL PASS** | Zero JWTs in browser JS cookies or `localStorage`/`sessionStorage`; Capacitor native isolation still uses OS-sandboxed `@capacitor/preferences` pending hardware Keychain/Keystore upgrade. |
| **Session revocation** | **PASS** | Atomic `User.token_version` + SimpleJWT blacklist immediately invalidate both refresh and stale access tokens across tabs (`401`). |
| **CSRF protection** | **PASS** | Double-submit `X-CSRFToken` enforced on all cookie-authenticated writes, refreshes, and logouts (`403` without token, `200` with token). |
| **Capacitor compatibility** | **CONDITIONAL PASS** | Bearer JSON mode & mocked Preferences tests pass; physical Android/iOS WebView E2E not executed in this environment. |
| **Offline privacy** | **PASS** | Strict `userId`/`companyId` scoping across sync workers, repositories, and `SyncStatusBadge`; in-flight pulls/pushes abort and discard on logout or tenant switch. |
| **Shared-device logout** | **PASS** | Explicit two-mode `LogoutConfirmModal` with pending-record warning & checkbox confirmation deletes `VouchOfflineDB`, `VouchSecurityVault`, storage keys, and SW caches. |
| **Encryption coverage** | **CONDITIONAL PASS** | Audited accurately: `VouchSecurityVault` protects non-extractable Ed25519 signing keys, while `VouchOfflineDB` records remain plaintext in IndexedDB (future encryption task documented with severity & recovery rationale). |

### Overall Stage 1.2 Verdict: **CONDITIONAL PASS**

- **Rationale:** Both confirmed P0 (browser JS-readable JWT exposure) and P1 (post-logout offline retention & stale sync) risks are closed and verified with automated backend tests (`34/34`), frontend unit/offline tests (`28/28`), production build (`npm run build`), and real headless Edge E2E verification. Overall classification is **CONDITIONAL PASS** due strictly to: (a) physical Capacitor device build testing not run locally, (b) Capacitor `@capacitor/preferences` not yet hardware-keystore-backed, and (c) plaintext `VouchOfflineDB` storage when users opt for Standard Logout instead of Secure Shared-Device Logout.
- **Release Note:** Overall production readiness remains independently governed by **Stage 4.15** operational/backend gates and **Stage 1.1** owner/legal publication gates. Ensure `python manage.py migrate accounts` is applied on staging prior to smoke testing this branch.
