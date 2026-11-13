# SRI LEKH — FINAL STAGE 1.2.3 RELEASE ACCEPTANCE & SIX-GATE VERDICT

**Assessment Date:** 2026-11-12  
**Active Feature Branch:** `feat/google-play-launch-readiness`  
**Protected Production Environment (Untouched):** `https://vouch-api-752s.onrender.com`, `neondb`, `main`, tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`).  
**Isolated Staging Identity Verified:** `https://vouch-u3u7.onrender.com` (`f8578a88`), `neondb_staging` (`6f4741bdaaf4`, `PostgreSQL 18.6`, `146` migrations, `0` prod tenant rows).

---

## 1. Six-Gate Release Acceptance Decision Matrix

### Gate A — Google Play Policy Readiness: **BLOCKED / OWNER ACTION REQUIRED**
- **Verified Code Controls:** Free-download workspace companion model enforced in Android via `NativeCommercialGuard` / `NativeCommercialHide`; `/delete-account` portal and in-app `Settings -> Account Profile` flow hardened and verified; `/privacy-policy` updated for HttpOnly cookies, `@capacitor/preferences` custody disclosure, and `VouchOfflineDB` WebCrypto AES-GCM-256 encryption; `512x512` PNG app icon & mipmaps present; zero ad/tracking SDKs.
- **External Owner Blockers:** Feature branch is intentionally unpushed/undeployed to live `https://srilekh.com` (Play reviewers require live accessible `/delete-account` and `/privacy-policy`); missing `1024x500` Feature Graphic & screenshots; Owner must supply registered legal entity/address, Grievance Officer identity, exact statutory retention years, reviewer sandbox demo credentials, and complete Play Console Data Safety / Financial Features / Content Rating forms.

### Gate B — Android Technical Readiness: **BLOCKED / NOT TESTED (Build Host & Physical Device)**
- **Verified Source Hardening:** `com.srilekh.app` targeting SDK `36` (`minSdkVersion 24`); `allowBackup="false"`; `READ_MEDIA_IMAGES` & storage perms removed; `usesCleartextTraffic="false"` + `network_security_config.xml`; first-party-only `allowNavigation` synced via `npx cap sync android` (`exit 0`); `MainActivity.java` `setAllowFileAccess(false)` & `OnBackPressedCallback`.
- **Host / Hardware Blockers:** Build host lacks JDK (`java`, `javac`, `keytool`), Android SDK (`adb`), and owner upload keystore. `./gradlew bundleRelease`, R8 verification, signed `.aab` creation, and the entire physical Android device QA matrix were **NOT TESTED**.

### Gate C — Authentication & Offline Privacy: **PARTIALLY VERIFIED (Code Controls Implemented; Staging SMTP & Hardware Keystore Pending)**
- **Verified Closed in Stage 1.2.3:**
  - `npm audit --omit=dev` remediated from `13` (`2` critical, `9` high, `2` moderate) -> **`0` production runtime vulnerabilities**.
  - Sensitive financial payloads in `VouchOfflineDB` are encrypted at rest via non-extractable `AES-GCM-256` keys in `VouchSecurityVault` (`offlineCrypto.ts` + DBCore + pre-sealing wrappers; raw IndexedDB verified free of plaintext party names/amounts/UTRs/GSTINs in Node & Chromium WebCrypto E2E).
  - Hardened `AccountDeletionView` with PostgreSQL `select_for_update()` locking, `AccountDeletionRateThrottle`, and `AuthorizedDevice`/`Notification` cleanup (`7/7` OK on SQLite & Neon PG).
  - HttpOnly cookies, CSRF, refresh rotation, logout/reset/deletion `token_version` revocation, and `resolveApiBaseUrl` environment isolation all verified.
- **Residual Limitations:** Native Capacitor token storage uses OS-sandboxed `@capacitor/preferences` (not hardware Android Keystore; accurately disclosed); live staging password-reset email delivery requires valid SMTP/relay credentials (`EMAIL_TIMEOUT=10` fallback verified via tests).

### Gate D — Staging Integration: **BLOCKED (Frontend Hosting & Staging Branch Deployment)**
- **Verified:** Live Render staging `https://vouch-u3u7.onrender.com` (`neondb_staging`, `6f4741bdaaf4`) verified isolated, returning `401` on protected APIs, strict security headers (`nosniff`, `DENY`, HSTS, `strict-origin-when-cross-origin`), and untrusted-origin CORS rejection; built Next.js `16.4.6` + isolated Django Playwright Chromium Edge E2E passed (`HTTP 200` routes, native commercial guards, zero `eyJ` DOM leaks, Chromium non-extractable WebCrypto IDB, `/delete-account` flow).
- **Blocked:** Deployed `staging.srilekh.com` frontend pointing to `vouch-u3u7.onrender.com` with `feat/google-play-launch-readiness` deployed is not live yet; deployed multi-tab & live SMTP inbox browser E2E remain **BLOCKED**.

