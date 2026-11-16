# SRI LEKH — STAGE 1.2.5 NATIVE, DEPENDENCY & APPLICATION SECURITY REPORT

**Assessment Date:** 2026-11-12  
**Branch / Commit:** `feat/google-play-launch-readiness` @ `c160fca0`  
**Overall Gate Verdict (Gate C — Security & Privacy):** **CONDITIONAL PASS** *(All automated PyPI CVEs remediated & CI `pip-audit` clean; 0 prod npm vulns; PG 18 auth/deletion/upload/WebCrypto suites verified; native Android Keystore token upgrade & physical WebView runtime checks remain pending hardware)*

---

## 1. Python PyPI CVE Audit & Remediation (Stage 1.2.5 Fix)

1. **Initial Baseline Audit (`https://api.osv.dev/v1/querybatch` against `requirements.txt`):**
   - Flagged 3 packages with public advisories on older installed/floor versions:
     - `djangorestframework==3.15.2` (7 advisories)
     - `pillow==12.3.0` (60 advisories in query window)
     - `pypdf==6.15.0` (40 advisories)
2. **Stage 1.2.5 Remediation Applied ([`requirements.txt`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/requirements.txt#L1-L15)):**
   - Upgraded & pinned minimum floors matching `.python-version` (`3.12.8`):
     - `djangorestframework>=3.18.3` (installed `3.18.3`)
     - `pillow>=13.0.0` (installed `13.0.0`)
     - `pypdf>=7.0.1` (installed `7.0.1`)
3. **Post-Upgrade Independent Verification:**
   - Local OSV `querybatch` re-scan across `21` checked `requirements.txt` packages: **`REMAINING_VULNS: []`** (`0`).
   - GitHub Actions Run `43259891989` (Job `131328026519`, Step 6 `pip-audit -r requirements.txt --strict --progress-spinner off` on `c160fca0`): **`No known vulnerabilities found`** (`completed success`).

---

## 2. JavaScript Dependency & Upload / WebCrypto Security

- **Frontend Production Audit (`cd frontend && npm audit --omit=dev` locally & in CI Job `131328027030`):** **`found 0 vulnerabilities`** (`11` moderate advisories remain confined strictly to devDependencies).
- **Frontend Security & Offline Crypto Tests (`45 / 45` PASS locally & in CI):**
  - `Spreadsheet Parser (safe xlsx replacement & CSV hardening)` (`9/9`): RFC-4180 CSV, `.xlsx` via `read-excel-file`, path traversal, MIME spoofing, ZIP-bomb decompressed ratio ceiling, 15 MB / 50,000-row DoS guard, negative price rejection, formula injection neutralization.
  - `Stage 1.2: Browser Token Elimination, Native Compatibility & Offline Privacy Closure` (`9/9`): Zero JWTs in `localStorage`/`document.cookie`, cross-user/cross-tenant outbox isolation, Secure Shared-Device Logout full wipe, non-extractable WebCrypto `AES-GCM-256` across all 13 offline IndexedDB tables, key rotation, tamper/AAD verification.
- **Backend Security, Cookie Auth, Upload & Deletion Tests on PostgreSQL 18:**
  - Cloud CI PG 18 (`Run #43259891989`, Step 7): **26 / 26 PASSED (`OK`, 14.287s)** covering `tests_stage1_2_auth_cookies`, `tests_play_launch_account_deletion`, `tests_upload_security`, `apps.audit.tests`, and `apps.common.tests_disaster_recovery`.
  - Neon PostgreSQL 18.6 (`test_neondb_staging`): Verified post-edit (**36 / 36 PASSED**, including `tests_play_launch_account_deletion` multi-thread `200+409` delete race & `tests_upload_security`).
  - Live Render Staging (`https://vouch-u3u7.onrender.com`): Verified `400 'Spreadsheet archive entry exceeds 50MB decompressed limit.'` on live 52 MB ZIP-bomb `.xlsx` upload + `200 COMPLETED` live self-service deletion + immediate token revocation (`401`).

---

## 3. Native Android Network & Token Storage Posture

- **Transport Security:** [`capacitor.config.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/capacitor.config.ts#L7-L17) enforces `cleartext: false`, `androidScheme: 'https'`; [`AndroidManifest.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/AndroidManifest.xml#L5-L7) enforces `allowBackup="false"`, `usesCleartextTraffic="false"`, and [`network_security_config.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/res/xml/network_security_config.xml#L1-L8) restricts trust anchors to system CAs without cleartext traffic.
- **Residual Caveat (`OA-11`):** Capacitor native mode persists JWT bearer tokens in `@capacitor/preferences` (application sandbox `SharedPreferences`, not Android Keystore `EncryptedSharedPreferences`). This behavior is accurately disclosed in the updated privacy policy on `feat/google-play-launch-readiness`; upgrading to Keystore-backed native storage remains a recommended hardening enhancement post-hardware setup.
