# SRI LEKH — STAGE 1.2: AUTHENTICATION REMEDIATION REPORT

**Date:** 2026-11-12  
**Branch:** `fix/stage4-12-day6-remediation`  
**Gap Addressed:** **P0 — JavaScript-readable authentication tokens** (while preserving Capacitor native compatibility, refresh rotation, and offline workflows)

---

## 1. Existing Implementation & Token Exposure Before Stage 1.2

Prior to Stage 1.2:
- [`frontend/src/utils/auth.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/auth.ts) wrote `access_token` and `refresh_token` directly to JavaScript-readable cookies (`js-cookie` `Cookies.set`) **and** duplicated both JWTs inside `localStorage` (`vouch_access_token`, `vouch_refresh_token`) plus Capacitor `Preferences`.
- [`frontend/src/components/NotificationBell.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/NotificationBell.tsx) also attempted `localStorage.getItem("access_token")`.
- [`config/settings.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/settings.py) configured DRF strictly with `JWTAuthentication` (Bearer header only) and set `CSRF_COOKIE_HTTPONLY = True`, preventing standard SPA header submission for cookie-backed sessions.
- Roughly 50 frontend components/pages checked `getAccessToken()` or passed `Authorization: Bearer ${token}` manually on raw `axios` calls, and stateless JWT access tokens remained valid for up to 30 minutes even after logout.

---

## 2. Changes Made

### Backend (`apps/accounts/`, `apps/accounting/claim_views.py`, `config/settings.py`)
1. **Per-User Immediate Token Revocation (`User.token_version`):**
   - Added `token_version = models.PositiveIntegerField(default=0)` to [`User`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/models.py#L41) via [`0007_user_token_version.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/migrations/0007_user_token_version.py).
   - Embedded `token_version` inside access and refresh claims in [`CustomTokenObtainPairSerializer`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/serializers.py), [`CustomTokenRefreshSerializer`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/serializers.py), `RegisterCompleteView`, and [`ClaimRegisterView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/claim_views.py).
   - [`revoke_user_tokens`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/cookies.py) atomically increments `User.token_version` **and** blacklists outstanding refresh tokens on both `POST /api/v1/auth/logout/` and `PasswordResetConfirmView`.
2. **`HttpOnly` Cookie Authentication & Origin-Aware Cookie Policy ([`cookies.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/cookies.py), [`authentication.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/authentication.py)):**
   - Replaced DRF `DEFAULT_AUTHENTICATION_CLASSES` in [`config/settings.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/settings.py) with [`CookieJWTAuthentication`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/authentication.py).
   - Login, refresh, registration completion, and claim-registration endpoints attach:
     - `srilekh_access`: `HttpOnly=True`, `Path=/`, `max_age=1800s`
     - `srilekh_refresh`: `HttpOnly=True`, `Path=/api/v1/auth/`, `max_age=7d`
   - When `X-Client-Type: web` is sent (browser sessions), [`attach_auth_cookies`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/cookies.py) **strips `access` and `refresh` strings from the JSON response body**, returning non-secret session metadata (`auth_mode: "cookie"`, `csrf_token`, `expires_at`, `refresh_expires_at`, `user`) so zero JWTs enter browser JavaScript memory or storage.
   - `ThrottledTokenRefreshView` reads `srilekh_refresh` from `HttpOnly` cookies (when omitted from JSON), enforces CSRF on cookie-backed refreshes, preserves `ROTATE_REFRESH_TOKENS=True` & `BLACKLIST_AFTER_ROTATION=True`, and rejects rotated/revoked tokens.
   - Added [`CsrfCookieView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py) (`GET /api/v1/auth/csrf/`) and [`LogoutView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py) (`POST /api/v1/auth/logout/`).

### Frontend ([`auth.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/auth.ts), [`api.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/api.ts), Callers)
1. **Browser Token Storage Eliminated:**
   - [`setAuthenticatedSession`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/auth.ts) no longer calls `Cookies.set` or writes JWTs into `localStorage` in browsers; [`purgeLegacyJsTokens`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/auth.ts) removes any prior `access_token`, `refresh_token`, `vouch_access_token`, or `vouch_refresh_token` entries.
   - `getAccessToken()` and `getRefreshToken()` return `undefined` in browser mode. Only non-secret expiry/user-ID metadata (`vouch_session_meta`) and UI display profile (`vouch_user`) are kept locally so offline UI gating remains functional.
