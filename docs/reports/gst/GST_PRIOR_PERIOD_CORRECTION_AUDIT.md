# SriLekh — Prior-Period GST Correction & Adjustment Capability Audit

**Date:** 20 November 2026  
**Auditor:** Senior Indian GST Compliance Architect, Django Engineer & Accounting Auditor  
**Repository:** `https://github.com/prakhar2207/Vouch`  
**Branch Audited:** `main` (Certified Commit: `640f3e9`)  
**Staging Database Target:** Neon `neondb_staging` (Fingerprint: `6f4741bdaaf4`)  
**Dedicated Sandbox Tenant:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) — *Strictly Protected (Zero Access)*

---

## 1. Executive Summary & Verdict

### Audit Verdict: `PARTIALLY IMPLEMENTED — CORE ACCOUNTING SOUND, GST RETURN AMENDMENT ENGINE INCOMPLETE`

This audit evaluates whether SriLekh's current `main` branch supports accountants correcting previous-month accounting and GST mistakes in a later month.

### Key Audit Findings
1. **Double-Entry Accounting Layer is Robust:**
   SriLekh adheres strictly to double-entry accounting invariants. Posted vouchers are never silently mutated or deleted. Corrections and reversals create explicit balancing `JOURNAL` vouchers (`VoucherService.create_reversal_voucher`) with opposite debits/credits, dated on the day of reversal, maintaining $\sum \text{Debits} == \sum \text{Credits}$ and recalculating party/stock balances.
2. **Critical Architecture Gap in GST Return Allocation:**
   Both `GSTReturnsService.prepare_gstr1` and `prepare_gstr3b` filter transactions strictly by `voucher_date__gte=start_date, voucher_date__lte=end_date` derived from the selected return period. Because there is no concept of a separate "GST Filing / Effective Tax Period" independent of the transaction date:
   - A missed January sales invoice entered in February with a January date is **completely excluded** from February's GSTR-1 and GSTR-3B.
   - A late-received January purchase bill entered in February with its authentic vendor invoice date is **completely excluded** from February's GSTR-3B Table 4 ITC claim.
3. **GSTR-1 Amendment Tables are Stubbed:**
   In `GSTReturnsService.prepare_gstr1` (lines 500–510), all official GSTR-1 amendment tables (`b2ba`, `b2cla`, `b2csa`, `cdnra`, `cdnura`, `expa`, `ata`, `txpda`) are hardcoded as empty arrays (`[]`). While the schema accepts them, the engine cannot generate Table 9A/9B/9C/10 amendments.
4. **GSTR-3B Reversals & Reclaims are Stubbed:**
   In `GSTReturnsService.prepare_gstr3b` (lines 1052–1066), Table 4(B) ITC Reversals (Rules 42, 43, 37, 38) and Table 4(D) ITC Ineligible/Reclaimed are hardcoded to `0.00`.
5. **Filed Period Protection is Missing:**
   There is no locking mechanism preventing users from reversing or editing metadata on vouchers belonging to periods where `GSTFilingRecord` is marked `FILED` or `GSTReturnWorkspace` is marked `EXPORTED`.

---

## 2. Detailed Capability Assessment Matrix

Below is the classification of the 10 required correction and adjustment capabilities:

