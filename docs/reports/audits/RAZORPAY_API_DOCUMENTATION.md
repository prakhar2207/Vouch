# SRI LEKH — RAZORPAY & BILLING API DOCUMENTATION

**Base URL:** `/api/v1/billing/`  
**Authentication:** Standard Session JWT (`CookieJWTAuthentication` / `Bearer` token)  
**Tenant Scoping:** Authenticated endpoints require `X-Company-ID` header or `company_id` parameter.

---

## 1. Plans & Catalog

### `GET /api/v1/billing/plans/`
- **Access:** Public (`AllowAny`)
- **Description:** Returns the active commercial subscription plans.
- **Response `200 OK`:**
```json
{
  "success": true,
  "plans": [
    {
      "id": "starter",
      "name": "Starter",
      "tagline": "Micro-Retail / Dukaan",
      "description": "Essential double-entry accounting, GST invoicing, B2B network, and daily OCR automation for micro-retailers.",
      "target_persona": "Micro-Retail / Dukaan",
      "billing_interval": "annual",
      "base_amount_paise": 59900,
      "base_amount_rupees": "599.00",
      "tax_rate": "18.00",
      "tax_amount_paise": 10782,
      "tax_amount_rupees": "107.82",
      "total_amount_paise": 70682,
      "total_amount_rupees": "706.82",
      "currency": "INR",
      "tier_order": 1,
      "features": {
        "b2b_edi_network": true,
        "sales_invoicing": true,
        "double_entry_accounting": true,
        "gst_compliance": true,
        "inventory_management": true,
        "banking_reconciliation": true,
        "offline_pwa": true,
        "audit_trail": true,
        "bi_sales_timeline": false,
        "bi_monthly_trajectory": false,
        "bi_brand_mix": false,
        "bi_sales_forecast": false,
        "bi_rfm_segmentation": false,
        "bi_inventory_turnover": false,
        "bi_pareto_matrix": false,
        "bi_churn_radar": false,
        "bi_cash_cycle": false
      },
      "limits": {
        "ocr_fast_daily": 5,
        "ocr_deep_daily": 1
      },
      "is_active": true
    }
  ]
}
```

### `GET /api/v1/billing/plans/<str:plan_id>/`
- **Access:** Public (`AllowAny`)
- **Description:** Returns details of a specific plan by plan ID.

---

## 2. Subscription & Entitlements

### `GET /api/v1/billing/subscription/`
- **Access:** Authenticated (`IsAuthenticated`, `IsCompanyMember`)
- **Headers:** `X-Company-ID: <UUID>`
- **Description:** Retrieves the current active subscription, plan details, and today's daily usage counters for the workspace.
- **Response `200 OK`:**
```json
{
  "success": true,
  "company_id": "82b27a6b-6c8b-4b1a-b0df-6d3b89526939",
  "company_name": "Precision Agro Traders",
  "subscription": {
    "id": "7662fd11-cac5-4556-bb9c-6776552e3368",
    "company_id": "82b27a6b-6c8b-4b1a-b0df-6d3b89526939",
    "company_name": "Precision Agro Traders",
    "plan": { "id": "growth", "name": "Growth", ... },
    "billing_interval": "annual",
    "status": "active",
    "current_period_start": "2026-11-16T12:00:00Z",
    "current_period_end": "2027-11-16T12:00:00Z",
    "next_billing_at": "2027-11-16T12:00:00Z",
    "cancelled_at": null,
    "is_currently_active": true
  },
  "entitlements": {
    "has_active_subscription": true,
    "plan_id": "growth",
    "plan_name": "Growth",
    "features": { ... },
    "limits": { "ocr_fast_daily": 15, "ocr_deep_daily": 3 }
  },
  "daily_usage": {
    "ocr_fast_scans": 3,
    "ocr_deep_scans": 1
  }
}
```

### `POST /api/v1/billing/subscription/cancel/`
- **Access:** Authenticated (`OWNER` or `ADMIN` only)
- **Headers:** `X-Company-ID: <UUID>`
- **Request Body:**
```json
{
  "reason": "Branch consolidation"
}
```
- **Response `200 OK`:**
```json
{
  "success": true,
  "subscription_id": "7662fd11-cac5-4556-bb9c-6776552e3368",
  "status": "cancelled",
  "access_valid_until": "2027-11-16T12:00:00Z",
  "message": "Subscription cancelled. Access remains active until the end of your billing cycle."
}
```

---

## 3. Checkout & Payment Verification

### `POST /api/v1/billing/checkout/create-order/`
- **Access:** Authenticated (`OWNER` or `ADMIN` only)
- **Headers:** `X-Company-ID: <UUID>`
- **Request Body:**
```json
{
  "plan_id": "pro_ai"
}
```
- **Response `201 Created`:**
```json
{
  "success": true,
  "checkout": {
    "order_id": "order_d3c74a24bdfd4e",
    "amount": 306682,
    "currency": "INR",
    "key_id": "rzp_test_srilekh_staging",
    "transaction_number": "TXN-A8D77291617B",
    "plan": {
      "id": "pro_ai",
      "name": "Pro AI",
      "total_amount_rupees": 3066.82,
      "billing_interval": "annual"
    },
    "company": {
      "id": "82b27a6b-6c8b-4b1a-b0df-6d3b89526939",
      "name": "Precision Agro Traders",
      "email": "owner@precisionagro.in"
    }
  }
}
```

### `POST /api/v1/billing/checkout/verify/`
- **Access:** Authenticated (`OWNER` or `ADMIN` only)
- **Headers:** `X-Company-ID: <UUID>`
- **Request Body:**
```json
{
  "razorpay_order_id": "order_d3c74a24bdfd4e",
  "razorpay_payment_id": "pay_f88589bdf58d4d",
  "razorpay_signature": "4a7336a53da234a9844e138be780760e1d087799e46a788bbd431fcf3bba223b"
}
```
- **Response `200 OK`:**
```json
{
  "success": true,
  "subscription_id": "751dfb22-6461-41f0-afbd-a0d122de54c2",
  "plan_id": "pro_ai",
  "plan_name": "Pro AI",
  "status": "active",
  "current_period_end": "2027-11-16T12:00:00Z",
  "invoice_number": "SL-INV-202611-0001",
  "transaction_number": "TXN-A8D77291617B"
}
```

---

## 4. Invoices & Download

### `GET /api/v1/billing/invoices/`
- **Access:** Authenticated (`IsAuthenticated`, `IsCompanyMember`)
- **Headers:** `X-Company-ID: <UUID>`
- **Description:** Returns all issued subscription tax invoices for the workspace.

### `GET /api/v1/billing/invoices/<uuid:invoice_id>/download/`
- **Access:** Authenticated (`IsAuthenticated`, `IsCompanyMember`)
- **Headers:** `X-Company-ID: <UUID>`
- **Description:** Streams official PDF for the requested invoice. Strictly prevents IDOR by verifying company ownership.
- **Response:** `200 OK`, `Content-Type: application/pdf`, `Content-Disposition: attachment; filename="SL-INV-202611-0001.pdf"`

---

## 5. Webhook

### `POST /api/v1/billing/webhooks/razorpay/`
- **Access:** Public (`AllowAny`, no CSRF)
- **Headers:** `X-Razorpay-Signature: <HMAC-SHA256>`
- **Payload:** Raw Razorpay webhook event JSON.
- **Security:** Verifies cryptographic signature against `RAZORPAY_WEBHOOK_SECRET` before processing. Idempotent against duplicate event IDs.
