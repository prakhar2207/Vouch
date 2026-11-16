# SriLekh — GST Round 1.1 Independent Code Audit Report

## 1. Executive Summary

This independent code audit rigorously inspects the codebase at commit `8adc8da` and all subsequent fixes on branch `fix/stage4-12-day6-remediation`. The audit evaluated 10 core dimensions: Multi-GSTIN data relationships, primary registration exclusivity, checksum algorithms, cache correctness, provider token lifecycle, tenant authorization, party enrichment safety, soft-deactivation, log redaction, and accounting side-effect prevention.

---

## 2. Dimensional Code Inspection Matrix

| Item # | Inspection Dimension | Implementation Location | Actual Behavior & Verdict |
| :--- | :--- | :--- | :--- |
| **1** | **Multi-GSTIN Relationships** | `apps/gst/models.py`<br>`GSTRegistration` | **PASS** — Models use `ForeignKey(Company, related_name='gst_registrations')` with unique constraint `unique_together = ('company', 'gstin')`. Allows one company to register multiple state GSTINs under the same PAN. |
| **2** | **Primary Registration Exclusivity** | `apps/gst/services/registration_service.py` | **PASS** — Atomic transaction updates demote any existing primary registration before setting `is_primary=True` on a new or updated registration. The first registration created for a tenant defaults to `is_primary=True`. |
| **3** | **GSTIN Validation & Checksum** | `apps/gst/services/gstin_service.py`<br>`calculate_gstin_checksum()` | **PASS** — Implements statutory ISO 7064 MOD 37-2 / Luhn MOD-36 algorithm. Rejects bad length, invalid state code, invalid PAN structure, and character mismatches locally without external network overhead. |
| **4** | **Verification Cache Correctness** | `apps/gst/services/gstin_service.py`<br>`GSTTaxpayerCache` | **PASS (REMEDIATED)** — Initial code allowed 30-day cache; remediated to strictly enforce **24-hour TTL (`timedelta(hours=24)`)**, preventing stale profiles if taxpayer status is suspended or cancelled. |
| **5** | **Provider Authentication & Token Expiry** | `apps/gst/services/sandbox_client.py`<br>`SandboxGSTClient` | **PASS** — POST `/authenticate` exchanges credentials for JWT. Caches token in `CompanyGSTConfig` and re-authenticates 5 minutes prior to expiry. Retries on 401 with forced token refresh. |
| **6** | **Tenant Authorization & IDOR** | `apps/gst/views.py`<br>`GSTRegistrationService` | **PASS** — Every view inspects `request.user.memberships` against the target `company_id`. Rejects cross-tenant access with `403 Forbidden`. |
| **7** | **Selective Party Enrichment** | `apps/gst/services/gstin_service.py`<br>`preview_party_enrichment()` | **PASS** — Generates side-by-side diff preview between GST portal data and local ledger records. Only fields explicitly checked by the user are applied; zero silent overwrites. |
| **8** | **Soft-Deactivation Behavior** | `apps/gst/services/registration_service.py`<br>`deactivate_registration()` | **PASS** — Sets `status='INACTIVE'` without dropping or cascading deletion to historical vouchers or ledger records. |
| **9** | **Audit-Log Redaction** | `apps/gst/services/audit_service.py`<br>`redact_sensitive_payload()` | **PASS** — Headers `x-api-key`, `Authorization`, and sensitive payload secrets are masked with `[REDACTED]` prior to persistence in `GSTAuditLog`. |
| **10** | **Accounting Side-Effect Prevention** | `apps/gst/tests_round1_foundation.py` | **PASS** — Party enrichment and GSTIN verification execute zero queries against `Voucher`, `LedgerEntry`, or `StockItem` tables. Total Debits == Total Credits remains invariant. |

---

## 3. Discrepancies Identified & Remediations

1. **Taxpayer Cache TTL**:
   - *Reported*: 24-hour TTL.
   - *Observed in Code*: `cache_age < timedelta(days=30)` in `gstin_service.py`.
   - *Remediation*: Corrected to `cache_age < timedelta(hours=24)` in `apps/gst/services/gstin_service.py`.
2. **Environment Variable Prefix Flexibility**:
   - *Observed in Code*: `sandbox_client.py` only looked for `GST_SANDBOX_API_KEY`.
   - *Remediation*: Updated `sandbox_client.py` to check both `SANDBOX_API_KEY` and `GST_SANDBOX_API_KEY`, as well as `SANDBOX_API_SECRET` and `SANDBOX_BASE_URL`.
3. **Encryption Descriptor Accuracy**:
   - *Reported*: "AES-256 Fernet".
   - *Actual Cryptographic Specification*: Fernet implements AES-128-CBC encryption with HMAC-SHA256 authentication using a 256-bit derived key.
   - *Remediation*: Corrected field description and documentation in `apps/gst/encryption.py`.
4. **Missing Import in Encryption Service**:
   - *Observed*: `os` module was missing in `apps/gst/encryption.py` when evaluating environment fallback.
   - *Remediation*: Added `import os` to `apps/gst/encryption.py`.

---

## 4. Audit Verdict

**VERDICT: PASS (REMEDIATED)** — All 10 architectural invariants are verified with automated test evidence.
