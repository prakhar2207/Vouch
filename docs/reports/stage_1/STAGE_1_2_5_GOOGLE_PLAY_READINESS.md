# SRI LEKH — STAGE 1.2.5 GOOGLE PLAY LAUNCH READINESS REPORT

**Assessment Date:** 2026-11-12  
**Package ID:** `com.srilekh.app`  
**Target Branch:** `feat/google-play-launch-readiness` @ `c160fca0`  
**Overall Gate Verdict (Gate A — Google Play Readiness):** **BLOCKED** *(Technical controls & visual/store listing drafts prepared; live public URLs `404`, owner legal fields, Play Console declarations, and reviewer demo account still require owner completion)*

---

## 1. Stage 1.2.5 Deliverables Completed in Repository

| Requirement | Stage 1.2.4 Status | Stage 1.2.5 Closure & Artifact |
| :--- | :--- | :--- |
| **Feature Graphic (`1024 x 500 px`)** | Missing | Created & visually inspected [`docs/play-store/feature-graphic-1024x500.png`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store/feature-graphic-1024x500.png) (`1024x500` RGB, `45,923` bytes, verified via `PIL.Image` and visual review with `0` clipped text) |
| **Phone Screenshots (min 2)** | Missing | Captured `4` real built-UI Playwright (`msedge`) renders against isolated SQLite sandbox: `phone-01-dashboard.png`, `phone-02-vouchers.png`, `phone-03-privacy-policy.png`, `phone-04-delete-account.png` (`780x1688`, `390x844 @2x`) |
| **Tablet Screenshots** | Missing | Captured `2` real built-UI tablet renders: `tablet-01-dashboard.png`, `tablet-02-landing.png` (`1280x800`) |
| **App Icon (`512 x 512 px`)** | Present | Verified existing [`frontend/public/icons/icon-512x512.png`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/public/icons/icon-512x512.png) (`512x512 RGBA`) |
| **Store Listing Draft Copy** | Unwritten | Authored strictly factual Play listing draft in [`docs/play-store/PLAY_STORE_LISTING_DRAFTS.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store/PLAY_STORE_LISTING_DRAFTS.md) (`App Name` 29 chars, `Short Description` 76 chars, zero fabricated claims) |
| **Account Deletion Backend Live Staging Proof** | `404` on staging (`f8578a88`) | Verified live on `https://vouch-u3u7.onrender.com` (`44fd0150`): unauthenticated `POST /api/v1/auth/account/delete-request/` returns `401`; ephemeral user deletion returns `200` `COMPLETED`, immediately revokes bearer tokens (`GET /api/v1/auth/me/` -> `401`), and `/delete-status/` exposes zero PII |

---

## 2. Android Policy & Manifest Guardrails Verified

- Inspecting [`frontend/capacitor.config.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/capacitor.config.ts#L1-L37) confirms:
  - `appId: 'com.srilekh.app'`, `appName: 'SriLekh'`
  - `cleartext: false`, `androidScheme: 'https'`, `allowNavigation: ['srilekh.com', '*.srilekh.com', 'api.srilekh.com']`
- Inspecting [`frontend/android/app/src/main/AndroidManifest.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/AndroidManifest.xml#L1-L69) confirms:
  - `android:allowBackup="false"`, `android:usesCleartextTraffic="false"`, `android:networkSecurityConfig="@xml/network_security_config"`
  - Minimal permissions: `INTERNET`, `ACCESS_NETWORK_STATE`, `CAMERA` (`android.hardware.camera` `required="false"`) — no `READ_CONTACTS`, `ACCESS_FINE_LOCATION`, or ad SDK permissions.

---

## 3. Remaining Owner Actions (`OA-01`, `OA-02`, `OA-10`)

1. **Publish Policy & Account Deletion URLs (`OA-01`):** `https://www.srilekh.com/privacy-policy` and `https://www.srilekh.com/delete-account` still return `HTTP 404` until `feat/google-play-launch-readiness` is approved for merge to `main`.
2. **Confirm Legal Entity & Grievance Officer Details (`OA-02`):** Provide legal company name, registered office address, phone number, Grievance Officer name/email, and formal retention term in years to replace `[Pending Owner Confirmation]` markers.
3. **Google Play Console Portal Submission (`OA-10`):**
   - Upload signed release `.aab` + store listing assets (`docs/play-store/`).
   - Complete Data Safety form (matching `@capacitor/preferences` local session tokens and WebCrypto encrypted IndexedDB disclosures), App Content (Financial features, 18+ Business target audience, Ads: No), and attach dedicated sandbox demo account credentials (strictly NEVER `Maa Annapurna Belting Store`).
   - Consider re-capturing on-device Android WebView/device-frame screenshots after physical device QA if desired before Play Store publication.
