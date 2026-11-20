# SRI LEKH — GST ROUND 1.2.1 AUDIT REPORT: TEST COVERAGE GAPS & HARNESS AUDIT
**Audited Target:** `apps/gst/tests_round1_foundation.py` & `apps/gst/`  
**Git Commit:** `8860b99ac3f13db1c554b7d9b0a559a79c5a927e`  
**Branch:** `fix/stage4-12-day6-remediation`  
**Auditor:** Independent QA Lead & Senior Django Test Architect  
**Date:** 2026-11-16  

---

## 1. Executive Summary

This independent forensic audit evaluates the test harness supporting the GST integration in SriLekh, specifically `apps/gst/tests_round1_foundation.py` (15 tests) and the broader `apps.gst` suite (41 tests).

While all 15 foundation tests pass cleanly (executing in 14.4 seconds with zero errors), **the test suite currently tests only happy paths and mocked ideal conditions**.

Crucial edge cases—such as token stampedes under concurrency, intra-company role permissions, database-level key rotation persistence, and HTTP view-level party enrichment—are **completely untested**. These blind spots explain why multiple P1 and P2 vulnerabilities escaped detection in Round 1.2.

---

## 2. Test Execution Baseline

```text
Ran 15 tests in 14.430s
OK
System check identified no issues (0 silenced).

Apps Tested:
- apps.gst.tests_round1_foundation.GSTRound1FoundationTests:
  * test_client_authentication_success_and_caching ................... PASS
  * test_client_missing_credentials_raises_error ...................... PASS
  * test_client_authentication_failure_handling ....................... PASS
  * test_client_rate_limiting_429 ..................................... PASS
  * test_client_timeout_and_server_error_handling ..................... PASS
  * test_luhn_mod36_checksum_calculation .............................. PASS
  * test_gstin_format_validation ...................................... PASS
  * test_verify_gstin_sandbox_call_and_cache_persistence .............. PASS
  * test_multi_gstin_registration_lifecycle ........................... PASS
  * test_party_enrichment_preview_and_non_intrusive_apply ............. PASS
  * test_tenant_isolation_on_gst_registrations ........................ PASS
  * test_accounting_engine_invariance ................................. PASS
  * test_dedicated_encryption_key_enforcement_in_staging .............. PASS
  * test_encryption_roundtrip_with_direct_and_derived_keys ............ PASS
  * test_taxpayer_cache_24h_expiry_and_force_refresh .................. PASS
```

---

## 3. Comprehensive Gap Analysis Matrix

| # | Gap Area | Existing Test Behavior | Real-World Risk Uncovered | Severity |
|---|---|---|---|---|
| **GAP-01** | **Database-Level Key Rotation Re-Encryption** | `test_encryption_roundtrip_with_direct_and_derived_keys` only tests Python in-memory `encrypt` and `decrypt`. | Stored PostgreSQL database columns remain encrypted with the old key forever. When the old key is decommissioned, records become unreadable. | **P1** |
| **GAP-02** | **Intra-Company RBAC on Registration Mutations** | `test_tenant_isolation_on_gst_registrations` only tests Company B vs Company A. No test checks `role='EMPLOYEE'` or `role='VIEWER'` within Company A. | Low-privilege company members can create, update, or deactivate registrations. | **P1** |
| **GAP-03** | **View-Level Party Enrichment & Name Mapping** | `test_party_enrichment_preview_and_non_intrusive_apply` only calls `GSTINService.apply_party_enrichment()`. It does not test the HTTP API `PartyEnrichmentApplyAPIView`. | The HTTP endpoint silently fails to update `party.name` because `hasattr(party, 'legal_name')` is False, and skips audit logging. | **P1** |
| **GAP-04** | **Token Stampede Without `CompanyGSTConfig`** | `test_client_authentication_success_and_caching` seeds `CompanyGSTConfig` before calling `get_access_token()`. | When credentials come from environment variables, every outbound call hits `/authenticate`, exhausting provider rate limits. | **P1** |
| **GAP-05** | **Nested `expires_in` in Quicko Token Response** | Tests pass flat JSON: `{"access_token": "...", "expires_in": 86400}`. | If Quicko returns `{"data": {"access_token": "...", "expires_in": 3600}}`, expiry is miscalculated as 24 hours instead of 1 hour. | **P2** |
| **GAP-06** | **Concurrent Primary Registration Toggle** | `test_multi_gstin_registration_lifecycle` executes single-threaded updates sequentially. | Concurrent create calls can insert multiple rows with `is_primary=True`, causing `MultipleObjectsReturned` in downstream billing. | **P2** |
| **GAP-07** | **Force Refresh Exception Fallback** | `test_taxpayer_cache_24h_expiry_and_force_refresh` tests happy-path cache bypass. | If an exception occurs during `force_refresh=True`, stale cache is returned as `success: True`, masking cancelled/suspended vendors. | **P2** |
| **GAP-08** | **PAN Stem Consistency Across Registrations** | Tests register matching PANs: `27AAACA1234A1Z5` and `07AAACA1234A1Z7`. | No test asserts that adding a mismatched PAN (e.g. `07BBBCB5678B1Z2`) is rejected. | **P2** |

---

## 4. Actionable Remediation Test Plan

To close these critical gaps in Round 1.3, the following 8 targeted test cases must be added to `apps/gst/tests_round1_foundation.py`:

```python
# 1. Test Key Rotation Re-Encryption Persistence
def test_key_rotation_database_reencryption_lifecycle(self): ...

# 2. Test Role Enforcement on Registration Endpoints
def test_employee_and_viewer_cannot_mutate_registrations(self): ...

# 3. Test HTTP View-Level Party Enrichment
def test_party_enrichment_api_view_updates_party_name_and_audits(self): ...

# 4. Test Token Caching via Environment Variables (No Config Row)
def test_token_caching_fallback_when_company_gst_config_absent(self): ...

# 5. Test Nested Token Expiry Parsing
def test_token_nested_expires_in_parsing(self): ...

# 6. Test Concurrent Primary Registration Exclusivity
def test_concurrent_primary_registration_constraint(self): ...

# 7. Test Force Refresh Exception Does Not Return Success From Stale Cache
def test_force_refresh_failure_does_not_return_stale_cache_as_success(self): ...

# 8. Test PAN Stem Invariance
def test_pan_stem_mismatch_raises_validation_error(self): ...
```

---

## 5. Verdict & Release Readiness

**Dimension Verdict:** **FAIL (HARNESS GAPS REQUIRE CLOSURE)**  
While existing tests pass cleanly, they fail to exercise concurrent conditions, role boundaries, and HTTP view entry points. Expanding test coverage according to Section 4 is a mandatory prerequisite for Round 1.3 stabilization.
