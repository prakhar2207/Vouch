# SriLekh — Sandbox by Quicko GST Integration Architecture

## 1. Executive Summary

This document specifies the technical and operational architecture for integrating **Sandbox by Quicko** (`https://sandbox.co.in`, `https://developer.sandbox.co.in`) into **SriLekh**, an MSME Accounting and Business Management SaaS platform.

The integration provides Indian MSMEs, retailers, wholesalers, and distributors with automated GST compliance, including:
1. Real-time GSTIN validation and Party Master enrichment.
2. Comprehensive GSTR-1 return preparation, JSON generation, and direct submission.
3. GSTR-3B tax liability computation and Input Tax Credit (ITC) optimization.
4. GSTR-2B automated reconciliation against accounting purchase vouchers with 11-category classification.
5. Statutory e-Invoice (IRP/NIC Schema v1.1) generation, QR code storage, and 24-hour statutory cancellation.
6. E-Way Bill (Part-A and Part-B) generation, vehicle updates, and cancellations.

All GST operations are architected as an **additive compliance layer** that strictly preserves SriLekh's immutable double-entry accounting engine. Under no circumstances does any GST API interaction mutate financial vouchers, ledger balances, trial balances, or inventory stock levels.

---

## 2. High-Level System Architecture

```
+----------------------------------------------------------------------------------------------------+
|                                      SRILEKH FRONTEND (Next.js)                                    |
|   - Multi-GSTIN Switcher             - GSTIN Verification Dialog     - GSTR-1 Workspace            |
|   - GSTR-2B Reconciliation Console   - e-Invoice / EWB Manager       - Compliance Audit Viewer     |
+----------------------------------------------------------------------------------------------------+
                                                  │ HTTPS / REST (JWT Session)
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                    SRILEKH BACKEND (Django REST)                                   |
|   apps/gst/                                                                                        |
|   ├── permissions.py          (HasGSTPermission, Tenant Isolation, RBAC)                           |
|   ├── views.py                (REST Endpoints for Registrations, Returns, e-Invoice, EWB, Recon)   |
|   ├── serializers.py          (Validation, Serializers, Masked Field Transformers)                 |
|   └── services/                                                                                    |
|       ├── sandbox_client.py   (Quicko API Client: JWT Exchange, Auth, Retries, Session Tokens)     |
|       ├── gstin_service.py    (Luhn MOD-36 Checksum, Public Search, 24-hr Caching, Enrichment)    |
|       ├── returns_service.py  (GSTR-1 Tables B2B/B2CL/B2CS/CDNR/HSN/DOCS, GSTR-3B Table 3.1 & 4)   |
|       ├── reconciliation_service.py (11 Mismatch Categories, GSTR-2B Ingest, Action Workflow)      |
|       ├── einvoice_service.py (IRP v1.1 Schema, Eligibility Guard, Idempotency, 24-hr Cancel)     |
|       ├── ewaybill_service.py (Part-A, Part-B, Distance Calculation, Vehicle Update, Cancel)      |
|       └── audit_service.py    (Tamper-evident GSTAuditLog, Sensitive Credential Redaction)         |
+----------------------------------------------------------------------------------------------------+
           │                                                                      │
           │ ORM (PostgreSQL)                                                     │ HTTPS (x-api-key)
           ▼                                                                      ▼
+─────────────────────────────────+                    +─────────────────────────────────────────────+
|    POSTGRESQL DATABASE (Neon)   |                    |           SANDBOX BY QUICKO API             |
| - gst_registration              |                    |  Base URL: https://api.sandbox.co.in        |
| - gst_companygstconfig          |                    |  Test URL: https://test-api.sandbox.co.in   |
| - gst_taxpayer_cache            |                    |                                             |
| - gst_filing_record             |                    |  Endpoints:                                 |
| - gst_gstr2b_import / record    |                    |  - POST /authenticate                       |
| - gst_einvoice_record           |                    |  - POST /gst/compliance/public/gstin/search |
| - gst_ewaybill_record           |                    |  - POST /gst/compliance/tax-payer/otp       |
| - gst_audit_log                 |                    |  - POST /gst/compliance/e-invoice/...       |
+─────────────────────────────────+                    |  - GET  /gst/compliance/tax-payer/gstrs/... |
                                                       +─────────────────────────────────────────────+
```

---

## 3. Multi-Tenant & Multi-GSTIN Data Architecture

In India, a single legal enterprise may maintain distinct GST registrations across multiple states (e.g., Delhi `07...`, Maharashtra `27...`, Uttar Pradesh `09...`). Each registration has its own state jurisdiction, turnover threshold, e-invoicing mandate, and filing obligations.

### Data Model Hierarchy
```
Company (Tenant)
  │
  ├── CompanyGSTConfig (Encrypted Provider Credentials, Global Sandbox Settings)
  │
  ├── GSTRegistration [1..N] (State-level GSTIN, e-Invoice / EWB credentials)
  │     ├── EInvoiceRecord [0..N] (IRN, Signed QR, Ack No, Linked to Sales Voucher)
  │     ├── EWayBillRecord [0..N] (EWB No, Valid Upto, Vehicle No, Linked to Voucher)
  │     ├── GSTR2BImport [0..N] (Period-level GSTR-2B Batch Import)
  │     │     └── GSTR2BRecord [0..N] (Individual 2B line item with mismatch categorization)
  │     └── GSTFilingRecord [0..N] (Return Period, Form GSTR1/3B, SHA-256 Payload Hash, State)
  │
  └── GSTAuditLog [0..N] (Audit trail with fully redacted secrets and request metadata)
```