2. **Global Axios, `apiFetch`, & CSRF Bridge ([`api.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/api.ts)):**
   - Configured both `api` and global `axios` with `withCredentials: true`, `X-Client-Type: web|capacitor`, automatic `X-CSRFToken` injection on `POST`/`PUT`/`PATCH`/`DELETE` (bootstrapped in memory via `GET /api/v1/auth/csrf/` when needed), defensive stripping of `Bearer undefined`/`Bearer null` or browser `Bearer` headers, shared-mutex 401 cookie refresh, and `AbortSignal` hookup.
   - Added `apiFetch()` for `fetch()` callers (`sync-worker.ts`, `clientOperationManager.ts`, `clientKeyManager.ts`).
   - Updated [`login/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/login/page.tsx), [`register/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/register/page.tsx), [`claim/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/claim/page.tsx), [`NotificationBell.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/NotificationBell.tsx), [`BulkBrandDiscountModal.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/modals/BulkBrandDiscountModal.tsx), repositories (`ledgers`, `products`, `vouchers`, `bank-transactions`), `lib/api/gst.ts`, and pages checking `if (token)` to rely on `isAuthenticated()` and cookie/CSRF auth cleanly.

---

## 3. Cookie & CSRF Configuration Details

- **`Secure` Flag:** `AUTH_COOKIE_SECURE` defaults to `not DEBUG` (also auto-enabled when `request.is_secure()`).
- **Origin-Aware `SameSite` (`resolve_cookie_samesite`):**
  - **Same-site origins** (`https://srilekh.com` <-> `https://api.srilekh.com`, `http://localhost:3000` <-> `http://localhost:8000`): uses **`SameSite=Lax`** (first-party cookie behavior without requiring third-party cookies).
  - **Cross-site origins** (`https://vouch-pi-one.vercel.app` <-> `https://vouch-api-752s.onrender.com`): automatically uses **`SameSite=None`** with `Secure=True` (configurable via `AUTH_COOKIE_SAMESITE`).
- **CSRF Enforcement:**
  - `CookieJWTAuthentication` calls [`enforce_cookie_csrf`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/cookies.py) (`CSRFCheck`) on all non-safe (`POST`/`PUT`/`PATCH`/`DELETE`) cookie-authenticated requests.
  - `ThrottledTokenRefreshView` enforces CSRF when refreshing via `srilekh_refresh` cookie, and `LogoutView` enforces CSRF when `srilekh_access`/`srilekh_refresh` cookies are present.
  - `CSRF_COOKIE_HTTPONLY = False` and `CSRF_COOKIE_SAMESITE = 'None' if not DEBUG else 'Lax'` in `config/settings.py`; JSON `csrf_token` is returned on `/csrf/`, `/login/`, `/refresh/`, `/register/complete/`, `/claim-register/` so cross-origin SPAs can attach `X-CSRFToken` without needing `document.cookie` across origins.

---

## 4. Capacitor / Native Compatibility & Storage Evaluation

- **Runtime Separation:** `isCapacitorNative()` activates only when `window.Capacitor?.isNativePlatform?.()` is true. Native requests send `X-Client-Type: capacitor` and continue using `Authorization: Bearer <access>` without cookie CSRF failures (`credentials: 'omit'`).
- **Storage Evaluation (`@capacitor/preferences` vs Native Keychain/Keystore):**
  - Inspected [`frontend/package.json`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/package.json) and [`frontend/capacitor.config.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/capacitor.config.ts). Note `capacitor.config.ts` currently points `server.url` to `https://srilekh.com/dashboard` and bundles `@capacitor/preferences` (`^8.0.1`), with **no** Capacitor Keychain/Keystore plugin installed.
  - Stage 1.2 isolates native tokens strictly inside `@capacitor/preferences` (in memory during execution, hydrated via `hydrateNativeTokens()` and wiped on `removeTokens()`), **not** duplicating them into web `document.cookie` or web `localStorage`.
  - **Honest Risk Caveat:** `@capacitor/preferences` stores values in OS app-sandboxed Android `SharedPreferences` / iOS `UserDefaults`, which are **not** hardware-backed Android Keystore / iOS Keychain encryption. On rooted/jailbroken devices, OS app-data inspection could read `Preferences`.

---

## 5. Remaining Authentication Risks

1. **Native Hardware Keystore:** Migrating Capacitor token persistence from `@capacitor/preferences` to an audited Keychain/EncryptedSharedPreferences plugin (`capacitor-secure-storage-plugin` or `@capawesome/capacitor-secure-preferences`) remains a separate native mobile hardening task.
2. **Browser Support for Third-Party Cookies on Preview Hosts:** While primary domain `srilekh.com` <-> `api.srilekh.com` operates first-party (`SameSite=Lax`), preview deployments bridging separate domains (`*.vercel.app` -> `*.onrender.com`) rely on `SameSite=None; Secure` and can be blocked if a user disables all third-party cookies in strict browser modes unless hosted under a shared domain.
3. **Cold Start Native Sync Helper (`hydrateNativeTokens`):** Native mobile background listeners should invoke `await ensureValidSession()` (which already awaits `hydrateNativeTokens()`) before issuing raw Bearer requests.
4. **Stage 1.1 Copy Sync:** Section 7 & Section 9 of [`privacy-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/privacy-policy/page.tsx) (frozen under Stage 1.1 policy scope) still note non-`HttpOnly` JS tokens and should be updated during Stage 1.1 owner pre-publication sign-off.
