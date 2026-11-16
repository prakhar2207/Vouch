# SriLekh GST Integration — Round 1.3 Automated Test Suite Execution & Gateway Report
## Unit, Integration, Concurrency & Security Test Coverage

- **Target Module:** `apps/gst`
- **Test Harness:** `apps/gst/tests_round1_foundation.py`
- **Execution Date:** November 16, 2026
- **Branch:** `fix/stage4-12-day6-remediation`
- **Gateway Status:** `NOT LIVE-VERIFIED (Pending Owner Credentials)`

---

## 1. Test Harness Overview

The automated test harness for the GST Integration Foundation was significantly expanded in Round 1.3 to cover all remediated security defects, cryptographic operations, concurrency race conditions, and role-based permissions.

```
Total Test Cases: 29
Engine: Django Test Runner / Isolated SQLite In-Memory Database
Zero Production Database Access: CONFIRMED
```

---

## 2. Test Execution Breakdown

| # | Test Method Name | Domain | Verification Objective | Result |
|---|---|---|---|---|
| **1** | `test_valid_gstin_checksum_algorithm` | Validation | Formats, state codes, entity types, and Luhn checksum math. | **PASS** |
| **2** | `test_invalid_gstin_checksum_rejected` | Validation | Rejection of bad checksum digits and malformed regex. | **PASS** |
| **3** | `test_state_code_mismatch_raises_validation_error` | Validation | Rejection when state code does not match first 2 digits of GSTIN. | **PASS** |
| **4** | `test_offline_taxpayer_cache_retrieval` | Cache | Cache retrieval within 24-hour TTL without outbound HTTP calls. | **PASS** |
| **5** | `test_force_refresh_bypasses_valid_cache` | Cache | `force_refresh=True` queries provider and updates cache. | **PASS** |
| **6** | `test_expired_cache_triggers_provider_fetch` | Cache | Cache older than 24 hours expires and refreshes. | **PASS** |
| **7** | `test_provider_outage_returns_stale_cache_gracefully` | Resilience | If provider is 500/timeout, returns stale cache with `is_stale=True`. | **PASS** |
| **8** | `test_force_refresh_provider_error_does_not_return_cached_as_live` | Resilience | Forced refresh failures return `success: False` with `provider_error`. | **PASS** |
| **9** | `test_single_primary_gstin_enforced_per_company` | Invariants | Creating a new primary GSTIN atomically demotes existing primary. | **PASS** |
| **10** | `test_concurrent_primary_registration_unique_constraint` | Database | Partial `UniqueConstraint` blocks concurrent duplicate primary rows. | **PASS** |
| **11** | `test_deactivate_primary_promotes_next_active_registration` | Lifecycle | Deactivating primary promotes next active registration automatically. | **PASS** |
| **12** | `test_pan_stem_invariant_enforced_across_registrations` | Invariants | Non-matching PAN stem raises `GSTINValidationError`. | **PASS** |
| **13** | `test_encrypted_credential_storage_and_transparent_retrieval` | Cryptography | Transparent encryption on save and decryption on fetch. | **PASS** |
| **14** | `test_raw_database_contains_ciphertext_not_plaintext` | Cryptography | Raw database column inspection confirms `enc:v1:` Fernet prefix. | **PASS** |
| **15** | `test_corrupted_ciphertext_raises_credential_decryption_error` | Security | Tampered ciphertext triggers `CredentialDecryptionError` fail-closed. | **PASS** |
| **16** | `test_key_rotation_management_command_dry_run_and_execution` | Operations | Zero-downtime key rotation (`--dry-run` and live re-encryption). | **PASS** |
| **17** | `test_sandbox_client_ssrf_host_allowlist_enforced` | Security | Host allowlist blocks outbound requests to unauthorized domains. | **PASS** |
| **18** | `test_sandbox_client_rate_limiting_exponential_backoff` | Resilience | Exponential backoff with jitter on HTTP 429 for idempotent GETs. | **PASS** |
| **19** | `test_sandbox_client_token_caching_and_stampede_prevention` | Performance | Token cached in DB + cache backend; stampede prevented. | **PASS** |
| **20** | `test_rbac_registration_mutations_restricted_to_admin_owner` | RBAC | Only `OWNER` and `ADMIN` can create/update/deactivate registrations. | **PASS** |
| **21** | `test_registration_authorized_users_object_permission` | Security | Granular registration `authorized_users` enforcement for viewers. | **PASS** |
| **22** | `test_party_enrichment_rbac_and_cross_tenant_isolation` | Security | Party auto-fill requires Accountant+; cross-tenant party rejected. | **PASS** |
| **23** | `test_party_enrichment_tamper_resistance_against_unverified_input`| Security | Input verified against `GSTTaxpayerCache` before updating ledger. | **PASS** |
| **24** | `test_gst_audit_log_records_registration_events` | Audit | Audit trail recorded for all registration lifecycle mutations. | **PASS** |
| **25** | `test_client_timeout_and_server_error_handling` | Resilience | Provider socket timeouts return normalized HTTP 504. | **PASS** |
| **26** | `test_unified_verify_gstin_endpoint_authenticated` | API | Public unauthenticated access rejected with HTTP 401. | **PASS** |
| **27** | `test_company_gst_config_endpoint_rbac` | API | Config endpoints restricted to `OWNER` / `ADMIN`. | **PASS** |
| **28** | `test_iso8601_date_parsing_for_taxpayer_registration_date` | Integrity | Strict date parser handles standard and non-standard portal formats. | **PASS** |
| **29** | `test_audit_log_sensitive_fields_masked` | Security | Audit logs mask API credentials, tokens, and secrets. | **PASS** |

---

## 3. Provider Gateway Status

```
GATEWAY STATUS: NOT LIVE-VERIFIED (Pending Owner Credentials)
```

- All automated integration tests were executed using deterministic provider mocks adhering to Quicko Sandbox API specifications.
- Live network traffic to `https://api.sandbox.co.in` will remain disabled until the client provisions live staging API keys in the Render environment variables.
