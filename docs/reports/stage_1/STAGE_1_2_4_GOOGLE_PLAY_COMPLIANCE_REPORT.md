# SRI LEKH — STAGE 1.2.4 GOOGLE PLAY COMPLIANCE REPORT

**Assessment Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Target Package:** `com.srilekh.app`  
**Overall Gate Status (Gate A):** **BLOCKED / OWNER ACTION REQUIRED**

---

## 1. Live URL Audit (`https://www.srilekh.com`)

Direct unauthenticated HTTPS checks performed during Stage 1.2.4 against live public domain:
- `https://www.srilekh.com/` -> **`HTTP 200`**
- `https://www.srilekh.com/privacy-policy` -> **`HTTP 404`**
- `https://www.srilekh.com/delete-account` -> **`HTTP 404`**
- `https://www.srilekh.com/terms` -> **`HTTP 404`**
- `https://www.srilekh.com/refund-policy` -> **`HTTP 404`**
- `https://www.srilekh.com/contact` -> **`HTTP 404`**
- `https://www.srilekh.com/pricing` -> **`HTTP 404`**

Play Console rejects apps whose declared **Privacy Policy URL** or **Account Deletion URL** returns `HTTP 404`. All 6 pages exist, build, and pass Playwright Desktop + Mobile checks on `feat/google-play-launch-readiness`, awaiting approved promotion/deployment.

---

## 2. Compliance Controls Verified in Repository

1. **Account Deletion Web & In-App Flow:** `/delete-account` + `Settings -> Account Profile` backed by [`AccountDeletionView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py#L1011-L1206) (`10/10` tests on Neon PG 18.6 + Chromium Edge E2E).
2. **Privacy Disclosure Alignment ([`privacy-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/privacy-policy/page.tsx)):** Accurately documents HttpOnly cookie auth, `@capacitor/preferences` token custody on Android (`allowBackup="false"`, without overclaiming hardware Keystore), and `VouchOfflineDB` `AES-GCM-256` local encryption.
3. **No In-App Billing / Play Payment Circumvention Risk:** Verified via Chromium Edge Playwright E2E with simulated Capacitor runtime (`window.Capacitor.isNativePlatform() => true`) that `/pricing` hides commercial upgrade CTAs (`0` subscription buttons visible via [`NativeCommercialHide`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/public/NativeCommercialHide.tsx)).
4. **Honest Placeholders Left Clean ([`contact/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/contact/page.tsx), [`delete-account/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/delete-account/page.tsx)):** Legal entity name, office address, phone number, and statutory retention years retain explicit `[Pending Owner Confirmation]` markers rather than invented owner/company details.
5. **Minimal Permissions & Zero Ad/Tracking SDKs:** `CAMERA`, `INTERNET`, `ACCESS_NETWORK_STATE` only in [`AndroidManifest.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/AndroidManifest.xml); zero ad or third-party analytics SDKs in `package.json` or `build.gradle`; `512x512` logo + adaptive mipmaps present.

---

## 3. Remaining External Play Console Blockers (Owner Action Required)

1. Deploy `feat/google-play-launch-readiness` (after review) so `https://srilekh.com/privacy-policy`, `/delete-account`, `/terms`, `/refund-policy`, `/contact`, and `/pricing` return live `HTTP 200`.
2. Replace `[Pending Owner Confirmation]` fields in [`public-constants.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/public/public-constants.ts), [`contact/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/contact/page.tsx), [`privacy-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/privacy-policy/page.tsx), and [`delete-account/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/delete-account/page.tsx) with owner-verified legal entity name, registered address, phone, Grievance Officer identity, and retention policy period.
3. Supply Play Console visual assets (`1024x500` Feature Graphic, phone & tablet screenshots), complete Data Safety / Financial Features / Content Rating / App Access review forms, and provide an isolated non-production demo credential (`test_neondb_staging` / demo sandbox only — never `Maa Annapurna Belting Store`).
4. Build and sign release `.aab` on a JDK 21 + Android SDK host after physical device QA.
