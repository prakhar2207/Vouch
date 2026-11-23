# SRI LEKH — GST SANDBOX GSP/ASP AUTHORIZATION REPORT
**Date**: November 23, 2026  
**Provider**: Sandbox by Quicko (`https://console.sandbox.co.in/`)  
**Official Docs**: `https://sandbox-docs.readme.io/reference/gst-taxpayer-authentication`  
**System Target**: SriLekh ERP (`https://srilekh.com`)  

---

## 1. Provider Empanelment & Legal Entities

### 1.1 Exact GSP Legal Name
- **GSP Legal Name**: `Quicko Infosoft Private Limited`
- **GSTN Empanelment**: Quicko is a GSTN-empaneled Goods and Services Tax Suvidha Provider (GSP).
- **Official Portal Identifier**: On `https://services.gst.gov.in`, under **Manage API Access**, taxpayers selecting a third-party GSP must choose:
  ```
  Quicko Infosoft Private Limited
  ```

### 1.2 Exact ASP Legal Name
- **ASP Name**: `Quicko Infosoft Private Limited` / `Sandbox by Quicko`.

### 1.3 SriLekh ASP Registration Requirement
- **Requirement**: **NOT REQUIRED**.
- **Reasoning**: Quicko operates as the empaneled GSP and API Gateway. SriLekh authenticates to Sandbox using organizational API credentials (`x-api-key` and `authorization: Bearer <access_token>`). Quicko bridges the taxpayer consent and OTP challenge directly to GSTN. SriLekh does not require separate direct GSTN empanelment.

---

## 2. Taxpayer Consent & Authorization Workflow

### 2.1 Is Taxpayer Consent Mandatory?
- **YES**. Under GSTN security regulations, automated API access to return filing, ITC 2B data, and ledger ledgers requires active taxpayer consent.
- Direct password authentication to SriLekh is strictly prohibited. All authentication is OTP-based.

### 2.2 Is "Enable API Request" Alone Sufficient?
- **YES**. On the Government GST Portal (`https://services.gst.gov.in`):
  1. Setting **Enable API Request** to **Yes**.
  2. Selecting **Duration** (recommended: **30 days**).
  3. Selecting GSP **Quicko Infosoft Private Limited** (if prompted).
  4. Clicking **Confirm**.
- Once confirmed on the GST Portal, requesting OTP via `POST /gst/compliance/tax-payer/otp` successfully dispatches the GSTN OTP to the taxpayer's registered mobile/email.

### 2.3 Taxpayer Consent Verification Mechanism
When SriLekh calls:
```http
POST https://api.sandbox.co.in/gst/compliance/tax-payer/otp
x-api-key: <key>
authorization: <token>
x-source: primary
x-api-version: 1.0.0
Content-Type: application/json

{
  "username": "<taxpayer_username>",
  "gstin": "<taxpayer_gstin>"
}
```
1. Sandbox forwards the request to GSTN.
2. GSTN validates that the taxpayer has enabled API access on their profile.
3. If disabled, GSTN immediately responds with error code `API_ACCESS_DISABLED` or `GSP_AUTH_MISSING`.
4. If enabled, GSTN sends an SMS OTP to the taxpayer's registered mobile number.

---

## 3. Visual Taxpayer Guidance Matrix

When SriLekh detects that API access is not yet enabled for a taxpayer's GSTIN, it displays the following step-by-step visual guidance:

```
┌────────────────────────────────────────────────────────────────────────┐
│  ⚠ Action Required on Government GST Portal                            │
│  GST API access is currently disabled for this GST registration.       │
│  Please enable API access in your GST Portal account and try again.     │
│                                                                        │
│  Follow these 4 simple steps:                                          │
│  1. Sign in to your GST Portal account at services.gst.gov.in          │
│  2. Go to My Profile > Manage API Access                               │
│  3. Select Yes for 'Enable API Request' and choose 30 days             │
│  4. If prompted for GSP, choose Quicko Infosoft Private Limited        │
│                                                                        │
│  [ Open Government GST Portal ↗ ]   [ I've enabled API access — Retry ]│
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Summary of Provider API Endpoints

| Operation | Sandbox.co.in Endpoint | Method | Required Headers | Payload |
|---|---|---|---|---|
| Generate Taxpayer OTP | `/gst/compliance/tax-payer/otp` | POST | `x-source`, `x-api-key`, `authorization` | `{"username": ..., "gstin": ...}` |
| Verify Taxpayer OTP | `/gst/compliance/tax-payer/otp/verify?otp=<otp>` | POST | `x-source`, `x-api-key`, `authorization` | `{"username": ..., "gstin": ...}` |
| Refresh Session | `/gst/compliance/tax-payer/session/refresh` | POST | `x-source`, `x-api-key`, `authorization` | `{}` |
| Disconnect / Logout | `/gst/compliance/tax-payer/logout` | POST | `x-source`, `x-api-key`, `authorization` | `{}` |
