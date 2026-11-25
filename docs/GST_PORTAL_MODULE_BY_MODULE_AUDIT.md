# SriLekh GST Portal Module-by-Module Audit

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Branch:** `audit/round-2.4.6-gst-integration-reliability`  
**Audit Date:** November 25, 2026  
**Auditor:** Principal Django/PostgreSQL Engineer & GST Compliance Architect  

---

## 1. Audit Scope & Methodology

This audit examines every GST portal-related module and service in the SriLekh codebase. Each module is evaluated across its complete vertical slice:
`Frontend UI -> API Endpoint -> Service Layer -> Provider / Gateway Adapter -> Database Persistence -> Audit Trail`

### Implementation Classification Standards
To maintain complete integrity, each module is assigned an authoritative implementation status:
- **LIVE GSP CONNECTED**: Active integration with a certified GST Suvidha Provider (GSP/ASP) communicating with live GSTN.
- **SANDBOX CONNECTED**: Operational integration with an approved developer sandbox (e.g. `api.sandbox.co.in`, Quicko Sandbox).
- **OFFLINE COMPLIANT**: Validated statutory file generation conforming to government JSON/Excel schemas for portal upload.
- **ERP INTERNAL**: High-integrity double-entry calculation, ledger posting, and reconciliation within SriLekh's engine.
- **MOCK / SIMULATED**: Deterministic algorithmic sandbox for automated unit and integration tests.
- **UNIMPLEMENTED**: No live government API connection exists in the current release.

---

## 2. Comprehensive Module-by-Module Audit Matrix

### Module 1: GST Portal Connection & Authentication
- **Implementation Status**: **SANDBOX CONNECTED** (Quicko Sandbox) / **OFFLINE COMPLIANT**
- **Frontend Path**: `frontend/src/app/gst/returns/page.tsx` (Portal Modal), `frontend/src/app/gst/page.tsx`
- **API Endpoints**:
  - `GET /api/v1/gst/portal/preflight/<company_id>/`
  - `POST /api/v1/gst/portal/request-otp/`
  - `POST /api/v1/gst/portal/verify-otp/`
  - `POST /api/v1/gst/portal/refresh/`
  - `POST /api/v1/gst/portal/disconnect/`
- **Service Layer**: `GSTPortalService` (`apps/gst/services/gst_sandbox_service.py`), `SandboxGSTClient` (`apps/gst/services/sandbox_client.py`)
- **Gateway Adapter**: `QuickoSandboxProvider`, `SandboxGSTClient`
- **Database Persistence**: `GSTRegistration.auth_token`, `GSTRegistration.token_expires_at`, `CompanyGSTConfig`
- **Audit Logging**: `GSTAuditLog` records every preflight, request, verify, refresh, and disconnect event.
- **Reality Statement**: Establishes genuine authenticated sessions against Sandbox by Quicko (`api.sandbox.co.in`). Does not communicate directly with `api.gst.gov.in` without an enterprise GSP production license.

---

### Module 2: OTP Generation, Delivery, Verification & Expiry
- **Implementation Status**: **SANDBOX CONNECTED**
- **Frontend Path**: `frontend/src/app/gst/returns/page.tsx` (Step 1 Credentials -> Step 2 OTP Verify)
- **API Endpoints**:
  - `POST /api/v1/gst/portal/request-otp/`
  - `POST /api/v1/gst/portal/verify-otp/`
- **Service Layer**: `GSTPortalService.request_portal_otp()`, `GSTPortalService.verify_portal_otp()`
- **Security & Rate Controls**:
  - 30-second atomic cooldown (`gst_otp_cd_{company}_{gstin}`)
  - Hourly rate limit (maximum 5 requests per hour per company/GSTIN)
  - Cryptographic challenge binding (`CHAL-...`) with 10-minute TTL in cache
  - Brute-force lockout after 5 incorrect OTP attempts
- **Reality Statement**: In sandbox mode, OTPs are delivered via Sandbox by Quicko API responses or simulated for test accounts. Real-world mobile/email OTP dispatch to taxpayers requires live GSTN GSP routing with API access enabled on `gst.gov.in`.

---

### Module 3: GST Registration & Taxpayer Information Retrieval
- **Implementation Status**: **SANDBOX CONNECTED** / **LIVE GSP CAPABLE**
- **Frontend Path**: `frontend/src/app/gst/page.tsx` (Lookup Tab & Registrations View)
- **API Endpoints**:
  - `GET /api/v1/gst/lookup/<gstin>/`
  - `POST /api/v1/gst/verify-gstin/`
  - `POST /api/v1/gst/party/enrich/`
  - `GET/POST /api/v1/gst/registrations/<company_id>/`
  - `POST /api/v1/gst/registrations/<company_id>/<pk>/verify/`