| # | Capability | Classification | Primary Models & Services | Gap / Limiting Factor |
|---|---|:---:|---|---|
| **1** | Adding a missed previous-month sales invoice | **PARTIALLY IMPLEMENTED** | `Voucher`, `VoucherService`, `returns_service.py` | Accounting posts cleanly; but `prepare_gstr1` filters by `voucher_date`, so it is excluded from current month's GSTR-1. |
| **2** | Adding a late-received purchase invoice | **PARTIALLY IMPLEMENTED** | `Voucher`, `reconciliation_service.py`, `returns_service.py` | Reconciles in GSTR-2B; but excluded from current month GSTR-3B Table 4 ITC due to `voucher_date` period filter. |
| **3** | Amending a previously reported sales invoice | **NOT IMPLEMENTED** | `Voucher`, `returns_service.py:prepare_gstr1` | GSTR-1 Table 9A (`b2ba`), 9B (`b2cla`), 10 (`b2csa`) are hardcoded empty lists `[]`. |
| **4** | Correcting GSTIN, POS, taxable value, or tax rate | **PARTIALLY IMPLEMENTED** (Accounting Only) | `FindingFixService.reassign_party`, `voucher_service.py` | Reversal journal + replacement voucher works in ledgers; fails to generate Table 9A GST amendment. |
| **5** | Recording a missed credit/debit note | **IMPLEMENTED AND VERIFIED** | `Voucher(voucher_type='CREDIT_NOTE')`, `returns_service.py` | Fully mapped to GSTR-1 Table 9B (`cdnr`/`cdnur`) with original invoice reference (`inum`, `idt`). |
| **6** | Reversing wrongly claimed ITC | **NOT IMPLEMENTED** | `returns_service.py:prepare_gstr3b` | GSTR-3B Table 4(B) (`itc_reversed`) is hardcoded to `0.00`. No linkage to ITC hold actions. |
| **7** | Reclaiming previously reversed ITC | **NOT IMPLEMENTED** | `returns_service.py:prepare_gstr3b` | GSTR-3B Table 4(D)(1) reclaim of reversed ITC is completely omitted from the summary payload. |
| **8** | Correcting an earlier RCM liability | **PARTIALLY IMPLEMENTED** | `Voucher(is_reverse_charge=True)`, `returns_service.py` | Works if voucher is dated in current month; prior-period RCM cannot be reported late; Section 50 interest absent. |
| **9** | Handling correction after return is filed | **NOT IMPLEMENTED** | `GSTReturnWorkspace`, `GSTFilingRecord` | Filed periods are not locked; vouchers can be reversed without creating subsequent period GST adjustments. |
| **10** | Blocking corrections after statutory deadlines | **NOT IMPLEMENTED** (Advisory Only) | `itc_reconciliation_service.py:get_sec16_4_expiry_radar` | Advisory radar warns of 30th Nov expiry, but no hard blocking exists in `post_voucher` or return engine. |

---

## 3. Deep Architectural Inspection (Phase 1)

### 3.1. GST Return Workspace & Lifecycle
- **Model:** `apps/gst/models.py:GSTReturnWorkspace`
- **Lifecycle Statuses:** `NOT_STARTED` $\rightarrow$ `DRAFT` $\rightarrow$ `VALIDATION_REQUIRED` $\rightarrow$ `READY_FOR_REVIEW` $\rightarrow$ `REVIEWED` $\rightarrow$ `EXPORTED`
- **Drift Detection:** `GSTWorkspaceService.check_drift` calculates SHA-256 hash across all vouchers in `(start_date, end_date)`. If vouchers change, `workspace.is_stale = True`, and `export_return` blocks export until refreshed.
- **Vulnerability:** `workspace.status` does not have a `FILED` state. Calling `generate_draft` on an `EXPORTED` workspace unconditionally overwrites `draft_payload`, obliterating the historical record of what was exported.

