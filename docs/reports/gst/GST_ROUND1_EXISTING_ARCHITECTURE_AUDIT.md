# SriLekh — GST Round 1 Existing Architecture Audit

## 1. Executive Summary

This audit assesses the existing GST architecture in **SriLekh** prior to implementing Round 1 of the Sandbox by Quicko integration.

SriLekh is an MSME Accounting SaaS built on Django REST Framework, PostgreSQL, and Next.js. Accounting correctness and data integrity are governed by strict invariants:
- Mathematical equilibrium: `Total Debits == Total Credits` on every posted voucher.
- Tenant isolation across all entities with zero cross-tenant visibility.
- Protected production tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) and production database `neondb` must never be touched by automated tests or migrations.

---

## 2. Inventory of Existing GST Components

### A. Company & Tenant Model (`apps/companies/models.py`)
- `Company` contains basic GST fields:
  - `gstin` (CharField, max_length=15, blank=True)
  - `pan` (CharField, max_length=10, blank=True)
  - `state_code` (CharField, max_length=2, blank=True)
  - `state_name` (CharField, max_length=100, blank=True)
- **Limitation**: `Company.gstin` only represents a single, primary GSTIN. Businesses operating in multiple states (e.g. branch offices in Delhi, Maharashtra, and Haryana) require distinct state-level GST registrations under one parent company.

### B. GST Registrations Model (`apps/gst/models.py`)
- `GSTRegistration`: Introduced to support multi-state/multi-GSTIN operations under one `Company`:
  - `company` (ForeignKey to `Company`, related_name=`gst_registrations`)
  - `gstin` (CharField, max_length=15, db_index=True)
  - `legal_name`, `trade_name`, `state_code`, `state_name`, `address`, `pincode`
  - `taxpayer_type` (`REGULAR`, `COMPOSITION`, `ISD`, `SEZ_DEVELOPER`, `SEZ_UNIT`, `CASUAL`, `NON_RESIDENT`)
  - `status` (`ACTIVE`, `SUSPENDED`, `CANCELLED`, `INACTIVE`)
  - `is_primary` (BooleanField, default=False)
  - `unique_together = ('company', 'gstin')`
- **Audit Findings**:
  - `GSTRegistration` is architecturally sound and correctly scoped to `company`.
  - Missing fields required by Round 1 specification:
    - `verification_status` (`NOT_VERIFIED`, `PENDING`, `VERIFIED`, `INVALID`, `INACTIVE`, `FAILED`, `PROVIDER_UNAVAILABLE`, `EXPIRED`)
    - `last_verified_at` (DateTimeField)
    - `provider_reference_id` (CharField)

### C. Party / Ledger Model (`apps/accounting/models.py`)
- `Ledger`:
  - `company` (ForeignKey to `Company`)
  - `name`, `group` (Sundry Debtors / Sundry Creditors)
  - `gstin` (CharField, max_length=15, blank=True)
  - `state_code` (CharField, max_length=2, blank=True)
  - `address`, `phone`, `email`
  - `current_balance`, `opening_balance`
- **Audit Findings**:
  - Ledgers store party GSTIN and state code.
  - Verification must NEVER create duplicate ledgers or overwrite party balances.
  - Verification must allow the user to preview changes (legal name vs books name) and selectively apply updates without silent overwrites.

### D. GST Calculation Engine (`apps/gst/services/gst_calculator.py` & `apps/accounting/services/`)
- Existing calculator computes CGST, SGST, IGST, and RCM based on supplier state vs recipient place of supply (POS).
- If supplier `state_code == recipient state_code` -> Intrastate (CGST 50% + SGST 50%).
- If supplier `state_code != recipient state_code` -> Interstate (IGST 100%).
- Round 1 provider integration does NOT alter tax computation logic; it supplies verified state codes to ensure tax calculation accuracy.

### E. Voucher & Invoicing Models (`apps/accounting/models.py`)
- `Voucher` (SALES, PURCHASE, RECEIPT, PAYMENT, JOURNAL, CONTRA, CREDIT_NOTE, DEBIT_NOTE).
- Financial values are immutable once posted.
- Adding or verifying GST registrations does not modify voucher financial data.

### F. Security, Permissions & Audit Logging
- `HasGSTPermission` enforces RBAC (`OWNER`, `ADMIN`, `ACCOUNTANT`).
- `GSTAuditLog` records endpoint, correlation ID, status code, and sanitized payloads with automatic redaction of secrets, tokens, and passwords.

---

## 3. Existing Limitations

1. **Verification Status Tracking**: `GSTRegistration` lacks explicit tracking for whether a registration was verified via the external Sandbox API vs manually entered.
2. **Settings Screen Integration**: Company settings (`frontend/src/app/settings/page.tsx`) previously had a basic GST portal OTP tab, but lacked a dedicated multi-GSTIN registration management interface (Add, Verify, Review, Edit, Deactivate).
3. **Party Master Verification Flow**: Party forms had basic GSTIN lookup, but lacked a side-by-side verification preview dialog that prevents silent overwrites.

---

## 4. Required Modifications for Round 1

1. **Schema Extension**:
   - Add `verification_status`, `last_verified_at`, and `provider_reference_id` to `GSTRegistration` in `apps/gst/models.py`.
   - Create migration `0006_gstregistration_verification_status_and_more.py`.
2. **Registration Service**:
   - Implement `GSTRegistrationService` in `apps/gst/services/registration_service.py` to handle creation, verification, updates, and deactivations with duplicate prevention.
3. **Provider Client Hardening**:
   - Verify `SandboxGSTClient` handles token auto-refresh, timeouts, rate limits (429), correlation IDs, and configuration fallbacks.
4. **GSTIN Verification Service**:
   - Enhance `GSTINService` to support registration verification alongside party verification.
5. **Frontend Extensions**:
   - Add `GSTRegistrationsView` in `Settings → GST Registrations` with desktop and mobile responsiveness.
   - Wire `GSTINVerifyDialog` into customer and supplier creation/edit forms.

---

## 5. Potential Migration Impact & Compatibility Risks

| Risk Area | Severity | Mitigation Strategy |
| :--- | :---: | :--- |
| **Double-Entry Regression** | High | GSTIN verification and registration management are strictly orthogonal to accounting vouchers; zero financial mutations. |
| **Tenant Boundary Violation** | High | Server-side validation of `company=request.company` on every query; automated IDOR test coverage. |
| **Existing Migrations** | Low | New migration adds nullable/defaulted columns to `GSTRegistration`; zero destructive changes. |
| **Performance Overhead** | Low | 24-hour local caching via `GSTTaxpayerCache` and local Luhn MOD-36 checksum checks eliminate unnecessary API calls. |