- **Service Layer**: `SandboxGSTClient.search_taxpayer()`, `GSTINLookupService`, `GSTINValidator`
- **Gateway Adapter**: `QuickoSandboxProvider` (primary), `GSPProvider` (Cashfree verification), `MockGSTProvider` (fallback)
- **Database Persistence**: `GSTRegistration`, `GSTTaxpayerCache` (30-day cached profiles)
- **Audit Logging**: `GSTAuditLog` logs verification requests and party enrichment diffs.
- **Reality Statement**: Fully functional for live taxpayer verification and party legal name / address auto-population using Sandbox by Quicko and Cashfree GSTIN verification APIs.

---

### Module 4: GSTR-1 Outward Supplies
- **Implementation Status**: **OFFLINE COMPLIANT** (GSTN Schema v3.1.2) / **ERP INTERNAL**
- **Frontend Path**: `frontend/src/app/gst/page.tsx` (GSTR-1 Tab), `frontend/src/app/gst/returns/page.tsx`
- **API Endpoints**:
  - `GET /api/v1/gst/returns/gstr1/<company_id>/`
  - `POST /api/v1/gst/returns/gstr1/submit/<company_id>/`
  - `GET /api/v1/gst/reports/gstr1/<company_id>/`
  - `POST /api/v1/gst/workspace/<company_id>/export/`
- **Service Layer**: `GSTRReportService.generate_gstr1()`, `GSTWorkspaceService`
- **Data Sections Covered**:
  - Table 4: B2B Invoices (inter-state & intra-state)
  - Table 5: B2CL (Large Invoices > ₹2.5 Lakhs inter-state)
  - Table 7: B2CS (Small Invoices & Consumer Supplies)
  - Table 9B: CDNR (Registered Credit/Debit Notes)
  - Table 9B: CDNUR (Unregistered Credit/Debit Notes)
  - Table 12: HSN Summary of Outward Supplies
- **Direct Portal Upload Safeguard**: Direct API transmission (`GSTRDirectPortalUploadGSTR1APIView`) is blocked from live government filing by `LiveFilingProhibitedError`. Generates official offline `.json` files uploadable via `gst.gov.in`.

---

### Module 5: GSTR-3B Monthly Return Summary
- **Implementation Status**: **OFFLINE COMPLIANT** / **ERP INTERNAL**
- **Frontend Path**: `frontend/src/app/gst/page.tsx` (GSTR-3B Tab), `frontend/src/app/gst/returns/page.tsx`
- **API Endpoints**:
  - `GET /api/v1/gst/returns/gstr3b/<company_id>/`
  - `GET /api/v1/gst/reports/gstr3b/<company_id>/`
- **Service Layer**: `GSTRReportService.generate_gstr3b_report()`, `GSTWorkspaceService`
- **Statutory Computation Engine**:
  - Table 3.1: Tax on Outward and Reverse Charge Inward Supplies
  - Table 4: Eligible ITC & Reversals (Table 4A Inward supplies, Table 4B1 Blocked credits under Sec 17(5), Table 4B2 Rule 37 & 37A statutory reversals, Table 4D Ineligible credits)
  - Table 5: Values of Exempt, Nil-rated, and Non-GST Inward Supplies
  - Table 6.1: Tax Payment & Rule 88A Cross-Head Set-Off (IGST -> CGST -> SGST waterfall)
- **Reality Statement**: Complete mathematical and statutory formulation computed from double-entry ledger vouchers. Exports both statutory JSON and human review PDF/reports. Live portal submission is disabled.

---

### Module 6: GSTR-2A & GSTR-2B Inward Statements
- **Implementation Status**: **SANDBOX CONNECTED** (Sync) / **OFFLINE COMPLIANT** (XLSX/ZIP Ingestion)
- **Frontend Path**: `frontend/src/app/gst/page.tsx` (Reconciliation Tab), `frontend/src/app/gst/itc-shield/page.tsx`
- **API Endpoints**:
  - `POST /api/v1/gst/itc/upload-2b/`
  - `POST /api/v1/gst/reconciliation/<company_id>/upload-2b/`
  - `POST /api/v1/gst/reconciliation/gstr2b/sync/<company_id>/`
- **Service Layer**: `GSTR2BUploadView`, `SandboxGSTClient.get_gstr2b_data()`
- **Ingestion Security**:
  - Strict file validation: Magic byte validation for XLSX/ZIP, zip-bomb decompression protection (100MB uncompressed limit, max 50 entries)
  - Duplicate ingestion prevention: Computes SHA-256 payload hash and locks ingestion per `(company, return_period, gstin)`
