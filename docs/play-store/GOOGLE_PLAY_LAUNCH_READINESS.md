# SRI LEKH — GOOGLE PLAY LAUNCH READINESS REPORT

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness` (branched from staging `fix/stage4-12-day6-remediation` @ `f8578a88`)  
**Target Android Package:** `com.srilekh.app` (App Name: `SriLekh`)  
**Commercial Model:** Free app download with direct existing-account workspace access (no in-app subscription plans, no Google Play Billing, no payment gateways or checkout links exposed inside Android).

---

## 1. Executive Launch Readiness Summary

| Store Listing / Launch Track | Classification | Notes |
| :--- | :--- | :--- |
| **App Identity & Package (`com.srilekh.app`)** | **Verified PASS** | Configured in [`capacitor.config.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/capacitor.config.ts), [`build.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/build.gradle), and [`strings.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/res/values/strings.xml). |
| **Commercial Model Compliance (Zero In-App Billing/Pricing/Checkout Links)** | **Verified PASS** *(Local E2E)* / **BLOCKED** *(Physical Android Device)* | [`NativeCommercialGuard.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/public/NativeCommercialGuard.tsx) and [`NativeCommercialHide.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/public/NativeCommercialHide.tsx) suppress `/pricing`, `/refund-policy`, and pricing/checkout links inside Capacitor (`isCapacitorNative()`), while keeping public web pages intact. Verified in simulated Chromium/Edge Capacitor E2E (`CAP_EVAL: res=True`). Live website deployment + physical Android device testing still required. |
| **App Icon (`512x512` PNG + adaptive mipmaps)** | **Verified PASS** | `frontend/mobile-shell/logo.png` verified `512x512 PNG` (`59,102` bytes); `mipmap-xxxhdpi/ic_launcher.png` verified `192x192 PNG`; splash screens up to `1280x1920 PNG` present. |
| **Account Deletion (In-App + Web URL `https://srilekh.com/delete-account`)** | **Verified PASS** *(Local + Automated)* / **BLOCKED** *(Production/Live Web Deploy)* | Backend API, `/delete-account` web portal, and `Settings → Account Profile` in-app link implemented and verified (`exit 0` in Django tests and live Edge E2E). Not yet deployed to live `srilekh.com` (`main` untouched per safety policy). |
| **Privacy Policy & Data Safety Alignment** | **PARTIALLY VERIFIED** | Code disclosures updated in [`privacy-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/privacy-policy/page.tsx); final legal entity identity, registered address, Grievance Officer, and Play Console Data Safety form submission require Owner action. |
| **Feature Graphic (`1024x500`) & Phone/Tablet Screenshots** | **OWNER ACTION REQUIRED** | Not present in repository; must be produced from final signed/staged UI without unimplemented claims. |
| **Signed Release `.aab`, JDK/Android SDK, Physical Device Test & Play Console Forms** | **BLOCKED / OWNER ACTION REQUIRED** | Host lacks JDK (`java`/`keytool`), Android SDK (`adb`), upload keystore, Play Console account declarations, and physical Android hardware. |

---

## 2. Draft Google Play Store Listing Copy (Strictly Implemented Capabilities Only)

### A. Store Listing Metadata
- **App Name:** `SriLekh`
- **Category:** Business (Finance/Accounting SaaS tool)
- **Short Description (<= 80 chars, verified 76 chars):**  
  `GST billing, double-entry accounting & inventory management for Indian MSMEs`
- **Full Description Draft (accurate to verified codebase):**
  > **SriLekh** helps Indian retailers, wholesalers, distributors, and small businesses manage day-to-day billing, inventory, and double-entry accounting in a clean multi-company workspace.
  >
  > **Implemented Capabilities:**
  > - **Double-Entry Accounting:** Sales, Purchase, Receipt, Payment, Contra, Journal, Proforma Quotation, Credit Note, and Debit Note vouchers with balanced debit-credit validation and SHA-256 audit hash trails.
  > - **GST Calculation & Reports:** Automated CGST, SGST, and IGST computation based on company/party state codes, GSTIN format checks, GSTR-1/3B/9 summary preparation, and GSTR-2B file reconciliation (JSON/Excel). *(Note: Direct government GSTN filing and live IRN/E-Way dispatch are not enabled in this release.)*
  > - **Inventory & Multi-Warehouse Stock:** Product categories, HSN codes, godown/warehouse tracking, and stock valuation (Average Cost, FIFO, LIFO, Standard Cost).
  > - **Bill Scanning & Statement Upload:** Upload purchase bill photos or PDFs for structured field extraction (when server AI keys are configured) and import CSV, Excel, PDF, OFX, or QIF bank statements for manual/assisted reconciliation. *(Live automatic bank feeds are not enabled.)*
  > - **Multi-Company & Role Permissions:** Manage multiple firms under one account with Owner, Admin, Chartered Accountant (CA), Employee, and Viewer roles, plus Tally XML data export.
  > - **Offline Continuity for Supported Workflows:** Draft supported sales/purchase vouchers and access synced local masters offline with automatic background sync upon reconnection. *(Live reports, payments, banking, and journals require connectivity.)*

### B. Play Console Required Declarations & Guidance
1. **Ads Declaration:** Select **"No, my app does not contain ads"** (verified zero ad SDKs in `package.json` and `build.gradle`).
2. **Target Audience & Age Group:** `18 and older` (B2B accounting software for businesses/MSMEs; not directed at children).
3. **Content Rating Questionnaire:** Complete IARC questionnaire in Play Console (`Business / Utility`; no violence, UGC, gambling, or restricted content).
4. **Financial Features Declaration:** Mandatory for all apps in Play Console. SriLekh is an internal business bookkeeping/billing tool (NOT a lending, digital wallet, UPI PSP, banking, investment, or crypto app). Declare accurately per Google Play Financial Features questionnaire; confirm whether India fintech exclusions apply via owner/counsel check before submission.
5. **App Access Instructions (Mandatory because Login is Required):** Provide Google Play reviewers with dedicated **non-production demo credentials** in Play Console (`App content > App access`) scoped to a synthetic sandbox tenant (`Stage 4.14 Live Audit Sandbox` or equivalent isolated demo tenant — never real customer books like `Maa Annapurna Belting Store`).

---

## 3. Missing Owner-Provided Information & Mandatory Owner Actions

| Item | Why Needed | Current Status |
| :--- | :--- | :--- |
| Legal entity name & Udyam/CIN/GST registration details | Store listing, `/privacy-policy`, `/terms`, `/contact`, Play Developer verification | **OWNER ACTION REQUIRED** |
| Registered physical office address & verified support phone | India commercial disclosures, Play Store developer contact section | **OWNER ACTION REQUIRED** |
| Support email operational inbox verification (`support@srilekh.com` or verified mailbox) | Play Store contact email + manual deletion fallback | **OWNER ACTION REQUIRED** |
| Named Grievance Officer details (name, email, address) | `/privacy-policy` DPDP Act 2023 readiness | **OWNER ACTION REQUIRED** |
| Formal statutory accounting/audit data retention period (years) | Confirm placeholder in `/delete-account` & `/privacy-policy` Section 13 | **OWNER ACTION REQUIRED** |
| Feature graphic (`1024x500` PNG/JPEG) & >= 2 Phone Screenshots (+ Tablet if supporting large screens) | Mandatory Play Store graphic assets | **OWNER ACTION REQUIRED** |
| Play Upload Keystore + `key.properties` + Android SDK/JDK build host | Building & signing release `.aab` (`versionCode` increment if uploaded previously) | **OWNER ACTION REQUIRED** |
| Google Play Reviewer demo account credentials | Mandatory App Access review for gated SaaS apps | **OWNER ACTION REQUIRED** |
| Play Console Data Safety & Financial Features forms | Mandatory pre-submission declarations | **OWNER ACTION REQUIRED** |
