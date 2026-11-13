# SRI LEKH — GOOGLE PLAY SUBMISSION CHECKLIST

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Target Package:** `com.srilekh.app`  
**Classification:** **BLOCKED / OWNER ACTION REQUIRED** *(Technical & Policy Code Controls Ready; External Deployment, Store Assets & Owner Identity Required)*

---

## 1. Pre-Submission Technical & Policy Checklist

| Requirement | Code / Asset Evidence | Current Status |
| :--- | :--- | :--- |
| **Package Identity & Target SDK 36** | `com.srilekh.app`, `minSdkVersion 24`, `compileSdkVersion 36`, `targetSdkVersion 36` | **Verified in Source** |
| **App Icon (`512x512` PNG + adaptive mipmaps)** | Present in `frontend/mobile-shell/logo.png` & `android/app/src/main/res/mipmap-*` | **Verified Present** |
| **Account Deletion Web Portal & In-App Flow** | `/delete-account` + `Settings -> Account Profile` + hardened [`AccountDeletionView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py) (`select_for_update()`, throttle, token/device revocation, PII anonymization) | **Verified Local + Tests** *(Not yet live on `https://srilekh.com/delete-account`)* |
| **No In-App Billing / Pricing / Checkout Links in Android** | [`NativeCommercialGuard.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/public/NativeCommercialGuard.tsx) & [`NativeCommercialHide.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/public/NativeCommercialHide.tsx) verified in simulated Chromium Capacitor E2E (`pricing`, `refund-policy`) | **Verified Local E2E** *(Needs physical Android device QA)* |
| **Accurate Privacy Policy (`https://srilekh.com/privacy-policy`)** | Updated Sections 7, 9, 10 for HttpOnly browser cookies, Capacitor `@capacitor/preferences` disclosure (non-Keystore), and `VouchOfflineDB` WebCrypto AES-GCM-256 encryption | **Verified Updated** *(Not yet deployed live to `srilekh.com`)* |
| **Removed Sensitive Media Permissions & Cleartext Traffic** | Removed `READ_MEDIA_IMAGES` / storage perms; `allowBackup="false"`, `usesCleartextTraffic="false"`, `@xml/network_security_config`, restricted `allowNavigation` | **Verified in XML / `cap sync`** |
| **Zero Ads / Tracking SDKs** | Zero AdMob, Firebase Analytics, Mixpanel, or Sentry packages in `package.json` & `build.gradle` | **Verified PASS** |
| **Zero Production Runtime npm Vulnerabilities** | `npm audit --omit=dev` -> `0` (`xlsx` removed, `next@16.4.6`, `@serwist/*@9.5.13`, `dompurify@^3.4.17`) | **Verified PASS (`0` vulns)** |
| **Signed `.aab` Artifact (`./gradlew bundleRelease`)** | Host lacks JDK 21, Android SDK, and owner upload keystore | **BLOCKED (Build Host & Keystore)** |
| **Physical Android Device Testing Matrix** | No `adb` / physical device attached | **NOT TESTED** |
| **Play Console Graphic Assets & Owner Forms** | Missing `1024x500` Feature Graphic, Phone/Tablet screenshots, legal entity name/address, Grievance Officer, retention years, reviewer demo account, Data Safety & Financial Features forms | **OWNER ACTION REQUIRED** |

---

## 2. Draft Play Store Declarations (Non-Overstated)

- **Ads:** No (`Does not contain ads`)
- **Age Target:** `18 and older` (MSME B2B bookkeeping & billing)
- **Account Deletion Web URL:** `https://srilekh.com/delete-account` *(deploy live before submission)*
- **Privacy Policy URL:** `https://srilekh.com/privacy-policy` *(deploy live with owner legal details before submission)*
- **Accurate Capabilities Only:** Double-entry GST vouchers, state-wise CGST/SGST/IGST calculation, GSTR-1/3B/9 summary & GSTR-2B file reconciliation, multi-warehouse inventory valuation, optional AI OCR bill/statement extraction, manual/assisted bank statement import, Tally XML export, and offline sales/purchase drafting with AES-GCM-256 local encryption. **Do not claim** live GSTN API filing, live IRN/E-Way generation, live automatic Setu/bank feeds, Razorpay in-app payments, or ISO/SOC2 certification.
