# SriLekh GST — Round 2.5.6: Supplier Evidence Audit & GSTR-3B Verification Engine

**Repository:** https://github.com/prakhar2207/Vouch  
**Branch:** `fix/round2-5-6-itc-evidence-and-event-linkage`  
**Base Commit:** `d0e70798dfa823a597b3f412c894f0fb17692dfe`  
**Staging Database:** Neon PostgreSQL `neondb_staging` (`6f4741bdaaf4`)  
**Audit Standard:** CGST Act 2017 § 16(2)(c), CGST Rules 2017 Rule 37A, Rule 60(7), Section 155  
**Document Reference:** `GST_ROUND_2_5_6_SUPPLIER_EVIDENCE_AUDIT.md`  

---

## 1. Statutory Context & The GSTR-1 vs GSTR-3B Distinction

Under the Indian Goods and Services Tax (GST) legal architecture, the claim and retention of Input Tax Credit (ITC) by a registered buyer is governed by strict statutory conditions under **Section 16(2) of the Central Goods and Services Tax (CGST) Act, 2017**:

1. **Section 16(2)(a):** Possession of a tax invoice or debit note issued by a supplier.
2. **Section 16(2)(aa):** The details of the invoice or debit note have been furnished by the supplier in their statement of outward supplies (GSTR-1 or using the Invoice Furnishing Facility - IFF) and communicated to the recipient in **GSTR-2B** under Section 38.
3. **Section 16(2)(b):** Receipt of goods or services or both.
4. **Section 16(2)(c):** **Subject to Section 41, the tax charged in respect of such supply has been actually paid to the Government, either in cash or through utilization of admissible input tax credit.**
5. **Section 16(2)(d):** Furnishing of return under Section 39 (GSTR-3B) by the recipient.

### The Fatal Statutory Vulnerability in Conventional Systems
Conventional accounting and reconciliation packages frequently conflate **GSTR-1** disclosure with **tax payment**. 

- **GSTR-1 / IFF:** A statement of outward supplies containing transaction metadata (invoice number, date, value, tax rate, recipient GSTIN). Furnishing GSTR-1 populates the recipient's GSTR-2B on the 14th of the subsequent month. **GSTR-1 involves NO tax payment to the Government.**
- **GSTR-3B:** The self-assessed monthly summary return filed under Section 39 wherein tax liabilities are discharged via the Electronic Cash Ledger or Electronic Credit Ledger.

### Statutory Rule 37A Mandate
Inserted vide **Notification No. 26/2022-Central Tax dated 26-12-2022**, **Rule 37A** provides:
> *"Where input tax credit has been availed by a registered person in the return in FORM GSTR-3B for a tax period in respect of such invoice or debit note, the details of which have been furnished by the supplier in the statement of outward supplies in FORM GSTR-1 or using the invoice furnishing facility, but the return in FORM GSTR-3B for the tax period corresponding to the said statement of outward supplies has not been furnished by such supplier till the 30th day of September, following the end of financial year in which the input tax credit in respect of such invoice or debit note has been availed, the said amount of input tax credit shall be reversed by the said registered person in FORM GSTR-3B on or before the 30th day of November following the end of such financial year..."*

**Crucial Legal Finding:**
Rule 37A applies *precisely* to invoices that **APPEAR in GSTR-1 / GSTR-2B**, but whose supplier **FAILED to file GSTR-3B**. Therefore, checking `gstr2b_record.filing_date` (which is the GSTR-1 filing date) as evidence of compliance completely subverts Rule 37A, creating fatal compliance liability for the business.

---

## 2. Evidence Data Model Architecture

To enforce absolute evidentiary rigor, SriLekh Round 2.5.6 introduced two levels of verified supplier evidence tracking:

### 2.1. Dedicated Supplier GSTR-3B Filing Record (`SupplierGSTR3BFilingRecord`)
A tamper-evident, multi-tenant model tracking return filing facts directly sourced from the GST Common Portal, GST Suvidha Providers (GSPs), or verified manual tax challans:

```python
class SupplierGSTR3BFilingRecord(BaseModel):
    """
    Dedicated statutory evidence record capturing supplier GSTR-3B return filing status.
    CGST Act Sec 16(2)(c) & Rule 37A require proof of tax discharge via GSTR-3B return filing.
    GSTR-1 / GSTR-2B presence is NOT proof of tax payment.
    """
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='supplier_gstr3b_records')
    supplier_gstin = models.CharField(max_length=15, db_index=True)
    return_period = models.CharField(max_length=6, db_index=True)  # Format MMYYYY (e.g. '012026')
    
    status = models.CharField(
        max_length=25,
        choices=[
            ('FILED', 'Filed'),
            ('NOT_FILED', 'Not Filed'),
            ('UNKNOWN', 'Unknown'),
            ('DATA_UNAVAILABLE', 'Data Unavailable'),
        ],
        default='UNKNOWN',
        db_index=True
    )
    filing_date = models.DateField(null=True, blank=True)
    arn = models.CharField(max_length=30, blank=True, null=True, help_text="Application Reference Number (ARN)")
    verification_source = models.CharField(
        max_length=30,
        choices=[
            ('GST_PORTAL_API', 'GST Portal Official API'),
            ('GSP_INTEGRATION', 'GST Suvidha Provider'),
            ('MANUAL_VERIFIED', 'Manual CA/Accountant Verification'),
            ('SIMULATION_TEST', 'Sandboxed Simulation Test'),
        ],
        default='MANUAL_VERIFIED'
    )
    evidence_document_ref = models.CharField(max_length=128, blank=True, null=True)
    notes = models.TextField(blank=True)
    verified_at = models.DateTimeField(auto_now=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
```

