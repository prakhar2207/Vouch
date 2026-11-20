# SRI LEKH — STAGE 1.2.5 BASELINE & EXTERNAL BLOCKER CLOSURE MATRIX

**Assessment Date:** 2026-11-12  
**Active Branch:** `feat/google-play-launch-readiness` @ `c160fca0` *(progressed from Stage 1.2.3 `d27398c` -> Stage 1.2.4 `24af0d0` -> Stage 1.2.5 `6db09b3` -> `44fd015` -> `7c27c80` -> `3640c33` -> `c160fca`)*  
**Staging Branch Synchronized:** `fix/stage4-12-day6-remediation` fast-forwarded cleanly to `c160fca0` (`origin/fix/stage4-12-day6-remediation`)  
**Protected Production Environment (Untouched):** `main`, `https://vouch-api-752s.onrender.com`, DB `neondb`, protected tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`)

---

## 1. Stage 1.2.4 -> Stage 1.2.5 External Blocker Closure Matrix

| Stage 1.2.4 Blocker ID | Original Blocker | Stage 1.2.5 Autonomous Action | Current Stage 1.2.5 Status |
| :--- | :--- | :--- | :--- |
| **OA-12** | Continuous Python dependency CVE scanning (`pip-audit`) missing | Audited via `osv.dev`, upgraded `djangorestframework` (`3.15.2`->`3.18.3`), `pillow` (`12.3.0`->`13.0.0`), `pypdf` (`6.15.0`->`7.0.1`), added `--strict` `pip-audit` to [`.github/workflows/stage-verification-ci.yml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/.github/workflows/stage-verification-ci.yml) | **CLOSED** (`0` vulns OSV & CI `pip-audit` Run `43259891989`) |
| **OA-01 (Staging API)** | Render staging stuck at `f8578a88`; `/delete-request/` `404` | Fast-forwarded `fix/stage4-12-day6-remediation` (`44fd015` -> `c160fca`), executed live integration E2E on `https://vouch-u3u7.onrender.com` (`200 COMPLETED` delete + `400` 52MB ZIP bomb + `401` revoked token) | **CLOSED ON STAGING API** *(Production `main` / `www.srilekh.com` `404` remains blocked awaiting owner merge approval)* |
| **OA-03 (APK/AAB Compile)** | Android `.aab`/`.apk` build completely untested due to missing local JDK/SDK | Built Debug `.apk` & Unsigned Release `.aab` via JDK 21 + Android SDK 36 in Ubuntu Cloud CI (`Run #43259891989`, Job `131328027030`, `BUILD SUCCESSFUL in 2m 6s`, `534` tasks) | **COMPILATION CLOSED** *(Owner upload keystore signing & optional R8 remain OPEN)* |
| **OA-07 (Binary DR)** | Native PG 18 `pg_dump`/`pg_restore` unrun locally | Added PG 18 binary DR step to Cloud CI & discovered/fixed real `pg_restore` `TestCase` lockup + SQLite shared-cache lock in `backup_service.py` / `tests_disaster_recovery.py` / `tests_stage4_13_stabilization.py` | **CI BINARY DR CLOSED (`1`s RTO, `147/147` migrations)** *(Live `neondb_staging` populated snapshot DR remains OPEN)* |
| **OA-05 (Redis/Celery CI)** | Only `ALWAYS_EAGER` / model-level worker tested | Added live `redis:7-alpine` + detached `celery -A config worker` (`ALWAYS_EAGER=False`) task roundtrip to CI Step 9 (`celery@runnervmwuk1x` passed) | **CI WORKER CLOSED** *(Live paid Render worker/beat & managed TLS Redis remain OPEN)* |
| **OA-10 (Play Visual Assets)** | Zero Feature Graphic, phone/tablet screenshots, or store listing copy | Generated `docs/play-store/feature-graphic-1024x500.png` (`1024x500`), captured `6` real built-UI screenshots (`780x1688`, `1280x800`), authored `PLAY_STORE_LISTING_DRAFTS.md` | **ASSETS/DRAFTS CLOSED** *(Play Console submission & reviewer demo credentials remain OPEN)* |
| **OA-01 (Prod Web)** | `www.srilekh.com` returns `404` on `/privacy-policy`, `/delete-account`, `/terms`, `/refund-policy`, `/contact`, `/pricing` | Protected `main` untouched per rule | **OPEN (Owner Merge Approval Required)** |
| **OA-02** | Legal entity / GSTIN / Grievance Officer / retention placeholders (`[Pending Owner Confirmation]`) | Must not fabricate legal identity | **OPEN (Owner Input Required)** |
| **OA-04** | Physical Android device QA matrix (Android 8–15 handsets) | Host lacks `adb` / physical device | **OPEN (Owner Hardware Required)** |
| **OA-06** | Live SMTP credentials, DKIM TXT alignment & real inbox delivery (<10s) | Probed GoDaddy MX/SPF (`include:secureserver.net -all`), DMARC (`p=quarantine`), missing DKIM TXT, and TCP port `587/465` reachability; SMTP creds absent | **OPEN (Owner DNS + SMTP Credentials Required)** |
| **OA-08** | Continuous 7-day staging operational soak | Depends on OA-05 + OA-06 + time | **OPEN (Cannot be simulated)** |
| **OA-09** | Deployed Vercel staging frontend E2E (`staging.srilekh.com`) | Verified `staging.srilekh.com` NXDOMAIN & `.vercel.app` HTTP `302` SSO login wall | **OPEN (Owner DNS / Vercel Protection Toggle Required)** |
| **OA-11** | Native Android Keystore / `EncryptedSharedPreferences` token upgrade | Disclosed accurately in privacy policy | **OPEN (P2 Post-Hardware Enhancement)** |
