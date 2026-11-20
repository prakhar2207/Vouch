# SRI LEKH — STAGE 1.2.6 GOOGLE PLAY CONSOLE SUBMISSION CHECKLIST

**Assessment Date:** 2026-11-12  
**Target Package:** `com.srilekh.app`  
**Bundle Artifact Target:** Signed `app-release.aab` (`targetSdkVersion 35/36`, `minSdkVersion 24`)  
**Certification Verdict:** **READY FOR OWNER SUBMISSION (Pending OA-01 Live Policy URLs, OA-02 Legal Fields & OA-03 Signed AAB - OA-10)**  

---

## 1. Executive Summary

All static store listing copy, visual branding assets, screenshots, Data Safety responses, and Google Play policy technical requirements have been prepared and stored in [`docs/play-store/`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store).

This checklist serves as the exact step-by-step reference for the developer account owner when configuring the Google Play Console (`https://play.google.com/console`).

---

## 2. Store Listing Copy & Metadata

Copy verified against [`docs/play-store/PLAY_STORE_LISTING_DRAFTS.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store/PLAY_STORE_LISTING_DRAFTS.md):

| Play Console Field | Value to Enter | Character Limit / Check |
| :--- | :--- | :--- |
| **App Name** | `SriLekh: GST Billing & Ledger` | `29 / 30` chars (PASS) |
| **Short Description** | `Offline-first GST invoicing, double-entry ledgers, inventory & Tally export.` | `76 / 80` chars (PASS) |
| **Category** | `Business` | Recommended MSME category |
| **Tags** | `Accounting`, `Bookkeeping`, `Inventory`, `Invoicing` | Max 5 allowed |
| **Pricing & Distribution** | `Free` *(Free Business Companion Portal)* | Contains Ads: **No** |
| **In-App Purchases** | **No** (All billing handled externally for B2B enterprise onboarding) | Complies with B2B SaaS rules |

### Full Description Copy:
> SriLekh is an accounting, GST billing, and inventory management companion for Indian wholesalers, distributors, and MSME businesses.
>
> **Implemented Capabilities:**
> - **Double-Entry Bookkeeping:** Sales Invoices, Purchase Bills, Payment Receipts & Payouts, Debit/Credit Notes, and Journal/Contra vouchers with strict debit-credit equilibrium.
> - **Indian GST Workflows:** Automatic intra-state (CGST/SGST) vs. inter-state (IGST) calculation, GSTR-1/3B/9 summary views, and GSTR-2B JSON/Excel reconciliation.
> - **Inventory & Multi-Warehouse:** Product catalog, FIFO valuation, batch tracking, price-list import (`.xlsx`/`.csv`/PDF), and stock movement logs.
> - **Offline-First Resilience:** Create vouchers while offline with non-extractable WebCrypto `AES-GCM-256` local payload encryption and idempotent cloud sync upon reconnect.
> - **Financial Statements & Tally Export:** Trial Balance, Profit & Loss, Balance Sheet, Party Statements, Bank Statement Excel/CSV reconciliation, and Tally XML export.
> - **Self-Service Account Control:** Full in-app and web account deletion (`https://srilekh.com/delete-account`) with cryptographic audit log preservation where required by statutory bookkeeping law.

---

## 3. Verified Visual Graphics Inventory

All graphics are pre-verified for dimensions, aspect ratio, and zero placeholder content:

| Asset Type | Requirement | Repository File Path | Status |
| :--- | :--- | :--- | :--- |
| **App Icon** | `512 x 512` PNG (RGBA) | [`frontend/public/icons/icon-512x512.png`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/public/icons/icon-512x512.png) | Verified |
| **Feature Graphic** | `1024 x 500` PNG (RGB) | [`docs/play-store/feature-graphic-1024x500.png`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store/feature-graphic-1024x500.png) | Verified |
| **Phone Screenshot 1** | Dashboard UI (`390x844 @2x`) | [`docs/play-store/screenshots/phone-01-dashboard.png`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store/screenshots/phone-01-dashboard.png) | Verified |
| **Phone Screenshot 2** | Vouchers UI (`390x844 @2x`) | [`docs/play-store/screenshots/phone-02-vouchers.png`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store/screenshots/phone-02-vouchers.png) | Verified |
| **Phone Screenshot 3** | Privacy Policy (`390x844 @2x`) | [`docs/play-store/screenshots/phone-03-privacy-policy.png`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store/screenshots/phone-03-privacy-policy.png) | Verified |
| **Phone Screenshot 4** | Account Deletion (`390x844 @2x`) | [`docs/play-store/screenshots/phone-04-delete-account.png`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store/screenshots/phone-04-delete-account.png) | Verified |
| **Tablet 10" Screenshot 1** | Responsive Dashboard | [`docs/play-store/screenshots/tablet-01-dashboard.png`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store/screenshots/tablet-01-dashboard.png) | Verified |
| **Tablet 10" Screenshot 2** | Landing Portal | [`docs/play-store/screenshots/tablet-02-landing.png`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store/screenshots/tablet-02-landing.png) | Verified |

---

## 4. App Content & Policy Declarations (Play Console -> App Content)

### 4.1 Privacy Policy & Account Deletion Links
- **Privacy Policy URL:** `https://www.srilekh.com/privacy-policy` *(Prerequisite: Must return `HTTP 200` via OA-01 live deployment and have OA-02 legal placeholders resolved).*
- **Account Deletion URL:** `https://www.srilekh.com/delete-account` *(Prerequisite: Must return `HTTP 200` via OA-01 live deployment).*
- **In-App Account Deletion:** Active inside `Settings -> Privacy -> Delete Account` (routes securely to deletion verification modal).

### 4.2 Data Safety Form Exact Answers
| Question | Accurate Selection |
| :--- | :--- |
| Does your app collect or share any of the required user data types? | **Yes** |
| Is all of the user data collected by your app encrypted in transit? | **Yes** (HTTPS / TLS 1.2+) |
| Do you provide a way for users to request that their data is deleted? | **Yes** (`https://www.srilekh.com/delete-account`) |
| **Data Type 1: Personal Info** (Name, Email address, Phone number) | **Collected** (Account management & App functionality), Ephemeral: No, Required (not optional) for account registration. **Not Shared** with 3rd parties for ads. |
| **Data Type 2: Financial Info** (Purchase/Sales Invoice history) | **Collected** (App functionality — double-entry bookkeeping). **Not Shared**. |
| **Data Type 3: App Info & Performance** (Diagnostic error/audit logs) | **Collected** (App functionality, fraud prevention, security compliance). |

### 4.3 Permissions Justification (Sensitive Permissions)
- `android.permission.CAMERA`: **Not for background surveillance.** Used exclusively when user explicitly taps the "Scan Barcode / QR" button on invoice or product screens (`required="false"` in Manifest).
- `android.permission.INTERNET` / `ACCESS_NETWORK_STATE`: Required for cloud synchronization when network connectivity returns.

### 4.4 Target Audience & Content Rating
- **Target Age Group:** `18 and over` (B2B Trade, Wholesale & Accounting software; not designed for children under 13).
- **Content Rating Questionnaire (IARC):** No violence, no gambling, no user-generated public social feed -> Expected Rating: `3+` / `Everyone`.

---

## 5. App Access Instructions (Play Reviewer Sandbox Credentials)

Google Play reviewers must be provided with valid working login credentials because SriLekh requires authentication before entering the accounting dashboard.

> [!CAUTION]
> **MANDATORY TENANT ISOLATION RULE**: NEVER give Google Play reviewers credentials to **`Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`)** or any real customer company.

### Authorized Sandbox Reviewer Credentials to Enter in Play Console -> App Access:
- **Test Tenant Company:** `Apex Belting & Industrial Store (Demo)`
- **Company ID:** `4e62863a-08f9-4e99-b0bd-64873acfdd33`
- **Instructions for Reviewer:**
  1. Open the app and select **Login**.
  2. Enter dedicated demo account username and password configured for `Apex Belting & Industrial Store (Demo)` *(Owner to verify/reset demo password immediately prior to Play submission)*.
  3. Navigate Dashboard -> Sales Invoices -> Create Draft Invoice -> Toggle Airplane mode to observe Offline Queue -> Reconnect to observe automatic sync.
  4. Camera permission may be tested via Item Catalog -> Barcode Scan.

---

## 6. Final Pre-Submit Gate Check

1. [ ] `https://www.srilekh.com/privacy-policy` resolves with `HTTP 200` and zero `[Pending Owner Confirmation]` strings.
2. [ ] `https://www.srilekh.com/delete-account` resolves with `HTTP 200`.
3. [ ] Signed `app-release.aab` uploaded to Google Play Console (Internal Testing track verified on physical device first).
4. [ ] Reviewer credentials verified active against `Apex Belting & Industrial Store (Demo)`.