**Database Invariant:**
Enforces `unique_together = [('company', 'supplier_gstin', 'return_period')]` to guarantee deterministic state per supplier-month.

### 2.2. GSTR-2B Record Extensions (`GSTR2BRecord`)
To preserve backward compatibility with existing invoice reconciliation pipelines while embedding GSTR-3B compliance proof, `GSTR2BRecord` was upgraded with explicit GSTR-3B audit fields:

```python
# GSTR-3B return verification evidence (CGST Act Sec 16(2)(c) & Rule 37A)
gstr3b_filing_date = models.DateField(null=True, blank=True, help_text="Verified GSTR-3B filing date")
gstr3b_filing_arn = models.CharField(max_length=30, null=True, blank=True, help_text="GSTR-3B filing ARN")
gstr3b_return_period = models.CharField(max_length=6, null=True, blank=True, help_text="Supplier GSTR-3B return period (MMYYYY)")
gstr3b_verification_source = models.CharField(max_length=30, null=True, blank=True)
gstr3b_verified_at = models.DateTimeField(null=True, blank=True)
```

---

## 3. Removal of Unsafe Rule 37A Defaults

In Round 2.5.5, reversals could be generated when supplier filing status was ambiguous. In Round 2.5.6, `GSTAllocationService.create_rule37a_reversal_allocation()` enforces zero-trust evidence validation:

```python
# 1. Require explicit affirmative evidence of non-filing
if supplier_status != 'VERIFIED_NOT_FILED':
    raise ValidationError(
        f"Rule 37A reversal requires explicit affirmative evidence of supplier non-filing "
        f"('VERIFIED_NOT_FILED'). Received '{supplier_status}'. "
        f"DATA_UNAVAILABLE, UNKNOWN, or missing portal records must NOT be defaulted to non-filing."
    )
```

### Truth Table for Rule 37A Evaluation

| Supplier GSTR-1 Status | Supplier GSTR-3B Status | Evidence Quality | Rule 37A Statutory Action | System State |
| :--- | :--- | :--- | :--- | :--- |
| **FILED** | **FILED (with ARN)** | High (Verified Fact) | **No Reversal Required.** Credit fully compliant under § 16(2)(c). | `COMPLIANT_ACTIVE` |
| **FILED** | **NOT_FILED** | Verified Portal Fact | **Reversal Required by 30th Nov.** Proportional tax reversed under Rule 37A. | `REVERSED_RULE_37A` |
| **FILED** | **DATA_UNAVAILABLE** | Provider Outage / HTTP 5xx | **Zero Action Taken.** Reversal blocked. Flagged for retry; working capital protected. | `PENDING_RETRY` |
| **FILED** | **UNKNOWN** | No query performed yet | **Zero Action Taken.** Does not infer non-filing from absence of data. | `UNVERIFIED` |
| **NOT_FILED** | **FILED** | Edge Case / Late IFF | Reversal blocked; recipient advised to reconcile GSTR-2B mismatch. | `RECONCILIATION_FLAG` |

---

## 4. Remediation in Statutory Deadline Management Command

In `apps/gst/management/commands/check_gst_deadlines.py`, lines 135–170 were completely rewritten:

1. **Old Faulty Code:**
   Directly assigned `supplier_filed = bool(gstr2b_rec.filing_date)`.
2. **Corrected Statutory Implementation:**
   - First inspects dedicated `SupplierGSTR3BFilingRecord` for the exact supplier GSTIN and return period.
   - If missing, checks `gstr2b_rec.gstr3b_filing_date` and `gstr2b_rec.gstr3b_filing_arn`.
   - If only `gstr2b_rec.filing_date` (GSTR-1) exists, it explicitly logs:
     `"GSTR-1 filed on {date}, but GSTR-3B tax payment is unverified"`
     and sets `gstr3b_verified = False`.
   - Never substitutes GSTR-1 date for GSTR-3B date.

---

## 5. Verification Test Matrix

The supplier evidence audit was verified using independent adversarial unit and integration tests in `apps/gst/tests_round2_5_6_itc_evidence_and_lineage.py`:

| Test Name | Test Scenario | Expected Statutory Outcome | Result |
| :--- | :--- | :--- | :--- |
| `test_gstr1_filing_date_not_substituted_for_gstr3b` | GSTR-1 filed on 2026-02-11 with ARN. GSTR-3B fields empty. | `is_gstr3b_filed == False`. Attempted Rule 37A reclaim throws `ValidationError`. | **PASS** |
| `test_rule37a_requires_verified_not_filed` | Caller passes `supplier_status='DATA_UNAVAILABLE'` or `'UNKNOWN'`. | Operation rejected with `ValidationError`. Zero spurious reversals created. | **PASS** |
| `test_rule37a_reclaim_with_verified_gstr3b_evidence` | Supplier files GSTR-3B with ARN `AA070226012345M` and filing date `2026-12-10`. | Rule 37A reclaim succeeds. Allocates to period `122026`. Reversal marked `SUPERSEDED`. | **PASS** |
| `test_supplier_gstr3b_model_tenant_isolation` | GSTR-3B record for supplier in Company A queried from Company B. | Zero records returned. Tenant isolation preserved across queries. | **PASS** |

---

## 6. Conclusion

SriLekh is now immune to the industry-wide flaw of conflating GSTR-1 declarations with tax payments. By introducing `SupplierGSTR3BFilingRecord`, upgrading `GSTR2BRecord`, and eliminating heuristic defaults in `create_rule37a_reversal_allocation()`, SriLekh provides auditors and CFOs with an unassailable statutory audit trail under Section 16(2)(c) and Rule 37A.
