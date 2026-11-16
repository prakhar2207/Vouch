# SRI LEKH — SECURITY PENETRATION & HARDENING VERIFICATION REPORT

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Scope:** Backend DRF APIs, Next.js Frontend CSP/Headers, Offline Storage Custody, Android Manifest/WebView Hardening, and Live Staging Security Probes (`https://vouch-u3u7.onrender.com`).

---

## 1. Security Test Matrix & Observed Results

| Threat Vector / Control | Test Method & Target | Observed Outcome |
| :--- | :--- | :--- |
| **JavaScript-Readable Auth Tokens (XSS Token Theft)** | Edge E2E + [`stage1_2_offline_auth_privacy.test.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/sync/stage1_2_offline_auth_privacy.test.ts) + [`tests_stage1_2_auth_cookies.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/tests_stage1_2_auth_cookies.py) | **PASS** — Browser login strips JSON `access`/`refresh`, sets `HttpOnly; Secure` cookies, zero `eyJ` tokens in `localStorage`, `sessionStorage`, or `document.cookie`. |
| **CSRF State-Changing Request Bypass** | Django `enforce_csrf_checks=True` against `PATCH /api/v1/auth/me/`, `POST /api/v1/auth/refresh/`, `POST /api/v1/auth/logout/`, `POST /api/v1/auth/account/delete-request/` | **PASS** — Missing/invalid `X-CSRFToken` rejected with `403 Forbidden`; valid token succeeds (`200`). |
| **JWT & Refresh Token Replay After Logout / Deletion / Reset** | [`tests_play_launch_account_deletion.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/tests_play_launch_account_deletion.py), [`tests_stage1_2_auth_cookies.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/tests_stage1_2_auth_cookies.py), Edge E2E | **PASS** — `revoke_user_tokens` increments `User.token_version` & blacklists outstanding refresh tokens; replayed cookie or Bearer access/refresh tokens return `401 Unauthorized`. |
| **Account Deletion Race & Re-Auth Bypass** | Hardened [`AccountDeletionView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py) (`select_for_update()`, `AccountDeletionRateThrottle`, password check inside lock) | **PASS** — Unauthenticated (`401`), bad password (`403`), bad phrase (`400`), multi-user sole owner (`409 OWNERSHIP_TRANSFER_REQUIRED`), replay/already-anonymized (`401`/`409`), PII wiped, `AuthorizedDevice` revoked. |
| **Cross-Tenant IDOR & RBAC Escalation** | [`tests_stage4_15_auth.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/tests_stage4_15_auth.py), `tests_voucher_occ.py`, live staging `/accounting/vouchers/`, `/notifications/logs/` | **PASS** — Unauthenticated returns `401`; unauthorized company IDs / non-privileged roles return `403 Forbidden` or `404 Not Found` with zero cross-tenant leakage. |
| **Malicious File Upload & Formula Injection** | [`spreadsheet-parser.test.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/import/spreadsheet-parser.test.ts) + `tests_play_launch_account_deletion.py` | **PASS** — `.exe` rejected (`400`) by universal import & GSTR-2B APIs; `.xls` legacy BIFF rejected in browser; >15 MB / >50,000-row payloads blocked; `=CMD()`, `+`, `-`, `@` neutralized on export. |
| **Offline Financial Storage Dumping** | [`offlineCrypto.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/db/offlineCrypto.ts) + Tests 6–7 in [`stage1_2_offline_auth_privacy.test.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/sync/stage1_2_offline_auth_privacy.test.ts) | **PASS** — Raw IndexedDB (`VouchOfflineDB`) stores `AES-GCM-v1` ciphertexts with AAD table binding; party names/amounts/GSTINs/UTRs absent on disk; WebCrypto key non-extractable (`exportKey` rejects). |
| **CSP, Security Headers & Untrusted CORS** | Live `https://vouch-u3u7.onrender.com` probes + Next.js [`next.config.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/next.config.ts) Chromium test | **PASS** — `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`, `Referrer-Policy: strict-origin-when-cross-origin`; untrusted `Origin` receives no `Access-Control-Allow-Origin`; Next.js CSP `connect-src` blocked non-whitelisted port `:8019` in Chromium Edge. |
| **SQLi / XSS Parameter Fuzz on Deletion Status & Android Transport** | Live staging probes + Android `AndroidManifest.xml` & `network_security_config.xml` | **PASS** — Malformed UUID (`SQLi_UUID`, `XSS_UUID`) safely rejected before DB query (`403`/`404` on current staging; `400` locally); Android enforces `usesCleartextTraffic="false"` & `allowBackup="false"`. |
| **Supply-Chain Runtime Dependencies** | `cd frontend && npm audit --omit=dev --json` | **PASS** — Reduced from `13` (`2` critical, `9` high, `2` moderate) to **`0` production runtime vulnerabilities**. |

---

## 2. Residual Accepted / Deferred Items

1. **Capacitor Native Token Custody:** Uses OS-sandboxed `@capacitor/preferences` (`allowBackup="false"`); hardware-backed Android Keystore requires JDK/Android SDK build host verification.
2. **Staging Render Unpushed Diff:** Live staging `https://vouch-u3u7.onrender.com` currently runs `f8578a88`; Stage 1.2.2/1.2.3 fixes (`/api/v1/auth/account/delete-request/`) reside on local `feat/google-play-launch-readiness` pending push/deployment approval.
