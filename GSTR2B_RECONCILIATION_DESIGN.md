# SriLekh — GSTR-2B Automated Reconciliation Engine Architecture

## 1. Overview & Objective

Input Tax Credit (ITC) claiming in India is strictly governed by **Section 16(2)(aa) of the CGST Act**, which mandates that a taxpayer may only avail ITC on invoices that have been furnished by suppliers in their GSTR-1 and reflected in the recipient's auto-drafted **GSTR-2B** statement.

Claiming ITC on missing or mismatched invoices invites GST notices, interest penalties under Section 50 (18% to 24%), and potential blockage of credit.

SriLekh's GSTR-2B Reconciliation Engine automates the matching of supplier invoices downloaded from Sandbox against SriLekh's posted purchase vouchers, categorizing every entry across **11 standardized mismatch categories**.

---

## 2. Ingestion & Normalization Pipeline

1. **Direct Sandbox Fetch**:
   - Client calls `POST /api/v1/gst/reconciliation/gstr2b/sync/` with `year` and `month`.
   - Sandbox client executes `GET /gst/compliance/tax-payer/gstrs/gstr-2b/{year}/{month}`.
   - Batch records are ingested into `GSTR2BImport` and individual lines into `GSTR2BRecord`.
2. **Invoice Number Normalization**:
   - Invoices often have punctuation variances between accounting books and GST portal (e.g. `INV/2026/001` vs `INV-2026-001` vs `INV2026001`).
   - `GSTReconciliationService.normalize_invoice_number()` strips whitespace, hyphens, slashes, and leading zeros, converting the number to a canonical uppercase alphanumeric string.
3. **Date & Tax Quantization**:
   - Dates are parsed to canonical `YYYY-MM-DD`.
   - Currency values are quantized to standard 2-decimal places (`Decimal('0.01')`) with a statutory rounding tolerance of `₹2.00`.

---

## 3. The 11 Mismatch Categories & Logic Engine

| Category Code | Display Name | Mathematical / Logical Criteria | Recommended Action |
| :--- | :--- | :--- | :--- |
| **`MATCHED`** | Exact Match | Key match (`supplier_gstin` + `normalized_invoice_no`), date difference ≤ 3 days, total difference ≤ ₹2.00, and exact tax breakdown (IGST/CGST/SGST) match. | Auto-Eligible for GSTR-3B ITC Claim. |
| **`PARTIAL_MATCH`** | Approximate Match | Key match, but difference in taxable amount or total value between ₹2.00 and ₹50.00. | Review rounding or freight/discount discrepancy. |
| **`MISSING_IN_BOOKS`** | Missing in Books | Record exists in GSTR-2B, but no corresponding purchase voucher exists in SriLekh. | User can generate draft purchase voucher in 1 click. |
| **`MISSING_IN_2B`** | Missing in GSTR-2B | Purchase voucher posted in SriLekh, but supplier has not filed GSTR-1 or invoice not in 2B. | Defer ITC claim; trigger payment hold or supplier alert. |
| **`TAX_MISMATCH`** | Tax Breakdown Mismatch | Total values match, but tax breakdown differs (e.g. Books recorded IGST ₹900 while 2B recorded CGST ₹450 + SGST ₹450). | Correct voucher tax heads to match supplier filing. |
| **`GSTIN_MISMATCH`** | GSTIN Discrepancy | Invoice number and amounts match, but supplier GSTIN differs (e.g. multi-state branch GSTIN used). | Verify supplier billing entity and branch GSTIN. |
| **`DOC_NUM_MISMATCH`**| Document Number Variant | Supplier GSTIN, date, and amounts match exactly, but invoice number differs slightly beyond normalization. | Manual link and accept match. |
| **`DATE_MISMATCH`** | Date Discrepancy | Invoices match on GSTIN and number, but invoice dates differ by > 30 days (cross-period filing). | Verify supply period and claim in current return. |
| **`DUPLICATE`** | Duplicate Invoice | Multiple 2B records or multiple purchase vouchers found for the same supplier invoice. | Reject duplicate to prevent dual ITC claim. |
| **`INELIGIBLE_ITC`** | Statutory Ineligible | Supplier has marked `itc_availability = 'N'` or Place of Supply rule makes credit ineligible. | Exclude from Table 4(A)(5) and report in Table 4(B). |
| **`MISMATCHED`** | General Discrepancy | Multiple conflicting differences that require manual review. | Flag for accountant review. |

---

## 4. User Review & Decision Workflow

In the Next.js GST Center (`/gst` under the GSTR-2B tab), accountants can:
1. **Filter by Category**: Quickly isolate `MISSING_IN_2B` to hold vendor payments, or `TAX_MISMATCH` to fix tax heads.
2. **Accept Record**: Mark record as `review_status = 'ACCEPTED'`.
3. **Dispute Record**: Mark record as `review_status = 'DISPUTED'` and enter dispute notes.
4. **Hold Vendor Payment**: For invoices missing in 2B, automatically place a hold flag on the vendor's ledger balance until GSTR-1 filing is confirmed.

---

## 5. Audit Trail & Non-Repudiation

All reconciliation actions update `GSTR2BRecord.review_status` with timestamps and user identifiers. Decisions are permanently archived in `GSTAuditLog` for statutory GST audits.
