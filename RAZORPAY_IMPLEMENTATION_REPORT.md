# SRI LEKH — COMPLETE RAZORPAY PAYMENT GATEWAY & SUBSCRIPTION IMPLEMENTATION REPORT

**Date:** 2026-11-16  
**Environment:** Staging / Isolated Test Mode  
**Branch:** `fix/stage4-12-day6-remediation`  
**Starting Commit Hash:** `c160fca0ae69a5dc1bc6398aa95e3185da024bb4`  
**Protected Production Baseline (Untouched):** `main` (`origin/main` at `d39d481ac2eb545d0436fafa9dd2c593ceb7e946`)  
**Production Tenant Check:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) untouched (`count=0` modifications across all operations).

---

## 1. Executive Summary

SriLekh has been equipped with a complete, production-grade commercial payment and subscription billing infrastructure powered by **Razorpay**.

The architecture adheres strictly to the single source of truth defined in [`docs/vouch_tier_feature_matrix.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/vouch_tier_feature_matrix.md):
- **Strategic Philosophy:** *"Commoditize the Accounting ERP, Monetize on AI & Business Intelligence"*
- **Core Modules Unlocked for All Tiers:** Complete Double-Entry Bookkeeping, Sales & Purchase Invoicing, Inventory & Warehousing, GST Calculations & Return JSON preparation, Bank Statement Reconciliation, Offline-First PWA Billing, and Cryptographic Tamper-Proof Audit Trails.
- **Differentiating Tier Metrics:** Daily AI OCR scanning quotas (Fast Printed/Bank vs Deep Handwritten models) and advanced Business Intelligence modules (Sales Timeline, Monthly Trajectory, Brand Mix, 30-Day Predictive Sales Forecast, RFM Customer Matrix, Pareto 80/20, Customer Churn Radar, and Cash Conversion Cycle).

---

## 2. Source Control & Environment Verification

| Attribute | Observed Value | Verification Basis |
| :--- | :--- | :--- |
| **Git Working Branch** | `fix/stage4-12-day6-remediation` | Verified via `git branch` & `git status`. No new branch was created. |
| **Starting HEAD Commit** | `c160fca0ae69a5dc1bc6398aa95e3185da024bb4` | Fast-forward pulled from `origin/fix/stage4-12-day6-remediation`. |
| **Production Branch State** | Untouched | `origin/main` remains at baseline `d39d481`. Zero commits or merges into `main`. |
| **Staging API Target** | `https://vouch-u3u7.onrender.com` | Verified staging Render web service. |
| **Staging DB Target** | `neondb_staging` (`ep-silent-feather-b34egg28-pooler`) | Fingerprint `6f4741bdaaf4`. Fail-closed isolation guard enforced. |
| **Protected Tenant Isolation** | `5d2e5dea-ff86-4871-b2af-fe1c5a05c03c` | Zero test writes executed against real production tenant. |

---

## 3. Architecture & Database Design

A dedicated Django application **`apps.billing`** was introduced to strictly decouple SaaS billing from the core accounting ledger engine. This guarantees that SaaS subscription payments never create unlinked vouchers or corrupt double-entry accounting records.

### A. Data Models ([`apps/billing/models.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/billing/models.py))

1. **`SubscriptionPlan`**:
   - Single source of truth for commercial tiers: `starter`, `growth`, `pro_ai`, `enterprise`.
   - Prices stored in integer paise: base amount, 18% GST, and total amount.
   - Defines JSON feature flags and daily operational limits.
2. **`Subscription`**:
   - Links a company workspace (`Company`) to an active `SubscriptionPlan`.
   - Manages state machine: `created`, `authenticated`, `active`, `pending`, `past_due`, `halted`, `cancelled`, `completed`, `expired`.
   - Tracks `current_period_start`, `current_period_end`, `cancelled_at`, and Razorpay subscription IDs.
3. **`PaymentTransaction`**:
   - Records SaaS gateway transactions: `razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature`, `status`, and cryptographic signature verification status.
4. **`BillingInvoice`**:
   - Sequential SaaS tax invoice: `SL-INV-{YYYY}{MM}-{seq:04d}`.
   - Calculates taxable value, CGST (9%), SGST (9%), and IGST (18%) based on customer state code.
   - Generates official downloadable PDF stored in `media/billing_invoices/`.
5. **`WebhookEvent`**:
   - Persistent, idempotent log of Razorpay webhooks.
   - Uniqueness constraint on `event_id` prevents duplicate processing and replay attacks.
6. **`DailyUsageTracker`**:
   - Tracks atomic daily usage of rate-limited metrics (`ocr_fast_scans`, `ocr_deep_scans`) partitioned by company and date.

---

## 4. Centralized Feature Entitlement Engine

Implemented in [`apps/billing/services/entitlement_service.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/billing/services/entitlement_service.py) and [`apps/billing/permissions.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/billing/permissions.py):

- **Backend Authority:** Frontend elements never dictate access; all restrictions are enforced at the DRF view and service layer.
- **OCR Quota Enforcement:** Integrated into [`apps/accounting/ocr_views.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/ocr_views.py). When a company reaches its plan's daily limit, further extractions are blocked with HTTP 403 Forbidden with `{ "quota_exceeded": true, "metric": ..., "daily_limit": ..., "upgrade_url": "/pricing" }`.
- **Business Intelligence Feature Gating:** Integrated into [`apps/analytics/views.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/analytics/views.py). Restricts Sales Timeline & Trends (`Growth+`), 30-Day Sales Forecast & RFM Matrix (`Pro AI+`), and Cash Conversion Cycle (`Enterprise`). Unauthorized requests return HTTP 403 with upgrade instructions.
- **Data Preservation Guarantee:** Expired or cancelled subscriptions restrict future paid features but **never** delete historical vouchers, ledgers, inventory, or GST filings.

---

## 5. Frontend & Checkout User Journey

1. **Public Pricing Page ([`frontend/src/app/pricing/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/pricing/page.tsx))**:
   - Dynamically loads active plans from `/api/v1/billing/plans/`.
   - Displays all 4 approved tiers, daily OCR limits, and feature comparisons.
   - If authenticated, 1-click checkout opens Razorpay Checkout modal for the active company.
   - If unauthenticated, redirects to `/register?plan={id}`.
2. **Razorpay Checkout Modal ([`frontend/src/lib/billing/razorpay-checkout.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/billing/razorpay-checkout.ts))**:
   - Dynamically loads `checkout.js` on demand.
   - Collects payment securely in Razorpay's PCI-DSS compliant iframe.
   - Returns cryptographic payment credentials to the backend for authoritative verification.
3. **Billing Dashboard ([`frontend/src/app/settings/billing/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/settings/billing/page.tsx))**:
   - Embedded directly in Settings sidebar under *"Billing & Subscriptions"*.
   - Live plan status, billing dates, and daily OCR consumption meters.
   - Invoices table with 1-click official PDF download.
   - Razorpay transaction audit table.
   - Self-serve cancellation modal.

---

## 6. Verification & Automated Test Results

| Test Category | Suite | Passed | Failed | Status |
| :--- | :--- | :---: | :---: | :---: |
| **Billing & Payments** | `apps.billing.tests` (Plans, Checkout, Verification, Webhooks, Cancellation, Entitlements, IDOR) | **16** | 0 | **PASS** |
| **Accounting Non-Interference** | `apps.billing.tests.test_subscription_payments_do_not_create_accounting_vouchers` | **1** | 0 | **PASS** |
| **Upload & Storage Security** | `apps.accounting.tests_upload_security` | **5** | 0 | **PASS** |
| **Stabilization & Accounting** | `apps.accounting.tests_stage4_13_stabilization` | **4** | 0 | **PASS** |
| **Frontend TypeScript Types** | `npx tsc --noEmit` | **58/58 routes** | 0 | **PASS** |
| **Frontend Unit Suites** | `npm test` (Offline sync, encryption, token isolation, parser, contact) | **45** | 0 | **PASS** |
| **Next.js Production Build** | `next build --webpack` | **58/58 pages** | 0 | **PASS** |
