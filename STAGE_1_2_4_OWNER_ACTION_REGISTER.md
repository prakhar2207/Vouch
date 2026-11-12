# SRI LEKH — STAGE 1.2.4 OWNER ACTION REGISTER

**Assessment Date:** 2026-11-12  
**Branch Ready for Review:** `feat/google-play-launch-readiness`  
**Purpose:** Single consolidated register of all blockers outside local code control that require owner approval, credentials, external infrastructure provisioning, or build/device hardware.

---

## P0 / Release-Critical Owner Blockers

| ID | Gate | Action Required from Owner / DevOps | Why Blocked Locally | Acceptance Criteria to Close Blocker |
| :--- | :--- | :--- | :--- | :--- |
| **OA-01** | **Gate A / D** | **Approve branch push & deploy to staging and `https://srilekh.com`** | Branch `feat/google-play-launch-readiness` is unpushed per rule; live `www.srilekh.com` returns `404` on all 6 compliance pages & `vouch-u3u7.onrender.com` runs `f8578a88` (`delete-request` `404`). | `https://srilekh.com/privacy-policy`, `/delete-account`, `/terms`, `/refund-policy`, `/contact`, `/pricing` return `HTTP 200`; staging returns `200`/`401` (not `404`) on `/api/v1/auth/account/delete-request/`. |
| **OA-02** | **Gate A** | **Provide legal entity details & finalize compliance disclosures** (`[Pending Owner Confirmation]`) | Must not invent company legal identity, GSTIN/CIN, office address, phone, Grievance Officer name/email, or statutory retention period. | Update `public-constants.ts`, `contact/page.tsx`, `privacy-policy/page.tsx`, `delete-account/page.tsx` with verified entity info and deploy live. |
| **OA-03** | **Gate B** | **Provision JDK 21 + Android SDK (API 36) + Owner Upload Keystore & build release `.aab`** | `java`, `javac`, `keytool`, `adb`, Android SDK, and upload keystore are absent on this Windows host; [`build.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/build.gradle#L23-L28) still has `minifyEnabled false` & no `signingConfigs.release`. | `./gradlew clean bundleRelease` produces signed `.aab` cleanly (with `minifyEnabled true` R8 tested against `proguard-rules.pro` if desired). |
| **OA-04** | **Gate B** | **Execute physical Android device QA matrix** | No `adb` or physical Android test handset available locally. | Pass cold start, airplane-mode offline queue + reconnect sync, token refresh, password reset deep links, PDF download, camera picker, Secure Shared-Device Logout, and hardware back navigation on real Android 8–15 device(s). |
| **OA-05** | **Gate E** | **Provision managed TLS Redis + paid Render `worker` & `beat` services (`render.yaml`)** | External paid Render/Redis infrastructure cannot be purchased automatically; live health currently shows `redis.status: "unreachable"`, `workers_online: 0`. | `https://vouch-u3u7.onrender.com/api/v1/health/environment/` reports `redis.status: "ok"`, `workers_online >= 1`, `beat_schedule_active: true`. |
| **OA-06** | **Gate D / E** | **Configure live transactional SMTP / email relay & verify staging inbox delivery** | `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` absent locally; staging inbox delivery untested. | Password reset & welcome OTP arrive in real inbox with valid SPF/DKIM/DMARC (<10s) and zero secrets leaked. |
| **OA-07** | **Gate E** | **Run native `pg_dump -Fc` / `pg_restore` binary DR exercise on Linux/CI against `neondb_staging`** | PostgreSQL 18 client binaries (`pg_dump`, `pg_restore`, `psql`) absent on Windows host. | Clean non-production restore to scratch DB matching table row counts, `AuditLog` hash chain, and recorded RPO/RTO. |
| **OA-08** | **Gate E** | **Run 7-day continuous live staging operational soak** | Depends on OA-01, OA-05, OA-06 being continuously online for 7 days. | 7 continuous days of healthy `/api/v1/health/environment/`, zero stuck `PROCESSING` outbox events, zero dead-letter leaks. |
| **OA-09** | **Gate D** | **Bind Vercel staging custom domain (`staging.srilekh.com`) pointing preview build to `vouch-u3u7.onrender.com`** | `vercel`/`render` CLIs & credentials absent; `staging.srilekh.com` DNS lookup fails (`getaddrinfo failed`). | Deployed `staging.srilekh.com` passes multi-tab Chromium E2E against `vouch-u3u7.onrender.com`. |
| **OA-10** | **Gate A** | **Prepare Google Play Console listing assets, declarations & sandbox demo reviewer account** | External Play Console access & owner graphic assets missing (`1024x500` Feature Graphic, phone/tablet screenshots, Data Safety, Financial Features, Content Rating). | Complete Play Console store listing + attach isolated demo credentials (never `Maa Annapurna Belting Store`). |

## P2 Follow-Up Security Enhancement (Recommended Post-Hardware Validation)
- **OA-11 (Android Keystore Token Storage):** Evaluate upgrading [`auth.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/auth.ts) native Capacitor storage from `@capacitor/preferences` to hardware-backed `EncryptedSharedPreferences` / Keychain on a compiled Android/iOS build host, then update [`privacy-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/privacy-policy/page.tsx) once verified on device.
- **OA-12 (Python `pip-audit` Check in CI):** Add `pip-audit` step in GitHub Actions to continuously audit `requirements.txt` against PyPI advisories.