- **Database Persistence**: `GSTR2BImport`, `GSTR2BRecord` (invoice-by-invoice line items with filing status)

---

### Module 7: ITC Reconciliation (Vendor ITC Risk Shield)
- **Implementation Status**: **ERP INTERNAL** (Production Certified)
- **Frontend Path**: `frontend/src/app/gst/itc-shield/page.tsx`
- **API Endpoints**:
  - `GET /api/v1/gst/itc/reconciliation/`
  - `POST /api/v1/gst/itc/reconcile-now/`
  - `POST /api/v1/gst/itc/attribute-voucher/`
  - `POST /api/v1/gst/itc/correct-attribution/`
  - `POST /api/v1/gst/itc/hold-gst/`
  - `GET /api/v1/gst/itc/vendor-notice/<voucher_id>/`
- **Key Capabilities**:
  - 11 statutory matching categories (MATCHED, MISMATCHED, MISSING_IN_2B, MISSING_IN_BOOKS, REVIEW_REQUIRED, AMENDED, etc.)
  - QRMP Period Intelligence: Groups quarterly vendor vouchers (M1, M2, M3) against quarter-end GSTR-2B statements
  - CDNR Signed Math: Credit/Debit note sign normalization and mathematical net aggregation
  - Worker Exclusivity & Concurrency: Durable lease claim (`claimed_by`, `claim_token`, `generation`) preventing double execution
  - Background Recovery: Periodic Celery Beat recovery task (`recover_itc_reconciliation_jobs_task` every 60s)
  - Smart GST Payment Hold: Withholds tax payment until vendor GSTR-1 is reflected
  - WhatsApp Filing Chaser: 1-click wa.me chaser notice generator

---

### Module 8: E-Way Bill Lifecycle
- **Implementation Status**: **SANDBOX CONNECTED** / **MOCK CAPABLE**
- **Frontend Path**: `frontend/src/app/gst/page.tsx`, `EWayBillModal.tsx`
- **API Endpoints**:
  - `POST /api/v1/gst/ewaybill/generate/<voucher_id>/`
  - `POST /api/v1/gst/ewaybill/update-vehicle/<ewaybill_id>/`
  - `POST /api/v1/gst/ewaybill/cancel/<ewaybill_id>/`
  - `GET /api/v1/gst/eway-bill/voucher/<voucher_id>/`
- **Service Layer**: `EWayBillService`, `GSPProvider`
- **Features**: Part-A bill generation, Part-B transporter/vehicle update, statutory 24-hour cancellation with reason logging.
- **Reality Statement**: Operational via `MockGSTProvider` and configured GSP endpoints. In Quicko Sandbox mode, raises `ProductionSafetyViolationError` because Quicko Sandbox focuses on GSTIN lookup.

---

### Module 9: E-Invoice (IRP / IRN) Lifecycle
- **Implementation Status**: **SANDBOX CONNECTED** / **MOCK CAPABLE**
- **Frontend Path**: `frontend/src/app/gst/page.tsx` (E-Invoice Tab)
- **API Endpoints**:
  - `POST /api/v1/gst/einvoice/generate/<voucher_id>/`
  - `POST /api/v1/gst/einvoice/cancel/<voucher_id>/`
  - `GET /api/v1/gst/einvoice/voucher/<voucher_id>/`
- **Service Layer**: `EInvoiceService`, `GSPProvider`
- **Features**: Validates B2B invoice eligibility, constructs 64-character SHA-256 IRN hash, signed QR code, Ack Number, and Ack Date. Supports cancellation within 24 hours.

---

### Module 10: Electronic Cash Ledger
- **Implementation Status**: **ERP INTERNAL** (Ledger Accounting) / **UNIMPLEMENTED** (Direct Portal Sync)
- **Service Layer**: `apps/gst/services/returns_service.py` (Table 6.1 cash discharge)
- **Reality Statement**: SriLekh maintains double-entry accounting ledgers representing cash outlays for GST payments. However, direct real-time API synchronization with the government portal's Electronic Cash Ledger balance (`/taxpayerapi/v1.0/ledgers/cash`) is NOT implemented as a live automated API call.

---

### Module 11: Electronic Credit Ledger
- **Implementation Status**: **ERP INTERNAL** (Ledger Accounting) / **UNIMPLEMENTED** (Direct Portal Sync)
- **Service Layer**: `apps/gst/services/returns_service.py`, `ITCReconciliationService`
- **Reality Statement**: ITC balances and reversals are calculated from posted purchase vouchers and GSTR-2B imports. Direct portal API synchronization of government Credit Ledger balances is NOT connected.

---

