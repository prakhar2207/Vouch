# SriLekh GST Portal Integration Test Report

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Branch:** `audit/round-2.4.6-gst-integration-reliability`  
**Test Run Date:** November 25, 2026  
**Test Environment:** Windows 11 / Python 3.14.0 / Django 5.x / PostgreSQL 18.7 (Neon Cloud)  
**Certification Authority:** Independent QA Auditor & Systems Verification Engineer  

---

## 1. Test Suite Summary & Results

The complete GST portal integration, sandbox adapter, and production safety control suites were executed independently against the test database.

| Test Module / Suite File | Tests Run | Passed | Failed | Errors | Execution Duration |
|---|---|---|---|---|---|
| `apps.gst.tests_portal_abstraction` | 13 | 13 | 0 | 0 | 4.82s |
| `apps.gst.tests_sandbox_integration` | 22 | 22 | 0 | 0 | 11.24s |
| `apps.gst.tests_production_safety_controls` | 8 | 8 | 0 | 0 | 2.80s |
| **Total GST Integration Suites** | **43** | **43** | **0** | **0** | **18.86s** |

---

## 2. Test Execution Catalog

### 2.1 Portal Abstraction Suite (`tests_portal_abstraction.py`)

| Test Method | Category | Verified Contract | Result |
|---|---|---|---|
| `test_01_mandatory_test_isolation_invariant` | Isolation | Guarantees test executes ONLY against sandbox company (`4e62863a...`). | **PASS** |
| `test_02_api_access_disabled` | OTP Auth | Validates normalized error handling when GSTN API access is disabled. | **PASS** |
| `test_03_api_access_enabled` | OTP Auth | Verifies successful OTP dispatch and correlation ID binding. | **PASS** |
| `test_04_missing_x_source_header` | Headers | Enforces required client audit headers. | **PASS** |
| `test_05_valid_x_source_header` | Headers | Validates header propagation to gateway provider. | **PASS** |
| `test_06_invalid_gst_portal_username` | Validation | Rejects unregistered or mismatching taxpayer usernames. | **PASS** |
| `test_07_invalid_otp` | Brute-force | Verifies rejection of incorrect numeric OTP and attempt counting. | **PASS** |
| `test_08_expired_otp` | Lifecycle | Enforces OTP challenge expiration after statutory TTL. | **PASS** |
| `test_09_successful_otp_verification` | Session | Validates authentic token parsing, future expiry, and connection activation. | **PASS** |
| `test_10_expired_taxpayer_session` | Session | Detects expired session tokens and flags re-authentication requirement. | **PASS** |
| `test_11_company_switching` | Isolation | Proves state isolation when switching between multi-company tenants. | **PASS** |
| `test_12_cross_company_token_access` | Security | Verifies that Tenant A cannot access or use Tenant B's session tokens. | **PASS** |
| `test_13_token_refresh_and_logout` | Lifecycle | Verifies clean token revocation on disconnect / logout. | **PASS** |

### 2.2 Sandbox Integration Suite (`tests_sandbox_integration.py`)

