# SriLekh GST — Round 2.5.12 Positive Evidence Audit
## Comprehensive Statutory Evidence Architecture & Provenance Verification

---

### 1. Statutory Context & Legislative Framework

Under the **CGST Act, 2017** and **CGST Rules, 2017**:
1. **Rule 37A (Reversal of Input Tax Credit in case of non-payment of tax by supplier and reclaim thereof):**
   - When a supplier fails to furnish GSTR-3B by 30th September following the financial year, the recipient must reverse ITC on or before 30th November.
   - **Proviso to Rule 37A:** Where the supplier subsequently furnishes the return in FORM GSTR-3B for the said tax period, the recipient *may reclaim* the amount of reversed credit.
2. **Section 16(2)(c) of the CGST Act, 2017:**
   - Subject to Section 41, no registered person shall be entitled to the credit of any input tax in respect of any supply of goods or services unless *the tax charged in respect of such supply has been actually paid to the Government*, either in cash or through utilization of input tax credit admissible.
3. **Section 17(5) of the CGST Act, 2017:**
   - Certain categories of supply (e.g. motor vehicles for personal use, food and beverages, club memberships, goods lost/stolen/destroyed) are permanently blocked from ITC claim and can never be reclaimed.

---

### 2. Evidence Architecture Principles

Prior to Round 2.5.12, the system permitted reclaim eligibility evaluation based merely on callers asserting `VERIFIED_FILED` or `supplier_gstr3b_filed=True`. This represented an untenable compliance risk: a caller could trigger a statutory reclaim without establishing proof of tax discharge.

Round 2.5.12 establishes an airtight evidence validation pipeline:

```
[Incoming Voucher & Evidence Request]
                │
                ▼
┌────────────────────────────────────────────────────────┐
│  Rule37AEvidenceService.validate_positive_filing_evidence()
└────────────────────────────────────────────────────────┘
                │
    ┌───────────┴───────────┐
    │ 1. Multi-Tenant Guard │ ──> Reject if evidence.company_id != voucher.company_id
    └───────────┬───────────┘
                │
    ┌───────────┴───────────┐
    │ 2. Supplier Identity  │ ──> Reject if evidence.supplier_gstin != voucher.party_gstin
    └───────────┬───────────┘
                │
    ┌───────────┴───────────┐
    │ 3. Period Integrity   │ ──> Reject if normalized(evidence.period) != normalized(inv.period)
    └───────────┬───────────┘
                │
    ┌───────────┴───────────┐
    │ 4. Positive Discharge │ ──> Reject if status not in (VERIFIED_FILED, MANUALLY_CONFIRMED)
    │    (Section 16(2)(c)) │     Reject if GSTR-1 outward filing substituted for GSTR-3B tax payment
    └───────────┬───────────┘
                │
    ┌───────────┴───────────┐
    │ 5. Proof Requirement  │ ──> For PORTAL: Must have ARN + filing_date + persisted DB record
    │                       │     For MANUAL: Must have active user + doc_ref + reason + timestamp
    └───────────┬───────────┘
                │
    ┌───────────┴───────────┐
    │ 6. Conflict Guard     │ ──> Fail-closed to DATA_UNAVAILABLE on contradictory records
    └───────────┬───────────┘
                │
                ▼
[PositiveFilingEvidenceValidationResult: VALID]
                │
                ▼
┌────────────────────────────────────────────────────────┐
│   GSTAllocationService.create_rule37a_reclaim_allocation()
│   - SELECT FOR UPDATE on Voucher & Prior Reversal
│   - Section 17(5) blocked credit guard
│   - Available reversal balance limit enforcement
│   - Duplicate reclaim guard & Idempotency handler
│   - Proportional tax breakdown for partial reclaims
│   - SHA-256 Lineage tracking (GSTReversalReclaimLineage)
└────────────────────────────────────────────────────────┘
```

---

### 3. Detailed Evidence Audit Criteria

#### 3.1 Multi-Tenant Isolation
Every evidence record passed (`SupplierGSTR3BFilingRecord` or `GSTR2BRecord`) is inspected against `voucher.company_id`. Any cross-tenant record produces an immediate `ValidationError("Cross-Tenant Evidence Violation")`, preventing data leaks across tenant boundaries.

#### 3.2 Supplier Identity Validation
The supplier GSTIN on the evidence record is compared with the party ledger GSTIN of the voucher. Even if the status is `VERIFIED_FILED`, if the GSTIN does not match the voucher's supplier, authorization is strictly denied.

#### 3.3 Exact Return Period Validation
The return period is normalized to `MMYYYY` format. Evidence with a blank, null, or mismatched return period (e.g. matching an import batch statement period rather than the invoice return period) is strictly excluded.

#### 3.4 Outward Supply vs. Tax Discharge (Section 16(2)(c))
GSTR-1 reflects only outward supplies declared by the supplier; it does *not* prove payment of tax to the Government. If a `GSTR2BRecord` indicates `gstr1_filing_date` is present but `gstr3b_filing_date` is absent or `gstr3b_status != 'FILED'`, positive evidence validation fails closed with an explicit citation of Section 16(2)(c).

#### 3.5 Manual Verification Controls
When automated portal integration is supplemented by manual verification, the system strictly mandates:
1. `user`: An active registered system user who conducted the verification.
2. `verification_reference`: Verifiable reference identifier (e.g. CA certificate number, challan CIN).
3. `manual_verification_reason`: Explicit business rationale explaining how tax payment was confirmed.
4. `verification_timestamp`: Precise timestamp when verification took place.

#### 3.6 Conflict Resolution
If portal records report `VERIFIED_FILED` while GSTR-2B simultaneously reports `NOT_FILED` (or vice versa), the system treats this as a data conflict, failing closed to `DATA_UNAVAILABLE` rather than defaulting to an optimistic reclaim authorization.

#### 3.7 Historical Filing Facts vs. Negative Evidence Expiry
Negative supplier filing evidence (`VERIFIED_NOT_FILED`) requires a strict 30-day freshness window because a supplier who had not filed 35 days ago may have filed yesterday.
Conversely, **positive filing is an immutable historical statutory fact**: once a supplier files GSTR-3B with an official ARN on a specific date, that fact remains true permanently. Therefore, positive evidence validation does *not* subject historical filing facts to artificial 30-day expiry, avoiding bogus rejection of legitimate reclaims.

#### 3.8 Cryptographic Provenance
Every validated positive filing produces a deterministic SHA-256 hash incorporating `company_id`, `voucher_id`, `supplier_gstin`, `return_period`, `evidence_source`, `status`, `arn`, and `filing_date`. This guarantees end-to-end auditability and tamper evidence.
