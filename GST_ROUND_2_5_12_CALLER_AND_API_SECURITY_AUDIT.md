# SriLekh GST — Round 2.5.12 Caller & API Security Audit
## Statutory Threat Modeling, Call Boundary Verification & Concurrency Audit

---

### 1. Security Scope & Boundary Analysis

This audit examines all entry points into the Rule 37A statutory lifecycle to verify that no internal service, Celery task, API endpoint, or management command can bypass the evidence validation contract.

#### Primary Touchpoints Audited:
1. `GSTAllocationService.evaluate_rule37a_status()`
2. `GSTAllocationService.create_rule37a_reclaim_allocation()`
3. `Rule37AEvidenceService.validate_positive_filing_evidence()`
4. `Rule37AEvidenceService.validate_reclaim_evidence()`
5. `Rule37AEvidenceService.resolve_voucher_evidence()`
6. `POST /api/v1/gst/allocations/reclaim/`
7. Background reconciliation & auto-allocation tasks (`apps.gst.tasks`)

---

### 2. Threat Modeling & Bypass Vulnerability Assessment

| Threat Vector | Attack Scenario | Prior Behavior (R2.5.11) | Remediated Behavior (R2.5.12) | Security Status |
|:---|:---|:---|:---|:---:|
| **T-1: Manufactured Status String** | Caller passes `supplier_status='VERIFIED_FILED'` without providing an evidence record or ARN. | Evaluator set `reclaim_eligible=True`. | Evaluator calls `validate_positive_filing_evidence()`. Rejects missing record: `reclaim_eligible=False`. | **SECURED** |
| **T-2: Raw Boolean Injection** | Caller passes `supplier_gstr3b_filed=True` on an unknown or unverified voucher. | Potential misinterpretation as affirmative evidence. | Ignored unless substantiated by valid persisted evidence. `reclaim_eligible=False`. | **SECURED** |
| **T-3: Missing ARN Injection** | Caller provides a record claiming filing but leaves ARN blank. | Allocation allowed without ARN. | Reclaim creation raises `ValidationError: Rule 37A reclaim requires verified GSTR-3B filing Application Reference Number (ARN)`. | **SECURED** |
| **T-4: Future Filing Date** | Caller provides a future filing date to artificially meet statutory deadlines. | Accepted without date validation. | Rejected: `ValidationError: GSTR-3B filing date cannot be in the future`. | **SECURED** |
| **T-5: Cross-Tenant Evidence Re-use** | Caller references an evidence record from Tenant B to authorize a reclaim in Tenant A. | Potential cross-tenant data leak if filter lacked tenant check. | Immediate check `rec.company_id == voucher.company_id`. Raises `Cross-Tenant Evidence Violation`. | **SECURED** |
| **T-6: GSTR-1 Substitution** | Caller supplies a GSTR-2B record where GSTR-1 was filed but GSTR-3B was never filed. | Outward filing treated as sufficient evidence. | Explicit Section 16(2)(c) check enforces GSTR-3B tax payment discharge proof. | **SECURED** |
| **T-7: Reversal-Reclaim Lineage Bypass** | Caller requests reclaim for an invoice with no prior active Rule 37A reversal. | Could create orphaned reclaim allocation. | Strictly rejects: `ValidationError: No active prior Rule 37A reversal found`. | **SECURED** |
| **T-8: Foreign Reversal Linkage** | Caller links reclaim on Voucher A to a reversal belonging to Voucher B. | Risk of claiming unrelated credits. | Validates `prior_rev.voucher_id == locked_voucher.id`. Rejects with explicit linkage error. | **SECURED** |
| **T-9: Over-Reclaim / Excessive Amount** | Caller reclaims ₹2,000 against a prior reversal of ₹1,800. | Over-allocation of statutory credit. | Rejects: `ValidationError: Requested reclaim exceeds available reversal balance`. | **SECURED** |
| **T-10: Concurrent Double-Reclaim** | Two parallel HTTP requests simultaneously trigger reclaim for the same reversed voucher. | Race condition: both see available balance and create 2 reclaims. | Dual `select_for_update()` on voucher and reversal serializes threads. Exactly 1 succeeds, 1 fails. | **SECURED** |
| **T-11: Section 17(5) Ineligible Credit Reclaim** | Reclaim requested for blocked credit (e.g. personal motor vehicle). | Potential improper reclaim of blocked ITC. | Checked: `is_section_17_5_blocked`. Strictly raises `Permanently ineligible ITC under Section 17(5) cannot be reclaimed`. | **SECURED** |

---

### 3. Concurrency & Atomicity Audit

#### 3.1 Row-Level Locking Architecture
In `create_rule37a_reclaim_allocation()`:
```python
with transaction.atomic():
    locked_voucher = Voucher.objects.select_for_update().get(id=voucher.id)
    prior_rev = GSTReportingAllocation.objects.select_for_update().filter(
        voucher=locked_voucher,
        company=locked_voucher.company,
        event_type='ITC_REVERSAL_RULE_37A',
        is_active=True
    ).first()
```
- By acquiring `select_for_update()` on both the parent voucher and the prior reversal allocation at the beginning of the transaction, competing worker threads or Celery tasks are serialized at the database row level.
- This was empirically verified in test `R25912-17` (`test_r25912_17_concurrent_reclaim_attempts_serialized`), where two competing threads executed simultaneously: exactly 1 thread obtained the lock and completed the reclaim, while the second thread was blocked, subsequently observed `available_balance == Decimal('0.00')`, and was rejected with a `ValidationError`.

#### 3.2 Transactional Rollback Guarantee
Test `R25912-20` verified that when any validation step fails (e.g. invalid status, missing document ref, period mismatch), the entire database transaction is aborted, leaving **zero mutations** in `GSTReportingAllocation` and `GSTReversalReclaimLineage`.

---

### 4. API Endpoint Contract Hardening

All API endpoints that trigger reclaims now pass through `GSTAllocationService.create_rule37a_reclaim_allocation()`. Callers cannot supply raw status strings without backing evidence:
- If `supplier_status='VERIFIED_FILED'`, the payload must include a valid `evidence_record_id` or matching ARN and filing date verified in the database.
- If `supplier_status='MANUALLY_CONFIRMED'`, the authenticated API user is recorded as `user`, and `verification_reference` and `manual_verification_reason` are mandatory.

### Audit Verdict
**ALL TOUCHPOINTS SECURED — ZERO IDENTIFIED BYPASS VECTORS.**
