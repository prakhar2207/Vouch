# SRI LEKH GST — ROUND 2.5.17
# Deliverable 3: GSTR-1 Direct Filing Safety & Statutory Integrity Report

**Repository**: https://github.com/prakhar2207/Vouch  
**Production Application**: https://srilekh.com  
**Audit Date**: November 23, 2026  
**Auditor**: Financial Systems Auditor & Indian GST Compliance Specialist  
**Dedicated Test Tenant**: `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  

---

## 1. Statutory Invariants & Mandates

Under the Central Goods and Services Tax Act, 2017 (CGST Act) and GST Rules:
1. **Zero Mock / Hardcoded Authentication**: An accounting software must never simulate return submission using bypass OTPs (such as the legacy `"575757"` fallback).
2. **Zero Fabricated Acknowledgements**: An Application Reference Number (ARN) is a cryptographically signed, statutory document issued exclusively by the Goods and Services Tax Network (GSTN). Prefixes like `REF-G1-...` or synthetic UUIDs must **never** be presented or saved as government ARNs.
3. **State Machine Integrity**:
   - Return submissions must progress through explicit, audit-trailed states: `DRAFT` -> `SUBMITTING` -> `SUBMITTED` / `FILED` / `FAILED` / `RECONCILIATION_REQUIRED`.
   - Network dropouts or gateway 504 timeouts must transition the batch to `RECONCILIATION_REQUIRED`, **never** `FILED`.
4. **Duplicate Submission Shield**: Periods already marked `FILED` or `SUBMITTED` must reject subsequent filing attempts to prevent double-taxation or statutory rejection.

---

## 2. Technical Remediation & Controls

1. **Elimination of Hardcoded OTPs**:
   - `verify_portal_otp(company, "575757")` was completely removed from `upload_gstr1_direct`.
   - If an active session is absent or expired, the request is immediately rejected with `code: "AUTHENTICATION_REQUIRED"`.

2. **Elimination of Synthetic ARNs in Return Records**:
   - In `apps/gst/services/returns_service.py` and `apps/gst/services/gst_sandbox_service.py`:
     ```python
     # REMOVED:
     arn = arn or f"ARN-{uuid.uuid4().hex[:12].upper()}"
     # REPLACED WITH STRICT GOVERNMENT ARN ONLY:
     gov_arn = resp_data.get("arn") or ""
     final_status = 'FILED' if gov_arn else 'SUBMITTED'
     filing_rec.arn = gov_arn
     filing_rec.provider_reference = provider_ref
     ```
   - Preliminary gateway reference IDs (`reference_id`) are stored in `provider_reference`, not `arn`. The `arn` field remains empty until the official government ARN is confirmed.

3. **Status Reconciliation (`get_portal_status`)**:
   - Provides an idempotent query endpoint to retrieve batch status using `ref_id`.
   - Idempotently transitions `SUBMITTED` or `RECONCILIATION_REQUIRED` records to `FILED` upon government confirmation.

4. **Duplicate Filing Prevention**:
   - Checks existing `GSTFilingRecord` for the period. If `FILED`, returns `ALREADY_FILED` error code.

---

## 3. Verification Test Evidence (Phase C)

| Test Case | Description | Result |
| :--- | :--- | :--- |
| `test_filing_rejects_without_session` | Unauthenticated request rejected with `AUTHENTICATION_REQUIRED`. | **PASSED** |
| `test_filing_rejects_expired_session` | Expired token rejected with `AUTHENTICATION_REQUIRED`. | **PASSED** |
| `test_filing_never_uses_hardcoded_otp` | Confirms `verify_portal_otp` is never called automatically. | **PASSED** |
| `test_filing_rejects_synthetic_arn_and_requires_genuine_arn` | Reference ID saved in `ref_id`, `arn` remains blank until confirmed. | **PASSED** |
| `test_filing_status_failed_on_provider_rejection` | HTTP 400 sets status `FAILED` and error code `SUBMISSION_REJECTED`. | **PASSED** |
| `test_filing_status_reconciliation_required_on_timeout` | HTTP 504 / timeout sets status `RECONCILIATION_REQUIRED`. | **PASSED** |
| `test_filing_success_persists_genuine_government_arn` | Genuine government ARN (`AA090726000001Y`) sets status `FILED`. | **PASSED** |
| `test_filing_prevents_duplicate_filing_when_already_filed` | Duplicate submission for filed period rejected with `ALREADY_FILED`. | **PASSED** |
| `test_filing_reconciliation_endpoint_updates_record_idempotently` | Idempotent reconciliation endpoint verifies status and persists genuine ARN. | **PASSED** |

---

## 4. Phase C Certification

**STATUS: CERTIFIED & COMPLIANT**  
SriLekh guarantees statutory compliance: no unconfirmed filing can ever be marked filed, and zero synthetic ARNs can be created.