### Tenant Isolation Guarantee
1. **Model Layer**: Every GST table directly references `company_id` (ForeignKey with cascading deletion protections).
2. **View Layer**: `HasGSTPermission` checks company ownership, active tenant context (`X-Company-ID` or request URL parameter), and verifies user authorization.
3. **Database Querying**: All queries filter strictly on `company=request.company`. No tenant can query or view registrations, filings, or records of another tenant.

---

## 4. Request-Response Lifecycle & Auth Flow

### Quicko Sandbox Authentication Flow
```
SriLekh Backend                                                    Sandbox by Quicko
      │                                                                    │
      │ 1. POST /authenticate                                              │
      │    Headers: x-api-key, x-api-secret, x-api-version: 1.0.0          │
      ├───────────────────────────────────────────────────────────────────>│
      │                                                                    │
      │ 2. Return access_token (JWT, valid ~24h)                           │
      │<───────────────────────────────────────────────────────────────────┤
      │                                                                    │
      │ [Cache access_token in CompanyGSTConfig or Redis]                  │
      │                                                                    │
      │ 3. POST /gst/compliance/public/gstin/search                        │
      │    Headers: authorization: <access_token>, x-api-key, x-api-ver    │
      │    Body: {"gstin": "27AADCB2230M1ZT"}                              │
      ├───────────────────────────────────────────────────────────────────>│
      │                                                                    │
      │ 4. Return Taxpayer JSON Profile                                    │
      │<───────────────────────────────────────────────────────────────────┤
```

### Taxpayer Portal Session Flow (Filing / Returns / e-Invoice)
For operations requiring direct taxpayer credentials on the government portal (e.g., GSTR-1 submit or live e-invoicing):
1. SriLekh calls Sandbox OTP trigger: `POST /gst/compliance/tax-payer/otp`.
2. The taxpayer receives an official OTP on their GST-registered mobile number/email.
3. The user inputs the OTP in SriLekh; backend submits: `POST /gst/compliance/tax-payer/otp/verify`.
4. Sandbox returns a `taxpayer_session_token`, encrypted at rest and stored in `GSTRegistration.auth_token` for the 6-hour session window.

---

## 5. Caching Strategy & Rate Limit Mitigation

| Resource | Cache Store | TTL | Invalidation Trigger |
| :--- | :--- | :--- | :--- |
| **Sandbox Access Token** | DB / Cache | 23 Hours | 401 Unauthorized response from provider |
| **Public GSTIN Profile** | `GSTTaxpayerCache` | 24 Hours | Manual refresh click or status change |
| **GSTR-1 Computed Tables** | Application Memory | Request scope | Any sales voucher create/post/cancel |
| **GSTR-2B Auto-Match** | `GSTR2BRecord` | Persistent | New sync or user manual override |

---

## 6. Async vs Synchronous Execution Boundaries

1. **Synchronous (HTTP Request/Response)**:
   - GSTIN Verification (latency ~300ms–800ms)
   - Party Master Enrichment Preview & Apply
   - GSTR-1 Preview & Summary Computation
   - GSTR-3B Tax Summary Computation
   - Single e-Invoice Generation / Cancellation (statutory requirement: immediate IRN on invoice print)
   - Single E-Way Bill Generation / Vehicle Update

2. **Asynchronous (Celery Outbox / Worker)**:
   - Bulk GSTR-2B synchronization from Sandbox (can contain 5,000+ invoices)
   - Nightly 2B matching against posted purchase vouchers
   - GSTR-1 multi-invoice bulk batch submission
   - Compliance audit log archival and log maintenance

---

## 7. Error Handling & Circuit Breaking

1. **Deterministic Input Errors (400 / 422)**:
   - Invalid GSTIN format, invalid HSN code, missing line items: Surface directly to user with actionable localized error messages.
2. **Authentication Errors (401 / 403)**:
   - Automatic invalidation of cached JWT `access_token`, immediate re-authentication attempt against `/authenticate`, and single retry.
3. **Provider Rate Limiting (429)**:
   - Exponential backoff with jitter (`backoff_factor=1.5`, up to 3 retries).
4. **Network / Server Faults (500 / 502 / 503 / 504)**:
   - Fall back gracefully to local cached taxpayer data or offline preparation mode.

---

## 8. Summary of Compliance Architecture

| Architectural Principle | Implementation Standard |
| :--- | :--- |
| **Accounting Non-Interference** | Read-only extraction from accounting tables; zero voucher mutations |
| **Statutory Alignment** | Strict adherence to NIC/IRP Schema v1.1 and GST Rules 48(4) & 138 |
| **Zero Credential Leaks** | Encryption at rest (Fernet/AES-256); mandatory redaction in all logs |
| **Tenant Isolation** | Schema-level multi-tenancy enforced at model, serializer, and view tiers |
