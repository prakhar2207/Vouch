# SriLekh GST Portal Integration Architecture Audit

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Branch:** `audit/round-2.4.6-gst-integration-reliability`  
**Baseline Commit:** `346d9a3e7db7b3315b402a43a97293058b3eec10`  
**Audit Date:** November 25, 2026  
**Auditor:** Principal Django/PostgreSQL Engineer & GST Compliance Architect  

---

## 1. Executive Summary & System Footprint

The SriLekh GST compliance ecosystem is designed to provide comprehensive Indian Goods and Services Tax (GST) capabilities for MSMEs, including multi-GSTIN registrations, outward supply reporting (GSTR-1), monthly statutory liability computation (GSTR-3B), inward invoice reconciliation (GSTR-2B & ITC Risk Shield), E-Way Bill lifecycle, and E-Invoice (IRP) generation.

This architectural audit evaluates SriLekh's complete GST subsystem to clearly establish:
1. What components are connected to live government / GSP APIs versus sandbox or mock providers.
2. The security and encryption boundary protecting taxpayer credentials.
3. The server-side production safety controls preventing unauthorized or accidental live return submission.
4. The database-level immutability guarantees enforcing Indian statutory accounting compliance.

### Integration Footprint Overview

| Component Layer | Technologies | Responsibilities | Key Source Files |
|---|---|---|---|
| **Frontend PWA** | Next.js 14, React, TailwindCSS, TypeScript | Compliance dashboard, multi-GSTIN selector, GSTR-1 & 3B review, ITC Risk Shield, E-Way Bill modal, Portal OTP modal | `frontend/src/app/gst/page.tsx`<br>`frontend/src/app/gst/returns/page.tsx`<br>`frontend/src/app/gst/itc-shield/page.tsx`<br>`frontend/src/lib/api/gst.ts` |
| **API Endpoints** | Django REST Framework (DRF) | Multi-GSTIN CRUD, taxpayer search, portal OTP endpoints, return exports, reconciliation APIs, attribution endpoints | `apps/gst/urls.py`<br>`apps/gst/views.py`<br>`apps/gst/itc_views.py` |
| **Service Layer** | Python 3.14, Django 5.x | Report generation, GSTIN validation, OTP challenge management, reconciliation engine, lease management | `apps/gst/services/gst_sandbox_service.py`<br>`apps/gst/services/sandbox_client.py`<br>`apps/gst/services/itc_reconciliation_service.py`<br>`apps/gst/services/itc_reconciliation_job_service.py` |
| **Gateway Adapters** | Provider Architecture (ABC) | Quicko Sandbox (`api.sandbox.co.in`), GSP Provider (Cashfree/Clear), Mock GST Provider | `apps/gst/services/providers/base.py`<br>`apps/gst/services/providers/quicko_provider.py`<br>`apps/gst/services/providers/gsp_provider.py`<br>`apps/gst/services/providers/mock_provider.py` |
| **Async Tasks** | Celery 5.x, Redis | Periodic reconciliation recovery (`recover_itc_reconciliation_jobs_task`), deadline notifications | `apps/gst/tasks.py`<br>`apps/gst/management/commands/recover_itc_reconciliation_jobs.py` |
| **Persistence & Audit** | PostgreSQL 18.7 (Neon) | Multi-GSTIN registrations, filing records, reconciliation jobs, tamper-evident audit logs with DB triggers | `apps/gst/models.py`<br>`apps/gst/migrations/` |

---

## 2. Gateway Abstraction Layer

SriLekh enforces a strict abstraction layer between high-level compliance workflows and external gateway providers using the `GSTGatewayProvider` abstract base class (`apps/gst/services/providers/base.py`).

```
                    +--------------------------------+
                    |       GSTGatewayProvider       |
                    |             (ABC)              |
                    +--------------------------------+
                                   ▲
         +-------------------------+-------------------------+
         |                         |                         |
+-------------------+     +-------------------+     +-------------------+
|  MockGSTProvider  |     |  QuickoSandbox    |     |    GSPProvider    |
|   (Deterministic  |     |     Provider      |     |  (Live/Sandbox    |
|   Local Testing)  |     | (Sandbox.co.in)   |     |    GSP Router)    |
+-------------------+     +-------------------+     +-------------------+
```

### 2.1 Factory Resolution (`get_gst_provider`)
Provider selection is resolved dynamically per tenant via `get_gst_provider(company)` (`apps/gst/services/providers/factory.py`):
1. If no company is provided or no `CompanyGSTConfig` exists: defaults to `MockGSTProvider()`.
2. If `config.provider == 'MOCK'`: returns `MockGSTProvider(config)`.
3. If `config.provider == 'SANDBOX_CO_IN'`: returns `QuickoSandboxProvider(config, company)`.
4. Otherwise (e.g. `CASHFREE`, `GSP_DIRECT`): returns `GSPProvider(config)`.

### 2.2 Explicit Capability Scoping (`GSTCapability`)
Every gateway operation requires an explicit capability declared in the provider:
- `GSTIN_LOOKUP`
- `EWAY_BILL_GENERATE`
- `EWAY_BILL_UPDATE_VEHICLE`
- `EWAY_BILL_CANCEL`
- `EINVOICE_GENERATE`
- `GSTR1_FILE` (Prohibited)
- `GSTR3B_FILE` (Prohibited)

Any attempt to call an unsupported or unpermitted capability immediately triggers a `ProductionSafetyViolationError` or `LiveFilingProhibitedError`.

---

## 3. Credential & Secret Management

Taxpayer credentials, GSP API keys, and session tokens are protected through defense-in-depth:

### 3.1 Storage & Encryption
1. **At-Rest Field Encryption**: Sensitive fields in `CompanyGSTConfig` (`api_key`, `api_secret`, `sandbox_api_key`, `sandbox_api_secret`, `eway_password`, `einvoice_password`) and `GSTRegistration` (`auth_token`) use AES-256-GCM authenticated encryption via `apps/gst/encryption.py`.
2. **Key Derivation**: Encryption keys are derived via PBKDF2 with SHA-256 and unique per-installation salts, never stored in plain text.
3. **Environment Fallback**: For developer convenience, API credentials can also be supplied via environment variables (`SANDBOX_API_KEY`, `SANDBOX_API_SECRET`), which are dynamically validated upon client initialization.

### 3.2 Redaction & API Masking
1. **In-Flight Logging Redaction**: `GSTGatewayProvider.redact_sensitive_data()` recursively scrubs sensitive keys (`password`, `api_secret`, `access_token`, `auth_token`, `otp`, `client_secret`) before any payload is recorded in logs or audit records.
2. **Client API Masking**: The `CompanyGSTConfigAPIView` GET endpoint never returns raw API keys or secrets. Masked values (e.g. `key_****`) and booleans (`has_sandbox_api_key`) are provided to the frontend.

---

## 4. Sandbox vs. Production Separation & Safety Controls

To eliminate the risk of automated tests or misconfigured deployments targeting live production GSTN endpoints or corrupting real taxpayer records, SriLekh implements multi-layered safety controls:

### 4.1 Strict Host Allowlisting (SSRF Shield)
`SandboxGSTClient` and `GSTGatewayProvider` enforce a strict HTTPS allowlist:
- `api.sandbox.co.in`
- `test-api.sandbox.co.in`
- `sandbox.cashfree.com`

Any target URL outside this allowlist is rejected with `SSRFHostViolationError` or automatically reset to the authoritative `DEFAULT_BASE_URL`.

### 4.2 Server-Side Live Filing Prohibition
Direct automated submission of live statutory returns (GSTR-1, GSTR-3B) to government GSTN endpoints is explicitly disabled by server-side policy (`LiveFilingProhibitedError`). 
- GSTR-1 outward reporting is generated as an official **GSTN Offline Tool Schema v3.1.2** JSON payload, allowing compliance officers to review and upload offline.
- GSTR-3B monthly liabilities are computed and exported as a statutory review guide and GSP/ASP Return Filing API Specification v1.4 payload.

### 4.3 Mandatory Test Isolation Invariant
All automated test scripts, mock generators, and benchmarks are strictly prohibited from touching real client accounts (e.g. `Maa Annapurna Belting Store`, ID `5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`). Tests run exclusively against the designated demo company:
- **Sandbox Company:** `Apex Belting & Industrial Store (Demo)`
- **Sandbox Company ID:** `4e62863a-08f9-4e99-b0bd-64873acfdd33`

---

## 5. Multi-GSTIN Tenant and Entity Isolation

SriLekh supports multi-state enterprises with multiple GSTINs under a single corporate umbrella.

1. **Strict Registration Scoping**: Each GSTIN is represented by a `GSTRegistration` model instance scoped to `(company, gstin)`.
2. **Session Token Isolation**: Session tokens (`auth_token`), username, and token expiration are maintained at the `GSTRegistration` level. GSTIN `A` cannot reuse or inherit session tokens from GSTIN `B`.
3. **Ambiguity Prevention**: If a company owns multiple active GSTIN registrations and an incoming request omits the specific `registration_id` or `gstin`, the system fails closed with `AMBIGUOUS_GSTIN` or requires designated primary registration resolution.
4. **Voucher Attribution Isolation**: Purchase vouchers are explicitly attributed to a single buyer GSTIN via `VoucherGSTINAttributionLog`, preventing cross-GSTIN ITC leakage.

---

## 6. Audit Trail & PostgreSQL Immutability Guarantees

SriLekh maintains tamper-evident audit trails with native PostgreSQL database triggers:

1. **Filing Frequency Trigger (`trg_prevent_direct_filing_frequency_mutation`)**:
   Blocks raw SQL `UPDATE`, Django `QuerySet.update()`, and `bulk_update()` on `gst_gstregistration.filing_frequency`. Only authorized execution via `GSTRegistration.set_filing_frequency()` with `SET LOCAL vouch.allow_frequency_mutation = 'true'` is permitted.
2. **Frequency Audit Log Trigger (`trg_prevent_frequency_audit_tampering`)**:
   Enforces append-only immutability on `gst_gstregistrationfrequencyauditlog`. Rejects any `UPDATE` or `DELETE` at the database engine level.
3. **Attribution Audit Log Trigger (`trg_prevent_attribution_log_mutation`)**:
   Enforces append-only immutability on `gst_vouchergstinattributionlog`. Prevents any modification of historical voucher attribution events.
4. **Gateway Audit Logging (`GSTAuditLog`)**:
   Captures every external gateway request, response status, endpoint, correlation ID, and sanitized error messages via `GSTAuditService`.

---

## 7. Architecture Assessment & Verdict

| Architectural Domain | Status | Observations & Compliance |
|---|---|---|
| **Gateway Decoupling** | PASS | Clean ABC provider pattern with pluggable mock, sandbox, and live GSP drivers. |
| **Credential Security** | PASS | AES-256 encryption at rest, memory scrubbing, API redaction, no secret leakage in logs. |
| **SSRF & Host Protection** | PASS | Strict host allowlist validation, protocol enforcement (HTTPS only). |
| **Multi-GSTIN Isolation** | PASS | Fail-closed registration resolution, independent tokens, no cross-tenant state bleed. |
| **Database Integrity** | PASS | Native PostgreSQL triggers guard critical compliance fields against direct mutation or tampering. |
| **Release Reality** | CERTIFIED | System accurately identifies sandbox vs production boundaries without false claims of direct GSTN government connections. |
