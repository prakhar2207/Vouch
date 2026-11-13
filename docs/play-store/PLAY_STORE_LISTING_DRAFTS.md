# SriLekh — Google Play Console Store Listing & Graphic Asset Specification

**Target Package:** `com.srilekh.app`  
**Brand Name:** SriLekh  
**Target Audience:** 18+ Business Owners, Wholesalers, MSME Traders, Accountants (India)  
**Ads Present:** No  
**In-App Purchases / Subscriptions in Android App:** No *(Free Business Companion Portal)*

---

## 1. Existing vs. Required Visual Assets Audit

| Asset Slot | Google Play Requirement | Repo Status | File Path |
| :--- | :--- | :--- | :--- |
| **App Icon** | `512 x 512 px` 32-bit PNG (alpha optional) | **PRESENT** (`512x512 RGBA`) | [`frontend/public/icons/icon-512x512.png`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/public/icons/icon-512x512.png) |
| **Feature Graphic** | `1024 x 500 px` PNG/JPEG | **CREATED IN STAGE 1.2.5** (`1024x500 RGB`) | [`docs/play-store/feature-graphic-1024x500.png`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store/feature-graphic-1024x500.png) |
| **Phone Screenshots** | Minimum 2 (16:9 or 9:16, >=320px, max 3840px) | **CAPTURED IN STAGE 1.2.5** (Real UI renders @ `390x844` @2x = `780x1688` + Owner app capture checklist) | [`docs/play-store/screenshots/`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store/screenshots) |
| **7" & 10" Tablet Screenshots** | Recommended (`1280x800` / `1440x900`) | **CAPTURED IN STAGE 1.2.5** (Real UI responsive viewport renders) | [`docs/play-store/screenshots/`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/play-store/screenshots) |

---

## 2. Draft Store Listing Copy (Strictly Accurate to Implemented Features)

- **App Name (<=30 chars):** `SriLekh: GST Billing & Ledger` (`29` chars)
- **Short Description (<=80 chars):** `Offline-first GST invoicing, double-entry ledgers, inventory & Tally export.` (`76` chars)
- **Full Description Draft:**
  SriLekh is an accounting, GST billing, and inventory management companion for Indian wholesalers, distributors, and MSME businesses.

  **Implemented Capabilities:**
  - **Double-Entry Bookkeeping:** Sales Invoices, Purchase Bills, Payment Receipts & Payouts, Debit/Credit Notes, and Journal/Contra vouchers with strict debit-credit equilibrium.
  - **Indian GST Workflows:** Automatic intra-state (CGST/SGST) vs. inter-state (IGST) calculation, GSTR-1/3B/9 summary views, and GSTR-2B JSON/Excel reconciliation.
  - **Inventory & Multi-Warehouse:** Product catalog, FIFO valuation, batch tracking, price-list import (`.xlsx`/`.csv`/PDF), and stock movement logs.
  - **Offline-First Resilience:** Create vouchers while offline with non-extractable WebCrypto `AES-GCM-256` local payload encryption and idempotent cloud sync upon reconnect.
  - **Financial Statements & Tally Export:** Trial Balance, Profit & Loss, Balance Sheet, Party Statements, Bank Statement Excel/CSV reconciliation, and Tally XML export.
  - **Self-Service Account Control:** Full in-app and web account deletion (`https://srilekh.com/delete-account`) with cryptographic audit log preservation where required by statutory bookkeeping law.

---

## 3. Public Policy & URL Declarations

- **Privacy Policy URL:** `https://srilekh.com/privacy-policy` *(Pending live deploy of `feat/google-play-launch-readiness` & owner legal entity fields)*
- **Account Deletion URL:** `https://srilekh.com/delete-account` *(Pending live deploy)*
- **Support Email:** `support@srilekh.com`
- **Owner-Supplied Items Still Required Before Play Submission:** Registered Legal Entity Name, Physical Address, Support Phone, Grievance Officer Name & Contact, Formal Statutory Retention Period (years), Closed/Sandbox Reviewer Demo Credentials (never production tenant `Maa Annapurna Belting Store`), and Signed Release `.aab` from Owner Upload Keystore.
