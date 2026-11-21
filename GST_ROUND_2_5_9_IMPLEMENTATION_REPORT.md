# SriLekh GST — Round 2.5.9 Implementation Report
## Rule 37A Evidence Resolution Hardening & Independent Re-Certification

---

## 1. Executive Summary & Verification Context

- **Repository:** `prakhar2207/Vouch`
- **Base Commit:** `cb673004b343d4ea3a9b584f745f37437f60a8e4`
- **Base Branch:** `fix/round2-5-7-payment-evidence-certification`
- **Working Branch:** `fix/round2-5-9-rule37a-evidence-resolution-hardening`
- **Mandatory Policy Conformance:**
  - Dedicated Staging Database: `neondb_staging` (Host: Neon Pooler, Fingerprint: `6f4741bdaaf4` verified).
  - Dedicated Sandbox Company ONLY: `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
  - Production Tenant Protection: `Maa Annapurna Belting Store` (`5d2e5dea-fe86-4871-b2af-fe1c5a05c03c`) & Production DB `neondb` — **STRICTLY ZERO ACCESS / UNTOUCHED**.
  - Production Deployments / Merges: **NONE (STRICTLY PROHIBITED)**.

---

## 2. Core Invariant Enforced

> **Statutory Evidence Invariant:**
> SriLekh must NEVER create a statutory ITC reversal or reclaim under Rule 37A based on missing, stale, mismatched, ambiguous, or incorrectly attributed supplier filing evidence. Absence of evidence must NEVER be interpreted as affirmative evidence of supplier non-filing. A Rule 37A reversal strictly requires verified, invoice-period-specific, supplier-specific, fresh evidence.

---

## 3. Engineering Remediations Implemented

### 3.1 P0 — GSTR-2B Exact Return-Period Enforcement
- **File:** `apps/gst/services/rule37a_evidence_service.py` & `apps/gst/services/allocation_service.py`
- **Defect in Round 2.5.8:** The fallback filter `if g2b_period and g2b_period != inv_period: continue` allowed blank or empty GSTR-3B return periods to slip through and be accepted as matching evidence.
- **Remediation:**
  - Introduced `Rule37AEvidenceService.normalize_and_validate_return_period(period_str)` enforcing strict 6-digit `MMYYYY` format with month 01–12 and year 2017–2099.
  - Excluded any GSTR-2B record where `normalize_and_validate_return_period(g2b.gstr3b_return_period) != inv_period`.
  - Prohibited fallback or inference from the GSTR-2B batch statement period (`g2b.return_period`).
  - When matching GSTR-2B records exist for a voucher but lack valid exact-period GSTR-3B evidence, returns `DATA_UNAVAILABLE` rather than defaulting to default or failure.

### 3.2 Evidence Timestamp Preservation & Staleness Integrity
- **Files:** `apps/gst/services/rule37a_evidence_service.py`, `apps/gst/models.py`
- **Defect in Round 2.5.8:** Missing timestamps on negative evidence records were synthesized via `chosen["timestamp"] or timezone.now()`, disguising unverified or stale records as freshly verified. Furthermore, `SupplierGSTR3BFilingRecord.verified_at` had `auto_now=True`, overwriting historical verification timestamps on every save.
- **Remediation:**
  - Removed all fake timestamp fallbacks.
  - If a negative non-filing evidence record has no `verified_at`, immediately resolves to `status="DATA_UNAVAILABLE"` and `verification_timestamp=None`.
  - In `apps/gst/models.py`, updated `SupplierGSTR3BFilingRecord.verified_at` from `auto_now=True` to `models.DateTimeField(null=True, blank=True, default=timezone.now)` and authored migration `0017_alter_suppliergstr3bfilingrecord_verified_at.py`.
  - Negative evidence verified >30 days ago is converted to `DATA_UNAVAILABLE`.

### 3.3 Positive Filing Fact Validity & Provenance
- **File:** `apps/gst/services/rule37a_evidence_service.py`
- **Remediation:**
  - Affirmative supplier filing verified with an authoritative ARN and filing date is recognized as an immutable historical event on the GST portal under Section 155.
  - The original source verification timestamp is preserved separately from the return filing date.

### 3.4 Cross-Source Reconciliation & Ambiguity Resolution
- **File:** `apps/gst/services/rule37a_evidence_service.py`
- **Remediation:**
  - Direct contradiction between sources (e.g. `SupplierGSTR3BFilingRecord` reports `VERIFIED_FILED` while `GSTR2BRecord` reports `VERIFIED_NOT_FILED`, or vice versa) halts automation and returns `DATA_UNAVAILABLE` with reason `CONFLICTING_SOURCES`.
  - Ambiguity (one source reports `VERIFIED_NOT_FILED` while another reports `PENDING`) returns `DATA_UNAVAILABLE` with reason `AMBIGUOUS_SOURCES`.
  - Affirmative proof of filing with verified ARN and date takes priority over inconclusive pending or unavailable status.
  - Re-imports and multiple matching GSTR-2B records are deterministically sorted by `gstr3b_verified_at` (latest verified record selected).

### 3.5 Reversal & Reclaim Boundary Audit
- **Files:** `apps/gst/services/allocation_service.py`, `apps/gst/services/rule37a_evidence_service.py`
- **Remediation:**
  - Reversal attempts before the statutory default date (30th September following the end of the financial year) are rejected upfront with `ValidationError`.
  - Duplicate reversal attempts on the same invoice voucher are blocked.
  - Reclaims strictly require an active prior Rule 37A reversal (`require_prior_reversal=True`).
  - Added `GSTAllocationService.get_active_rule37a_reversal_balance(voucher)` to track available reversal balance after existing active reclaims.
  - Reclaim amounts exceeding the available reversal balance or duplicate reclaims after balance exhaustion are rejected.
  - Permanently blocked credits under Section 17(5) (`ITC_REVERSAL_SEC_17_5`) are blocked from reclaim.

### 3.6 CI Encryption Key Hygiene
- **File:** `.github/workflows/stage-verification-ci.yml`
- **Remediation:**
  - Removed all occurrences of the committed static Fernet key (`1XxlyIyQuZPNNYUELXz9FQ2RICOBa3VS4tK621QXdHg=`).
  - Added `Provision Ephemeral Test GST Encryption Key` step generating an ephemeral 32-byte Fernet key at runtime masked via `::add-mask::` and exported to `$GITHUB_ENV`.
  - Added `Verify CI Encryption Key Hygiene` step asserting valid 32-byte key and failing closed if static keys are detected.
  - Removed step-level `GST_ENCRYPTION_KEY` overrides across backend test steps, allowing steps to cleanly inherit the masked ephemeral key.

### 3.7 Fail-Closed Test Isolation
- **Files:** `apps/gst/tests_round2_5_8_rule37a_evidence_integrity.py`, `apps/gst/tests_round2_5_9_rule37a_evidence_resolution.py`
- **Remediation:**
  - Converted environment guard to fail-closed: asserts `connection.vendor == 'postgresql'`, asserts database name and SHA-256 host/db fingerprint match `neondb_staging` (`6f4741bdaaf4`) or local CI container, aborting immediately on SQLite.

---

## 4. Database Migrations

- **Migration Applied:** `apps/gst/migrations/0017_alter_suppliergstr3bfilingrecord_verified_at.py`
- **Operations:** Altered `SupplierGSTR3BFilingRecord.verified_at` from `auto_now=True` to `models.DateTimeField(null=True, blank=True, default=timezone.now)` to support null timestamps and prevent automatic overwriting of historical verification dates.
- **Migration Application:** Applied cleanly against `neondb_staging` (`OK`). `makemigrations --check --dry-run` confirms zero unmigrated schema changes.

---

## 5. Summary of Modified & Created Files

| File | Status | Description |
|---|---|---|
| `.github/workflows/stage-verification-ci.yml` | Modified | Ephemeral runtime key provisioning, log masking, removal of static Fernet key |
| `apps/gst/models.py` | Modified | Decoupled `verified_at` from `auto_now=True` on `SupplierGSTR3BFilingRecord` |
| `apps/gst/migrations/0017_alter_suppliergstr3bfilingrecord_verified_at.py` | Created | Migration altering `verified_at` field definition |
| `apps/gst/services/rule37a_evidence_service.py` | Modified | Return period normalization, timestamp preservation, cross-source conflict handling, UUID type safety |
| `apps/gst/services/allocation_service.py` | Modified | GSTR-2B exact period lookup, `get_active_rule37a_reversal_balance` method |
| `apps/gst/tests_round2_5_8_rule37a_evidence_integrity.py` | Modified | Fail-closed PostgreSQL vendor and staging fingerprint check |
| `apps/gst/tests_round2_5_9_rule37a_evidence_resolution.py` | Created | Dedicated 26-test statutory suite (Scenarios 1–26) |
| `GST_ROUND_2_5_9_IMPLEMENTATION_REPORT.md` | Created | This implementation report |
| `GST_ROUND_2_5_9_SUPPLIER_EVIDENCE_AUDIT.md` | Created | Technical evidence audit |
| `GST_ROUND_2_5_9_TEST_RESULTS.md` | Created | Test execution manifest & concurrency certification |
| `GST_ROUND_2_5_9_STATUTORY_LIMITATIONS.md` | Created | Statutory legal limitations document |
