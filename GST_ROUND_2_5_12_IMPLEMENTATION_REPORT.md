# SriLekh GST — Round 2.5.12 Implementation Report
## State-of-the-Art Rule 37A Positive Evidence, Reclaim Authorization & Provenance Integrity Remediation

---

### Executive Summary

| Attribute | Specification |
|:---|:---|
| **Repository** | `https://github.com/prakhar2207/Vouch` |
| **Base Commit** | `7c873d41196aeb1349d6da26e8a78fe2ac6f42d5` |
| **Base Branch** | `fix/round2-5-11-rule37a-missing-timestamp-guard` |
| **Working Branch** | `fix/round2-5-12-rule37a-positive-evidence-reclaim-guard` |
| **Target Engine** | SriLekh GST Statutory Compliance & Reversal/Reclaim Engine |
| **Staging Database** | `neondb_staging` (Host fingerprint: `6f4741bdaaf4`) |
| **Sandbox Tenant** | `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`) |
| **Protected Production Tenant** | `Maa Annapurna Belting Store` (`5d2e5dea-fe86-4871-b2af-fe1c5a05c03c`) — **ZERO ACCESS / 100% ISOLATED** |
| **Final Status** | **PASS — READY FOR FINAL INTEGRATION REVIEW** |

---

### 1. Problem Statement & Vulnerability Analysis

In Round 2.5.11, the negative evidence missing-timestamp vulnerability was resolved to prevent wrongful statutory reversals. However, independent architectural review of Round 2.5.11 identified a critical statutory vulnerability in the positive filing evidence and ITC reclaim authorization lifecycle:

1. **Unsubstantiated Status Authorization:**
   In `GSTAllocationService.evaluate_rule37a_status()`, `reclaim_eligible` was derived primarily from caller-supplied status strings (`supplier_status in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED')`) and boolean flags (`supplier_gstr3b_filed=True`), without validating the presence, provenance, or validity of the underlying filing proof.
2. **Missing Authoritative Evidence Contract:**
   An existing reversal could be reclaimed simply by passing a positive status string, even if:
   - No `SupplierGSTR3BFilingRecord` or `GSTR2BRecord` existed in the database.
   - The Application Reference Number (ARN) was missing or forged.
   - The filing date was missing or in the future.
   - The evidence belonged to an unrelated vendor GSTIN, tenant, or invoice period.
   - Manual confirmation lacked verifier identity, documentary reference (e.g. CA certificate), or verification timestamp.
3. **Absence of Strict Row-Level Locking:**
   Reclaim allocation creation previously lacked `select_for_update()` on both the invoice voucher and the source reversal allocation, creating a potential concurrency race condition where parallel threads could double-reclaim reversed ITC.

---

### 2. Remediation Architecture & Invariants

#### 2.1 The Core Statutory Invariant
> **Core Invariant:** An ITC reclaim must NEVER become eligible merely because a caller supplies a positive filing status (`VERIFIED_FILED`, `MANUALLY_CONFIRMED`) or raw boolean (`supplier_gstr3b_filed=True`). Reclaim authorization must be derived from independently validated, supplier-specific, company-specific, invoice-period-specific positive filing evidence.

