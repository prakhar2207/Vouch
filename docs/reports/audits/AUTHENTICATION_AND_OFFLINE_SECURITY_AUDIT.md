# SRI LEKH — AUTHENTICATION & OFFLINE SECURITY AUDIT

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Live Staging Target Audited:** `https://vouch-u3u7.onrender.com` (`f8578a88`, `neondb_staging`)

---

## 1. Authentication Security Evaluation

| Control | Implementation Audited | Verification & Status |
| :--- | :--- | :--- |
| **Zero JS-Readable Browser JWTs** | [`apps/accounts/cookies.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/cookies.py) & [`frontend/src/utils/auth.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/auth.ts) omit `access`/`refresh` from JSON for `X-Client-Type: web` and return `undefined` from `getAccessToken()`/`getRefreshToken()` on browsers. | **Verified PASS** (Live Render + Edge DOM check `0` `eyJ` in `localStorage`/`document.cookie` + `28/28` frontend tests). |
| **HttpOnly, Secure & Origin-Aware SameSite Cookies** | `srilekh_access` (`Path=/`, `Max-Age=1800`) and `srilekh_refresh` (`Path=/api/v1/auth/`, `Max-Age=604800`) always set `HttpOnly`, `Secure` (non-`DEBUG`), and `SameSite=Lax` (same-site domains e.g. `srilekh.com` <-> `api.srilekh.com`) or `SameSite=None; Secure` (cross-site e.g. `*.vercel.app` -> `*.onrender.com`). | **Verified PASS** (Live Render HTTPS observed `HttpOnly; SameSite=None; Secure`). |
| **CSRF Enforcement on Unsafe Cookie Requests** | `enforce_cookie_csrf` (`CSRFCheck`) invoked on unsafe methods in `CookieJWTAuthentication`, `ThrottledTokenRefreshView`, and `LogoutView`. Frontend [`api.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/api.ts) deduplicates `/api/v1/auth/csrf/` via `csrfBootstrapPromise` and sends `X-CSRFToken`. | **Verified PASS** (Live Render `403` without header vs `200`/`201` with `X-CSRFToken` across `PATCH`, `POST`, `DELETE`). |
| **Refresh Token Rotation & Replay Rejection** | `ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True`. Replaying pre-rotation `srilekh_refresh` rejected with `401`. | **Verified PASS** (Live Render & Django tests). |
| **Concurrent Refresh Mutex & Logout Race Control** | [`api.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/api.ts) coordinates concurrent refreshes behind module-level `refreshPromise`, checks `getAuthEpoch() !== startEpoch` before writing session metadata (`setAuthenticatedSession`), and attaches `getAuthAbortSignal()` to API calls so logging out aborts & discards in-flight work. | **Verified PASS** *(Code audit + unit tests)*; deployed cross-origin UI stress test **BLOCKED** on staging frontend access. |
| **Immediate Revocation (`User.token_version`)** | Logout, password reset confirmation, and permanent account deletion increment `User.token_version` atomically (`F('token_version') + 1`) and blacklist outstanding refresh tokens. | **Verified PASS** (Live Render logout -> `401`; Django password-reset & deletion -> `401`). |
| **Password Reset Request SMTP Timeout Hardening** | Previously `EMAIL_TIMEOUT` was unset (`None`), causing live `POST /api/v1/auth/password/reset/request/` on Render to hang >45s on unreachable/blocked SMTP. Added `EMAIL_TIMEOUT = env.int('EMAIL_TIMEOUT', default=10)`, `PasswordResetEmailRateThrottle` (`5/hour` per email SHA-256), `idempotency_key`, and generic `200` exception guard. | **Verified PASS** *(Django timeout test `200` + `EmailDeliveryLog` `DELIVERY_UNKNOWN`)* / **BLOCKED** *(Live SMTP inbox delivery not testable without working staging SMTP relay)*. |

---

## 2. Capacitor Native Token Storage & Migration Assessment

- **Current State:** Capacitor WebView sends `X-Client-Type: capacitor` and persists tokens in `@capacitor/preferences` (`SharedPreferences` on Android / `UserDefaults` on iOS).
- **Hardening Applied:** `android:allowBackup="false"` in [`AndroidManifest.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/AndroidManifest.xml) closes ADB / Android Auto Backup extraction of `SharedPreferences`; server logout & password reset revoke Capacitor sessions via `token_version`.
- **Remaining Risk (`P1` / Hardware Keystore Gap):** `@capacitor/preferences` is app-sandboxed plaintext rather than Android Keystore-backed encrypted storage (`EncryptedSharedPreferences` / Keychain).
  - **Safe Future Migration Plan (Non-Lockout):** When adding a vetted Keystore plugin (e.g., `@capgo/capacitor-native-biometric` or Keystore-backed secure preferences) on an Android SDK build host:
    1. On startup in `hydrateNativeTokens()`, read first from Secure Keystore; if empty, migrate once from legacy `@capacitor/preferences` (`vouch_access_token`/`vouch_refresh_token`), write into Secure Keystore, and delete the legacy `@capacitor/preferences` keys.
    2. Do not claim hardware-backed confidentiality before compiling and testing on a physical Android device.

---

## 3. Offline Data Security (`VouchOfflineDB`, `VouchSecurityVault` & Service Worker)

- **What Is Stored Offline in IndexedDB ([`offlineDb.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/db/offlineDb.ts)):**
  - `syncedVouchers`, `syncedLedgers`, `syncedProducts`, `syncedBankTransactions`, `syncedPaymentAllocations`, `analyticsDaily`, `analyticsParty`, `masters`, `ocrCache` (read caches cleared on company switch & ordinary logout).
  - `vouchers`, `outboxQueue`, `operationLog`, `inboxQueue`, `syncCursors` (offline mutations/outbox tagged by `userId` & `companyId`).
  - `VouchSecurityVault`: non-extractable Ed25519 signing keys per device (`vouch_ed25519_*`).
- **Isolation & Logout Protections (`Verified PASS`):**
  - `28/28` frontend tests verify User B sees `0` pending items from User A and refuses cross-user / cross-company sync; logout bumps `authEpoch`, aborts in-flight pulls/pushes (`AbortSignal`), prevents stale response writes, clears read caches & Service Worker caches (`sw-cache-policy.ts`), and supports **Secure Shared-Device Logout** (`forceDestroyAll: true`) deleting `VouchOfflineDB` and `VouchSecurityVault`.
- **Plaintext-at-Rest Limitation (`P1` — Documented, Not Hacked Around):**
  - Financial records inside `VouchOfflineDB` remain **plaintext at rest** on disk under the browser/WebView profile.
  - **Safe Remediation Roadmap:** Derive/unwrap an AES-GCM `CryptoKey` per authenticated session (stored non-extractable in WebCrypto / Keystore rather than `localStorage`), encrypt sensitive IndexedDB payload fields (`payload`, `partyName`, balances, `ocrCache`), keep lookup indexes (`id`, `companyId`, `userId`, `status`) separate, and require explicit re-auth unlock after offline restart before decrypting cached drafts so synchronization never breaks or corrupts queued entries.