### Module 12: Electronic Liability Ledger
- **Implementation Status**: **ERP INTERNAL** (Ledger Accounting) / **UNIMPLEMENTED** (Direct Portal Sync)
- **Service Layer**: `apps/gst/services/returns_service.py` (Table 3.1 & Table 6.1 offset waterfall)
- **Reality Statement**: Liabilities are tracked in double-entry sales registers and output tax ledgers. Automated live query of government Part I & Part II liability registers via GSP is not implemented.

---

### Module 13: GST Payment & Challan Functionality
- **Implementation Status**: **ERP INTERNAL** (Evidence Tracking) / **UNIMPLEMENTED** (Direct PMT-06 API)
- **Models**: `Rule37AEvidenceRecord` (`TAX_CHALLAN_CIN`), `accounting.PaymentAllocation`
- **Reality Statement**: SriLekh supports recording Challan CIN (Challan Identification Number) as documentary proof for Rule 37A reclaim and tracks ERP bank payments. Direct generation of PMT-06 challans or integrated net-banking payments on `gst.gov.in` is NOT supported via API.

---

### Module 14: Return Filing Status & Acknowledgements (ARN)
- **Implementation Status**: **SANDBOX CONNECTED** / **ERP INTERNAL**
- **Frontend Path**: `frontend/src/app/gst/returns/page.tsx`
- **API Endpoints**:
  - `GET /api/v1/gst/portal/status/<company_id>/<ref_id>/`
  - `POST /api/v1/gst/returns/mark-filed/<company_id>/`
- **Service Layer**: `GSTPortalService.get_portal_status()`, `Rule37AEvidenceService`
- **Integrity Invariant**: Enforces strict verification of official government ARNs. Prohibits dummy or fabricated ARNs (`"REF-G1-..."`). Preserves verified ARNs immutably once recorded.

---

### Module 15: Notices, Demands & Statutory Exception Services
- **Implementation Status**: **ERP INTERNAL**
- **Frontend Path**: `frontend/src/app/gst/itc-shield/page.tsx`
- **API Endpoints**:
  - `GET /api/v1/gst/returns/exceptions/<company_id>/`
  - `GET /api/v1/gst/itc/vendor-notice/<voucher_id>/`
- **Capabilities**:
  - Pre-filing statutory validation exceptions (invalid GSTIN, missing HSN, tax rate mismatch)
  - Automated WhatsApp filing chaser generation
  - Statutory 180-day non-payment tracker (Rule 37) and supplier GSTR-3B default tracker (Rule 37A)
  - Direct retrieval of government DRC-01 / DRC-07 notices via API is not connected.

---

## 3. Module Audit Summary Matrix

| # | GST Module | Implementation Category | Live API Status | Production Readiness |
|---|---|---|---|---|
| 1 | Portal Connection & Auth | Sandbox GSP | Sandbox.co.in active | Ready (Sandbox / GSP) |
| 2 | OTP Lifecycle | Sandbox GSP / Cache | Sandbox.co.in active | Ready (Requires GSP for SMS) |
| 3 | GSTIN Lookup & Taxpayer Info | Sandbox GSP / Cashfree | Live verified | **Production Ready** |
| 4 | GSTR-1 Outward Supplies | Offline JSON / ERP | GSTN Schema v3.1.2 | **Production Ready** |
| 5 | GSTR-3B Monthly Returns | Offline JSON / ERP | GSTN Spec v1.4 | **Production Ready** |
| 6 | GSTR-2B Inward Statements | Ingestion (XLSX/ZIP) | Sync + File Ingestion | **Production Ready** |
| 7 | ITC Risk Shield | ERP Internal Engine | High-performance DB | **Production Ready** |
| 8 | E-Way Bill Lifecycle | Sandbox / Mock | GSP Router | Ready (Sandbox / GSP) |
| 9 | E-Invoice Lifecycle | Sandbox / Mock | GSP Router | Ready (Sandbox / GSP) |
| 10 | Electronic Cash Ledger | ERP Ledger Accounting | No direct API | ERP Ready / Portal Manual |
| 11 | Electronic Credit Ledger | ERP Ledger Accounting | No direct API | ERP Ready / Portal Manual |
| 12 | Electronic Liability Ledger| ERP Ledger Accounting | No direct API | ERP Ready / Portal Manual |
| 13 | Payment & Challan Tracking | Documentary CIN Proof | No direct PMT-06 | ERP Ready / Portal Manual |
| 14 | Filing Status & ARN | Reference Reconciler | Sandbox / Manual | **Production Ready** |
| 15 | Notices & Pre-filing Rules | ERP Statutory Guard | Internal Engine | **Production Ready** |
