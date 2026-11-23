# SRI LEKH — GST SIMPLIFIED ONBOARDING AUDIT
**Date**: November 23, 2026  
**Auditor**: Principal Product Architect & Senior GST Backend Engineer  
**System**: SriLekh ERP (`https://srilekh.com`)  
**Repository**: `https://github.com/prakhar2207/Vouch`  

---

## 1. Executive Summary & Defect Root Causes

SriLekh's core mission is to provide **"Accounting flexibility like Tally, with the simplicity of modern business software."**
Ordinary business owners (kirana merchants, textile retailers, wholesale distributors, and MSME accountants) must never be confronted with raw technical infrastructure details, API keys, HTTP headers, backend provider names, or cryptographic exceptions.

An audit of the previous GST Portal Direct Connect interface revealed critical violations of abstraction and usability:

| # | Previous Defect Identified | Root Cause | Business Impact | Remediated Status |
|---|-----------------------------|------------|-----------------|-------------------|
| 1 | Infrastructure leaks ("Render Platform Environment Credentials Active LIVE API READY", "api.sandbox.co.in") | Diagnostic status flags were directly rendered to customer-facing UI components | Confused non-technical shop owners; leaked backend architecture | **Completely Removed**; replaced with clean "Government GST Portal" branding |
| 2 | Developer "Test Connection" button beside OTP button | Developer diagnostic ping endpoint was exposed to production users | Users clicked "Test Connection" expecting it to log them in, causing confusion | **Removed from production UI**; restricted to developer diagnostics |
| 3 | Leaked raw provider error: `Missing required request parameters: [x-source]` | Missing `x-source: primary` header on sandbox client request + raw unhandled exception bubble-up | Users saw cryptic HTTP header errors instead of actionable guidance | **Fixed**: `x-source: primary` injected, and all errors normalized with classification |
| 4 | React Hydration Error #418 | SSR vs Client timezone/date string mismatch on `portalExpiresAt` | DevTools console red error, UI blinking during hydration | **Fixed**: Protected date formatting with `mounted` state check & `suppressHydrationWarning` |
| 5 | No guided onboarding when GST Portal API access was disabled | Taxpayers disabling API access on `services.gst.gov.in` received generic or cryptic failures | Users were stuck without knowing what button to click on the government portal | **Fixed**: Intelligent detection (`API_ACCESS_DISABLED`) with direct portal link and 4-step checklist |

---

## 2. Technical and Customer Abstraction Boundaries

The system now enforces strict three-tier abstraction:

```
[ FRONTEND UI (Zero Technical Details) ]
   │
   ▼
[ BACKEND SERVICE LAYER (GSTPortalService & Error Normalizer) ]
   │
   ▼
[ EXTERNAL PROVIDER INTEGRATION (Sandbox.co.in / Quicko Empaneled GSP Gateway) ]
```

1. **Frontend Presentation Tier**:
   - Displays only: Company Name, GSTIN, Connection State (`Connected` vs `Not Connected`), Session Expiry, and OTP input.
   - Zero mention of: Quicko, Sandbox.co.in, Render, API Keys, Secrets, Bearer tokens, or endpoints.
2. **Business Logic & Error Normalization Tier**:
   - `get_structured_gst_error()` maps external HTTP responses to semantic codes: `API_ACCESS_DISABLED`, `GSP_AUTH_MISSING`, `INVALID_USERNAME`, `INCORRECT_OTP`, `EXPIRED_OTP`, `EXPIRED_SESSION`, `PROVIDER_OUTAGE`.
   - Internal technical parameters (headers, correlation IDs, status codes) are logged securely in server logs and masked from the customer.
3. **Data Protection Tier**:
   - GST portal session tokens (`auth_token`) and encryption keys (`SEK`) are stored encrypted at rest, isolated per tenant company, and never transmitted to the frontend.

---

## 3. Preflight & Intelligent Error Routing Architecture

Before initiating an OTP request, the application performs automatic preflight validation:
- Validates that the entity has a valid 15-character GSTIN.
- Detects whether an active session already exists.
- If API access is disabled on the GST Portal, delivers actionable instructions:
  - Official Portal URL: `https://services.gst.gov.in`
  - Empaneled GSP Legal Name: `Quicko Infosoft Private Limited`
  - Direct retry without page reloads.

---

## 4. Audit Sign-off

- [x] All customer-facing technical leaks removed.
- [x] Test connection button removed from production.
- [x] Missing `x-source` parameter resolved and shielded.
- [x] React Hydration mismatch #418 resolved.
- [x] Non-technical retail UX verified and validated.