### 3.2. GSTR-1 Payload Builder & Amendment Tables
- **File:** `apps/gst/services/returns_service.py:prepare_gstr1`
- **Inspection Finding:**
  ```python
  official_json = {
      "gstin": supplier_gstin,
      "fp": period_code,
      "version": "GST3.1.2",
      "cur_gt": float(total_txval + total_tax),
      "b2b": b2b_payload,
      "b2ba": [],      # Table 9A: Amended B2B (HARDCODED EMPTY)
      "b2cl": b2cl_payload,
      "b2cla": [],    # Table 9A: Amended B2CL (HARDCODED EMPTY)
      "b2cs": b2cs_payload,
      "b2csa": [],    # Table 10: Amended B2CS (HARDCODED EMPTY)
      "cdnr": cdnr_payload,
      "cdnra": [],    # Table 9C: Amended CDNR (HARDCODED EMPTY)
      "cdnur": cdnur_list,
      "cdnura": [],   # Table 9C: Amended CDNUR (HARDCODED EMPTY)
      "exp": exp_list,
      "expa": [],     # Table 9A: Amended Exports (HARDCODED EMPTY)
      "nil": nil_payload,
      "at": advances_received_list,
      "ata": [],      # Table 11A(1): Amended Advances (HARDCODED EMPTY)
      "txpd": advances_adjusted_list,
      "txpda": [],    # Table 11B(1): Amended Adjustments (HARDCODED EMPTY)
      "hsn": {"data": hsn_payload},
      "doc_issue": {"doc_det": doc_details}
  }
  ```
  SriLekh cannot generate GSTR-1 amendment payloads.

### 3.3. GSTR-3B Preparation & Adjustment Logic
- **File:** `apps/gst/services/returns_service.py:prepare_gstr3b`
- **Inspection Finding:**
  ```python
  table_4_itc = {
      "itc_available": { ... },
      "itc_reversed": {
          "as_per_rules_42_43": {"igst": 0.00, "cgst": 0.00, "sgst": 0.00, "cess": 0.00},
          "others": {"igst": 0.00, "cgst": 0.00, "sgst": 0.00, "cess": 0.00}
      },
      "net_itc_available": { ... },
      "itc_ineligible": {
          "as_per_sec_17_5": {"igst": 0.00, "cgst": 0.00, "sgst": 0.00, "cess": 0.00},
          "others": {"igst": 0.00, "cgst": 0.00, "sgst": 0.00, "cess": 0.00}
      }
  }
  ```
  Both Table 4(B) (Reversals) and Table 4(D) (Ineligible & Reclaims) are hardcoded to zero. There is no support for Section 50 interest calculations on late payment of tax or differential tax liability.

### 3.4. Voucher Immutability, Reversal & History Tracking
- **Model:** `apps/accounting/models.py:Voucher`
- **Fields Present:** `revision_of`, `superseded_by`, `reversal_voucher`, `corrects_voucher`, `original_invoice`, `correction_type`, `correction_reason`, `corrected_by`, `corrected_at`.
- **Reversal Engine (`VoucherService.create_reversal_voucher`):**
  - Acquires exclusive row lock `select_for_update()`.
  - Reverts stock movements atomically via `StockService.revert_voucher_stock`.
  - Creates a balancing `JOURNAL` voucher (`REV-<voucher_number>`) dated **today** (`timezone.now().date()`).
  - Generates exact inverse `LedgerEntry` items in deterministic lock order.
  - Transitions original voucher status to `'REVERSED'`.
  - Recalculates single-source-of-truth balances on affected ledgers.

---

## 4. Accounting Invariants Verification (Phase 2)

| Invariant | System Behavior | Verdict |
|---|---|:---:|
| **Original Dates Preserved** | When a voucher is reversed, its `voucher_date` is untouched. The reversal voucher receives `timezone.now().date()`. | **VERIFIED** |
| **No Silent Mutation** | `VoucherService.edit_posted_voucher_metadata` only permits updating narration, reference number, and voucher number/date. Financial amounts, tax heads, and ledger entries cannot be mutated without a reversal. | **VERIFIED** |
| **Linked Auditable Adjustments** | Reversal vouchers link via `voucher.reversal_voucher` and `reversal_voucher.reversal_voucher`. Replaced vouchers link via `corrects_voucher`. | **VERIFIED** |
| **Mathematical Equilibrium** | Reversal vouchers post exact opposite debits and credits: $\sum \text{Debits} == \sum \text{Credits}$. Balance rebuild verifies zero imbalance. | **VERIFIED** |
| **Stock & Ledger Consistency** | `StockService.revert_voucher_stock` and `recalculate_ledger_balance` guarantee that party khata and godown stock are immediately restored. | **VERIFIED** |
| **Duplicate Prevention** | `create_reversal_voucher` checks `voucher.reversal_voucher_id is not None` and raises `ValidationError` on duplicate reversal calls. `TransactionDeduplicationEngine` prevents duplicate voucher creation. | **VERIFIED** |
| **Filed Return Immutability** | `GSTFilingRecord` stores cryptographic SHA-256 `payload_hash`. However, vouchers belonging to that period are **not locked** against reversal, creating a mismatch between filed returns and books. | **GAP IDENTIFIED** |