#### 2.2 Authoritative Positive Filing Evidence Service (`Rule37AEvidenceService`)
Implemented `validate_positive_filing_evidence()` in `apps/gst/services/rule37a_evidence_service.py`:
- **Type-Safe Result:** Returns `PositiveFilingEvidenceValidationResult` dataclass with `is_valid`, `validation_reason`, `filing_arn`, `filing_date`, `evidence_hash`, `evidence_source`, and verified metadata.
- **Tenant Isolation:** Enforces `evidence_record.company_id == voucher.company_id`. Cross-tenant records are strictly rejected with a security violation.
- **Supplier Identity Matching:** Compares evidence supplier GSTIN against invoice voucher party ledger GSTIN. Mismatched GSTINs fail closed.
- **Exact Return Period Matching:** Compares evidence return period (`MMYYYY`) against normalized invoice return period. Discrepancies fail closed.
- **Mandatory Filing Proof:** For `VERIFIED_FILED`, requires non-empty ARN, valid non-future filing date, and an active persisted database record (`SupplierGSTR3BFilingRecord` or `GSTR2BRecord`).
- **Section 16(2)(c) Discharge Guard:** Outward declaration under GSTR-1 does not prove tax payment; affirmative proof of GSTR-3B return filing is strictly enforced.
- **Manual Verification Controls:** For `MANUALLY_CONFIRMED`, requires active verifier user, documentary reference (e.g. CA certificate, challan CIN), documented reason, and valid timestamp.
- **Contradictory Evidence Fail-Closed:** Conflicting positive and negative records across GSTR-2B and portal records fail closed to `DATA_UNAVAILABLE`.
- **Historical Fact Preservation:** Unlike negative evidence, genuine historical filing facts (>30 days old) remain permanently valid without artificial 30-day expiry.
- **Cryptographic Provenance:** Generates SHA-256 evidence hashes linking company, voucher, supplier GSTIN, period, status, ARN, and filing date.

#### 2.3 Evaluator Hardening (`GSTAllocationService.evaluate_rule37a_status`)
- Calls `Rule37AEvidenceService.validate_positive_filing_evidence(..., raise_exception=False)`.
- If validation fails, `reclaim_eligible` evaluates strictly to `False`, with `reclaim_ineligible_reason` providing explicit statutory audit trail.
- Reclaim eligibility also checks:
  1. Active prior Rule 37A reversal existence.
  2. Section 17(5) blocked credit guard (`is_section_17_5_blocked=False`).
  3. Available reversal balance (`reclaimable_balance > Decimal('0.00')`).
  4. Active reclaim duplicate guard.

#### 2.4 Reclaim Allocation Hardening (`create_rule37a_reclaim_allocation`)
- Wrapped in `transaction.atomic()` with `select_for_update()` row-level locking on both `voucher` and `prior_rev`.
- Validates positive evidence via `Rule37AEvidenceService.validate_positive_filing_evidence(..., raise_exception=True)`.
- Enforces strict reversal-to-voucher linkage if `source_reversal_id` is supplied.
- Calculates remaining reversal balance via `get_rule37a_available_reversal_balance()`.
- Supports partial reclaims with proportional tax component proration.
- Enforces idempotency via `idempotent=True` (returns existing allocation in same period without duplicate insert).
- Records statutory audit lineage in `GSTReversalReclaimLineage`.

---

### 3. File Modification Summary

| File | Changes |
|:---|:---|
| `apps/gst/services/rule37a_evidence_service.py` | Added `PositiveFilingEvidenceValidationResult`; implemented `validate_positive_filing_evidence()`; hardened `resolve_voucher_evidence()` to fail closed on unverified positive records; refactored `validate_reclaim_evidence()` to delegate to positive validator. |
| `apps/gst/services/allocation_service.py` | Updated `evaluate_rule37a_status()` to derive `reclaim_eligible` from positive evidence validator; added `get_rule37a_available_reversal_balance()`; hardened `create_rule37a_reclaim_allocation()` with row locks, lineage tracking, partial reclaims, and duplicate guards. |
| `apps/gst/tests_round2_5_12_rule37a_positive_evidence_reclaim.py` | Authored comprehensive 28-scenario statutory test suite covering 20 negative tests and 8 positive tests, including concurrency serialization. |

---

### 4. Verification Summary

- **Round 2.5.12 Suite:** 28/28 tests **PASSED** (163.5s)
- **Round 2.5.11 Regression Suite:** 14/14 tests **PASSED** (106.8s)
- **Round 2.5.10 Regression Suite:** 16/16 tests **PASSED** (124.2s)
- **Total Targeted Tests:** 58/58 tests **PASSED (100%)**
- **Pending Migrations:** 0 (`makemigrations --dry-run` reports "No changes detected")
- **System Check:** 0 issues identified