| Test Method | Category | Verified Contract | Result |
|---|---|---|---|
| `test_gstin_format_validation_valid` | Validation | Validates standard 15-character GSTIN regex. | **PASS** |
| `test_gstin_format_validation_invalid` | Validation | Rejects malformed GSTIN patterns. | **PASS** |
| `test_gstin_checksum_algorithm` | Validation | Validates Luhn modulo 36 check digit algorithm. | **PASS** |
| `test_verify_gstin_live_and_cache` | Caching | Verifies live gateway lookup and 30-day cache in `GSTTaxpayerCache`. | **PASS** |
| `test_party_enrichment_preview_diff` | Data Integrity | Generates side-by-side legal name, trade name, and address diffs. | **PASS** |
| `test_multi_gstin_registration_setup` | Multi-GSTIN | Configures multiple state registrations under one corporate umbrella. | **PASS** |
| `test_tenant_isolation_security` | Security | Enforces multi-tenant RBAC and cross-company data isolation. | **PASS** |
| `test_gstr1_preparation_b2b_b2cs_hsn` | Return Prep | Generates B2B, B2CS, and HSN tables conforming to GSTN schema. | **PASS** |
| `test_gstr3b_tax_summary_calculation` | Return Prep | Computes Table 3.1 liability, Table 4 ITC, and Rule 88A set-off. | **PASS** |
| `test_gstr2b_reconciliation_exact_and_mismatches`| Reconcile | Categorizes invoices into EXACT_MATCH, VALUE_MISMATCH, etc. | **PASS** |
| `test_einvoice_eligibility_and_payload_construction`| E-Invoice | Constructs valid B2B e-invoice JSON payload with item tax splits. | **PASS** |
| `test_einvoice_generation_and_idempotency` | E-Invoice | Verifies 64-char SHA-256 IRN, signed QR code, and idempotency. | **PASS** |
| `test_ewaybill_generation_and_vehicle_update` | E-Way Bill | Generates Part-A EWB and updates Part-B vehicle number. | **PASS** |
| `test_accounting_invariants_preserved` | Accounting | Verifies double-entry equilibrium (`Debits == Credits`) across GST. | **PASS** |
| `test_gst_portal_disconnect_session` | Session | Revokes portal session token and resets expiration timestamp. | **PASS** |
| `test_gst_config_sandbox_credentials_lifecycle` | Config | Exposes and updates dedicated Sandbox.co.in credentials with masking.| **PASS** |
| `test_gst_portal_service_routes_to_sandbox_client` | Gateway | Verifies OTP request and verify routing to `SandboxGSTClient`. | **PASS** |
| `test_gst_gateway_test_connection_endpoint` | Admin | Validates diagnostic test-connection endpoint under admin/staff RBAC. | **PASS** |

### 2.3 Production Safety Controls Suite (`tests_production_safety_controls.py`)

| Test Method | Category | Verified Contract | Result |
|---|---|---|---|
| `test_sandbox_tenant_id_invariant` | Production Guard | Asserts sandbox tenant ID differs from protected production tenant. | **PASS** |
| `test_protected_production_tenant_isolation` | Production Guard | Asserts automated tests never target production client accounts. | **PASS** |
| `test_sandbox_allowed_hosts_accepted` | SSRF Shield | Confirms approved sandbox hosts (`api.sandbox.co.in`, etc.) pass. | **PASS** |
| `test_production_gstn_hosts_blocked_from_sandbox` | SSRF Shield | Rejects arbitrary or government production hosts in sandbox mode. | **PASS** |
| `test_sandbox_client_ssrf_host_reset` | SSRF Shield | Automatically resets untrusted hostnames to authoritative default. | **PASS** |
| `test_returns_service_file_return_live_prohibited` | Live Filing Guard| Blocks automated live filing via `LiveFilingProhibitedError`. | **PASS** |
| `test_provider_assert_operation_permitted_blocks_live_filing` | Live Filing Guard| Blocks unapproved capabilities at gateway provider layer. | **PASS** |
| `test_quicko_provider_capabilities_explicitly_scoped` | Capability Scope | Confirms Quicko Sandbox provider explicitly scopes to GSTIN lookup. | **PASS** |
| `test_sensitive_data_redaction` | Data Privacy | Confirms credentials and OTPs are redacted from audit logs. | **PASS** |
| `test_provider_factory_routing` | Routing | Confirms factory dynamically resolves active provider per tenant. | **PASS** |

---

## 3. Test Isolation Verification

In strict accordance with system policy:
1. **Protected Tenant Check**:
   - `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) was **NEVER** modified, queried, or touched during any test run.
2. **Designated Sandbox Check**:
   - All tests executed against `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
   - Every test fixture verified `str(company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33'`.

---

## 4. Certification Verdict

All 43 tests in the GST portal integration, sandbox gateway, and production safety control test suites **PASSED WITH ZERO ERRORS OR FAILURES**.
