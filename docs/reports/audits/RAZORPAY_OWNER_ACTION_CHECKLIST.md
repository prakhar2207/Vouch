# SRI LEKH — RAZORPAY OWNER ACTION & PRODUCTION READINESS CHECKLIST

Before promoting the Razorpay payment integration to live production on `https://srilekh.com`, the business owner and legal team must complete the following items.

---

## 1. Razorpay Merchant Account Activation & KYC

- [ ] **Complete Business KYC:** Log in to [Razorpay Dashboard](https://dashboard.razorpay.com/) and submit business registration documents (Certificate of Incorporation / Partnership Deed / GST Certificate).
- [ ] **Bank Account Verification:** Complete penny-drop verification for SriLekh's settlement bank account.
- [ ] **Subscribed Payment Methods:** Ensure UPI, Debit/Credit Cards, and NetBanking are enabled for domestic INR transactions.

---

## 2. API Credentials Setup

### Staging (Test Mode)
- [ ] Log in to Razorpay Dashboard, toggle to **Test Mode**.
- [ ] Generate API Keys (`Settings > API Keys > Generate Key`).
- [ ] Set Render Staging environment variables:
  ```env
  RAZORPAY_KEY_ID=rzp_test_...
  RAZORPAY_KEY_SECRET=...
  RAZORPAY_WEBHOOK_SECRET=...
  RAZORPAY_ENVIRONMENT=test
  ```

### Production (Live Mode) — *Pending Owner Approval*
- [ ] Toggle to **Live Mode**.
- [ ] Generate Live API Keys (`Settings > API Keys > Generate Key`).
- [ ] Set Render Production environment variables:
  ```env
  RAZORPAY_KEY_ID=rzp_live_...
  RAZORPAY_KEY_SECRET=...
  RAZORPAY_WEBHOOK_SECRET=...
  RAZORPAY_ENVIRONMENT=production
  ```

---

## 3. Webhook Configuration in Razorpay Dashboard

- [ ] Add Staging Webhook URL: `https://vouch-u3u7.onrender.com/api/v1/billing/webhooks/razorpay/`
- [ ] Add Production Webhook URL: `https://api.srilekh.com/api/v1/billing/webhooks/razorpay/`
- [ ] Configure Secret: Enter a strong random 32-character string matching `RAZORPAY_WEBHOOK_SECRET`.
- [ ] Subscribe to the 11 required events detailed in [`RAZORPAY_WEBHOOK_CONFIGURATION.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/RAZORPAY_WEBHOOK_CONFIGURATION.md).

---

## 4. Legal & Compliance Disclosures (Pending Owner Confirmation)

The following placeholders currently preserved in [`frontend/src/app/terms/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/terms/page.tsx) and [`frontend/src/app/refund-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/refund-policy/page.tsx) must be finalized by the owner:

- [ ] **Legal Business Entity Name:** (e.g. `SriLekh Technologies Private Limited` or proprietorship firm name).
- [ ] **Registered Office Address:** Official registered postal address for billing invoices.
- [ ] **GSTIN for Billing Invoices:** SriLekh's own 15-character GSTIN for SaaS tax invoices.
- [ ] **Customer Support Phone Number:** Live phone support details if offering phone escalation.
- [ ] **Named Grievance Officer:** Formal name and official grievance email address required under Indian IT (Intermediary Guidelines and Digital Media Ethics Code) Rules.
- [ ] **Official Governing Jurisdiction:** (e.g. Courts of Lucknow / Kanpur / New Delhi, India).