---

## 5. GST Statutory Analysis (Phase 3)

### 5.1. Section 37(3): Outward Supply Rectification
- **Statutory Rule:** Rectifications of omissions or errors in GSTR-1 are barred after **30th November** following the end of the financial year (or the date of furnishing the annual return, whichever is earlier).
- **Current SriLekh Status:** No check exists in `post_voucher` or GSTR-1 generation to prevent late entry or amendments after 30th November.

### 5.2. Section 39(9): GSTR-3B Error Rectification
- **Statutory Rule:** Return particulars cannot be revised once filed. Errors must be corrected in the return of the month in which the error is discovered, subject to interest under Section 50(1) @ 18% p.a.
- **Current SriLekh Status:** SriLekh does not provide a mechanism to carry forward un-reported prior tax or differential tax into the current month's GSTR-3B Table 3.1.

### 5.3. Section 16(4): ITC Availment Time Limit
- **Statutory Rule:** ITC on an invoice/debit note cannot be claimed after **30th November** following the end of the financial year.
- **Current SriLekh Status:** `ITCReconciliationService.get_sec16_4_expiry_radar` provides an advisory query identifying expiring invoices. However, it does not prevent an accountant from posting or claiming an expired invoice.

### 5.4. Rule 37 & 37A: ITC Reversal & Reclaim
- **Statutory Rule:**
  - Rule 37: 180-day non-payment requires reversal in Table 4(B)(2) + Section 50 interest.
  - Section 16(2) Proviso: When payment is made to the supplier, the reversed ITC may be reclaimed in Table 4(A)(5) and reported in Table 4(D)(1) **without any time limit under Section 16(4)**.
- **Current SriLekh Status:** Table 4(B)(2) and Table 4(D)(1) are hardcoded to `0.00`.

---

## 6. Synthetic Test Execution & Evidence (Phase 4)

Executing the 12 synthetic test scenarios (`scratch/test_correction_scenarios.py`) yielded the following concrete execution evidence:

```
[January invoice discovered in February]
  voucher_date: 2026-01-15 | feb_period_range: 2026-02-01 to 2026-02-28
  included_in_feb_gstr1: False | included_in_feb_gstr3b: False
  Evidence: EXCLUDED from Feb return; included in Jan return if regenerated. Cannot report in Feb GSTR-1 without Table 4/amendment mechanism.

[January invoice discovered in November]
  voucher_date: 2026-01-15 | nov_period_range: 2026-11-01 to 2026-11-30
  included_in_nov_gstr1: False
  Evidence: EXCLUDED from Nov return; system does not allocate prior period unfiled invoices into Nov return.

[Prior FY invoice discovered after amendment deadline]
  statutory_deadline: 30th November following FY end (Section 37(3) & 16(4))
  system_blocks_posting: False | system_radar_warning: True
  Evidence: System allows posting in accounting (unless books locked); does NOT enforce GST statutory bar at voucher level.

[Purchase invoice received late]
  voucher_date: 2026-01-10 | recon_matches: True | included_in_feb_gstr3b_itc: False
  Evidence: GSTR-2B reconciliation matches it, but GSTR-3B Table 4 excludes it from February ITC claim due to voucher_date filter.

[ITC claim already made and subsequently reversed]
  table_4_b_populated: False
  Evidence: Table 4(B) is hardcoded to 0.00; no automatic flow from ITC reversal vouchers or hold status.

[ITC reclaim under Rule 37 proviso / Rule 37A]
  table_4_d_1_reclaim_supported: False
  Evidence: GSTR-3B schema does not populate Table 4(D)(1) reclaimed ITC.

[Duplicate correction submission]
  reversal_guard: Checked | dedup_engine: Active
  Evidence: PROTECTED in accounting layer against duplicate reversal or voucher re-creation.

[Correction after GSTR-1 export but before filing]
  drift_detected: True | export_blocked_on_drift: True
  Evidence: Drift guard detects changes and blocks export until draft is regenerated. However, regeneration silently replaces previously exported payload without preserving amendment delta.

[Correction after a return is filed]
  voucher_locked_by_filing: False | workspace_locked_by_filing: False
  Evidence: No foreign key or constraint prevents reversing a voucher belonging to a filed return period. GSTR-1 does not route the correction to Table 9A of the next period.

[Attempt to alter frozen return snapshot]
  immutability: GSTFilingRecord is immutable (SHA-256 payload_hash). GSTReturnWorkspace.generate_draft overwrites draft_payload if called again.

[Wrong GSTIN and POS corrections]
  Evidence: Accounting ledger is corrected via reversal journal + new voucher, but GSTR-1 amendment payload is NOT generated.

[Tax rate correction with differential liability]
  Evidence: Table 9A (b2ba) is empty; prepare_gstr3b has no field for differential tax or Section 50 interest.
```

---

## 7. Architectural Root Cause Analysis

Why does SriLekh currently struggle with prior-period GST corrections?

```
CURRENT ARCHITECTURE (STRICT VOUCHER_DATE FILTERING):
+--------------------+        +---------------------+        +--------------------+
| Voucher Created    | -----> | voucher_date:       | -----> | Included ONLY in   |
| (in Feb for Jan)   |        | 15-Jan-2026         |        | Jan 2026 Return!   |
+--------------------+        +---------------------+        +--------------------+
                                                                       |
                                                                       v
                                                      [If Jan is FILED, this invoice]
                                                      [is ORPHANED from GST portal!]

REQUIRED ARCHITECTURE (DUAL DATE / RETURN ALLOCATION):
+--------------------+        +---------------------+        +--------------------+
| Voucher Created    | -----> | voucher_date:       | -----> | Accounting Ledger  |
| (in Feb for Jan)   |        | 15-Jan-2026         |        | (Historical Truth) |
+--------------------+        +---------------------+        +--------------------+
         |
         v
+--------------------+        +---------------------+        +--------------------+
| gst_filing_period: | -----> | Allocated to:       | -----> | Included in Feb    |
| "022026"           |        | Feb 2026 GSTR-1/3B  |        | Return (Table 4/9) |
+--------------------+        +---------------------+        +--------------------+
```

1. **Coupling of Accounting Date and GST Return Period:**
   SriLekh assumes `return_period` is strictly equal to the month of `voucher_date`. In professional Indian accounting, a voucher has two distinct dates:
   - **Voucher Date (`voucher_date`):** The actual invoice date (for aging, credit limits, 180-day rule).
   - **Effective Tax Period (`gst_filing_period`):** The GST tax period in which the transaction is declared to the government.
2. **Missing `b2ba` / `cdnra` Serializers:**
   The GST return preparation service was designed for first-time period filings, with amendment sections left as stubbed empty lists.
3. **Decoupled Filing Records:**
   `GSTFilingRecord` exists as an audit record, but has no referential integrity link (`ForeignKey` or lock flag) to the vouchers that comprised that filing.

---

## 8. Prioritized Implementation & Remediation Roadmap

To make SriLekh fully compliant with Indian GST prior-period correction requirements, execute the following staged remediation:

### Phase 1: Return Period Allocation & Late-Entry Support (Priority: P0 - Critical)
1. **Add `gst_filing_period` to `Voucher`:**
   Add `gst_filing_period = models.CharField(max_length=10, null=True, blank=True)` to `Voucher`. Defaults to `voucher_date`'s period, but can be assigned to the current open tax period for late-received invoices.
2. **Update `prepare_gstr1` and `prepare_gstr3b` Queries:**
   Query vouchers where `gst_filing_period == return_period` (or `voucher_date__range` as fallback).
   This immediately enables:
   - Claiming late purchase invoices in the current month's GSTR-3B Table 4.
   - Reporting late-discovered sales invoices in the current month's GSTR-1 Table 4.

### Phase 2: Filed Period Lock & Snapshot Immutability (Priority: P0 - Critical)
1. **Enforce Filing Lock on Vouchers:**
   In `VoucherService.post_voucher`, `create_reversal_voucher`, and `edit_posted_voucher_metadata`:
   Check whether `GSTFilingRecord.objects.filter(company=voucher.company, return_period=voucher.gst_filing_period, status='FILED').exists()`.
   If filed, **block direct modification** and mandate an explicit amendment workflow.
2. **Lock `GSTReturnWorkspace` on Export/Filing:**
   Disallow `generate_draft` when status is `EXPORTED` or `FILED` unless an explicit "Unlock / Create Revision" action is taken.

### Phase 3: GSTR-1 Amendment Engine (Table 9A, 9B, 9C, 10) (Priority: P1 - High)
1. **Implement `b2ba` and `cdnra` Builders:**
   When a sales voucher is revised via `revisions`, or an amendment voucher is posted referencing an original invoice from a filed period:
   Populate Table 9A (`b2ba`) with:
   - Original invoice number (`oinum`) & original date (`oidt`).
   - Revised invoice number (`inum`), revised date (`idt`), revised value (`val`), revised POS, and revised rate items.
2. **Implement Table 10 (`b2csa`) Amendments:**
   Allow net differential adjustments to prior-period unregistered supplies by POS and tax rate.

### Phase 4: GSTR-3B Table 4(B) Reversals & 4(D)(1) Reclaim Engine (Priority: P1 - High)
1. **Rule 37 180-Day Automated Reversal Engine:**
   Identify purchase vouchers unpaid after 180 days. Automatically populate Table 4(B)(2) `others` with reversing ITC amounts.
2. **Rule 37 Proviso Reclaim Engine:**
   When payment is allocated to an unpaid voucher, automatically populate Table 4(A)(5) and Table 4(D)(1) with reclaimed ITC.
3. **Section 50 Interest Calculator:**
   Compute statutory interest @ 18% p.a. on late tax payments or Rule 37 reversals.

### Phase 5: Statutory Deadline Enforcer (Priority: P2 - Compliance Gate)
1. **Section 16(4) Hard Gate:**
   Raise `ValidationError` in `post_voucher` if an accountant attempts to claim ITC on an invoice whose preceding FY deadline (30th November) has passed.
2. **Section 37(3) Hard Gate:**
   Disallow outward invoice amendments for a prior FY after 30th November.

---

## 9. Conclusion

SriLekh's underlying accounting, ledger posting, and cryptographic audit trails are completely sound. The core reason prior-period corrections cannot currently flow into GST returns is the strict filtering of return tables by transaction `voucher_date` rather than an allocated `gst_filing_period`, coupled with stubbed amendment tables (`b2ba`, Table 4(B)).

Implementing the phased remediation plan above will make SriLekh a market-leading, fully compliant GST ERP capable of handling real-world MSME accounting errors and adjustments seamlessly.

**Audit Completed By:** Senior Indian GST Compliance Architect & Accounting Auditor  
**Final Status:** `AUDIT COMPLETE — REMEDIATION ROADMAP PREPARED`