### Gate E — Backend Operational Readiness: **BLOCKED (External Paid Infrastructure)**
- Live Render `/api/v1/health/environment/` confirms `redis.status: "unreachable"`, `workers_online: 0`, `beat_schedule_active: false`.
- Host lacks native PostgreSQL CLI (`pg_dump`, `pg_restore`, `psql`) for `PGDMP` binary DR testing (`DatabaseBackupService` encrypted DR passed in automated tests).
- Seven-day continuous live operational soak has **NOT STARTED**.

### Gate F — Accounting & Inventory Integrity: **Verified PASS**
- Verified on Neon PostgreSQL 18.6 (`test_neondb_staging --keepdb`) and SQLite:
  - `apps.accounts.tests_play_launch_account_deletion` + `tests_stage1_2_auth_cookies` + `apps.accounting.tests_voucher_occ`: **26 / 26 PASSED (`OK`)** on Neon PostgreSQL 18.6.
  - `apps.inventory.tests_stage4_15_inventory` (including multi-threaded `select_for_update()` stock deduction & FIFO/reversals): **3 / 3 PASSED (`OK`)** on Neon PostgreSQL 18.6.
  - `apps.accounting.tests_stage4_12_remediation.Stage412DEF02ConcurrentRaceTests`: **1 / 1 PASSED (`OK`)** on Neon PostgreSQL 18.6.
  - `apps.accounting.tests_financial_reports` + `tests_statement_accounting` + `apps.audit.tests`: **18 / 18 PASSED (`OK`)** on SQLite.
  - `apps.common.tests_code_review_findings`: **12 / 12 PASSED (`OK`)** on SQLite.

---

## 2. Complete Stage 1.2.3 Verification Ledger

| Check / Command | Target | Observed Result |
| :--- | :--- | :--- |
| `python scripts/verify_staging_identity.py` | Neon `neondb_staging` | **PASS** (`146` migrations, `76` tables, `0` prod tenant rows) |
| `python manage.py makemigrations --check --dry-run` | `feat/google-play-launch-readiness` | **PASS** (`No changes detected`) |
| `cd frontend && npm audit --omit=dev` | Production runtime dependencies | **PASS** (`found 0 vulnerabilities`, down from `13`) |
| `cd frontend && npm test` | Node + `fake-indexeddb` + WebCrypto | **PASS** (`39 / 39` passed, `0` failures) |
| `cd frontend && npx tsc --noEmit` | Frontend TypeScript | **PASS** (`exit 0`) |
| `cd frontend && npm run build` | Webpack production + Serwist `/sw.js` | **PASS** (`57 / 57` routes + `/sw.js`) |
| `cd frontend && npx cap sync android` | Android Capacitor platform | **PASS** (`exit 0`, 5 plugins synced) |
| Playwright Chromium (`msedge`) Local E2E | Built `:3000` + isolated SQLite `:8000` | **PASS** (`E2E_CHROMIUM_ALL_CHECKS_PASSED`) |
| Core Django Auth, OTP, Staging Isolation, Notifications & Encrypted DR (`task-12986`) | Isolated SQLite | **PASS** (`74 / 74` passed, `0` errors) |
| Financial Reports, Statement Accounting & Audit Hash Chain (`task-13192`) | Isolated SQLite | **PASS** (`18 / 18` passed, `0` errors) |
| Code Review Audit Findings (Idempotency, MultiFernet, Trial Balance, Error Masking) | Isolated SQLite | **PASS** (`12 / 12` passed, `0` errors) |
| Account Deletion, Cookie Auth & Voucher OCC Races (`task-13073`) | Neon PostgreSQL 18.6 (`test_neondb_staging --keepdb`) | **PASS** (`26 / 26` passed, `0` errors) |
| Concurrent Inventory Stock Lock & FIFO (`task-13180`) | Neon PostgreSQL 18.6 (`test_neondb_staging --keepdb`) | **PASS** (`3 / 3` passed, `0` errors) |
| Concurrent Metadata PATCH OCC Race (`Stage412DEF02ConcurrentRaceTests`) | Neon PostgreSQL 18.6 (`test_neondb_staging --keepdb`) | **PASS** (`1 / 1` passed, `0` errors) |

---

## 3. OVERALL STAGE 1.2.3 RELEASE VERDICT

# **NO-GO**

**Rationale:** Every technical and security remediation achievable inside the repository without external paid infrastructure or missing host SDK/hardware has been implemented, verified, and proven green (`0` runtime npm vulnerabilities, AES-GCM-256 non-extractable WebCrypto encryption on `VouchOfflineDB`, row-locked `AccountDeletionView`, API URL environment isolation, Android cleartext/backup/navigation hardening, `39/39` frontend tests, `104/104` SQLite + `30/30` Neon PostgreSQL tests, Playwright Chromium E2E, and `0` TS errors). Release promotion remains **NO-GO** strictly due to the external/owner blockers in **Gates A, B, D, and E** (JDK/Android SDK + keystore build & physical device QA, Owner legal/Play Console assets & forms, approved deployment to `srilekh.com`/staging, managed Redis + Celery Worker/Beat + SMTP relay, native `pg_dump`/`pg_restore` binary certification, and the 7-day operational soak).
