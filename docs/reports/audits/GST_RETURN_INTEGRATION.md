# SriLekh — GST Return Integration Architecture (GSTR-1 & GSTR-3B)

## 1. Overview

SriLekh provides automated preparation, exception auditing, JSON export, and direct Sandbox submission for:
1. **GSTR-1**: Monthly/Quarterly statement of outward supplies.
2. **GSTR-3B**: Monthly self-declared summary return of outward liabilities and Input Tax Credit (ITC).

All return data is derived **read-only** from SriLekh's posted double-entry sales vouchers and credit/debit notes.

---

## 2. GSTR-1 Table-by-Table Mapping Architecture

SriLekh's `GSTReturnsService` automatically categorizes outward transactions into statutory GSTR-1 tables:

| GSTR-1 Table | Category Name | Criteria & Business Logic | Source Models |
| :--- | :--- | :--- | :--- |
| **Table 4A, 4B, 4C, 6B, 6C** | **B2B Invoices** | Regular supplies to registered taxable persons with valid recipient GSTIN. | `Voucher` (type=`SALES`, status=`POSTED`, buyer has valid 15-char GSTIN) |
| **Table 5A, 5B** | **B2CL (Large)** | Unregistered (B2C) interstate supplies where invoice value exceeds ₹2,50,000. | `Voucher` (type=`SALES`, buyer has no GSTIN, interstate supply, `total_amount > 250000`) |
| **Table 7** | **B2CS (Small)** | Unregistered (B2C) intrastate supplies, OR interstate supplies ≤ ₹2,50,000. Aggregated by Place of Supply (POS) and Tax Rate. | `Voucher` (type=`SALES`, buyer has no GSTIN, not B2CL) |
| **Table 9B (Registered)** | **CDNR** | Credit and Debit Notes issued to registered persons (references original invoice). | `Voucher` (type in `['CREDIT_NOTE', 'DEBIT_NOTE']`, buyer has GSTIN) |
| **Table 9B (Unregistered)** | **CDNUR** | Credit and Debit Notes issued to unregistered recipients for B2CL supplies. | `Voucher` (type in `['CREDIT_NOTE', 'DEBIT_NOTE']`, buyer has no GSTIN) |
| **Table 6A** | **EXP (Exports)** | Zero-rated export supplies (with or without payment of tax). | `Voucher` (type=`SALES`, supply_type=`EXPORT`) |
| **Table 12** | **HSN Summary** | Summary of outward supplies aggregated by 4, 6, or 8-digit HSN/SAC code, quantity, and tax rates. | `VoucherItem` grouped by `hsn_code` and `tax_rate` |
| **Table 13** | **Doc Issue Summary**| Serial numbering range and count of invoices, credit notes, and debit notes issued and cancelled during the period. | `Voucher` serial ranges (`from_serial`, `to_serial`, `total_count`, `cancelled_count`) |

---

## 3. Pre-Filing Validation Checks & Exception Reporting

Before generating the official GSTR-1 JSON or transmitting it to Sandbox, `GSTReturnsService.get_gstr1_data()` executes an automated pre-filing audit.

Any transaction violating GST statutory rules is flagged in `validation_errors`:
1. **Missing or Malformed Recipient GSTIN**: Buyer marked as B2B but GSTIN fails the 15-character Luhn MOD-36 checksum.
2. **Missing HSN/SAC Code**: Line items lacking a valid 4-to-8 digit HSN code (mandatory under CGST Notification No. 78/2020).
3. **Interstate vs Intrastate Tax Rate Inconsistency**:
   - An interstate transaction having CGST/SGST instead of IGST.
   - An intrastate transaction having IGST instead of CGST/SGST.
4. **Invalid Place of Supply (POS)**: POS state code does not match recipient's registered state.
5. **Voucher Imbalance**: Mathematical difference between `sum(items)` and `total_amount`.

---

## 4. GSTR-3B Monthly Tax Summary Integration

SriLekh computes GSTR-3B monthly liabilities and ITC balances in real time:

### Table 3.1: Tax on Outward Supplies
- **Taxable Value**: Sum of taxable amounts across all posted sales vouchers.
- **IGST**: Total Integrated GST on interstate supplies.
- **CGST**: Total Central GST on intrastate supplies.
- **SGST**: Total State GST on intrastate supplies.
- **Cess**: Total GST compensation cess.

### Table 4: Eligible Input Tax Credit (ITC)
- **Part (A)(5) All Other ITC**: Total IGST, CGST, and SGST paid on purchase vouchers from registered suppliers.
- **Part (B) Ineligible / Blocked ITC**: ITC on goods blocked under Section 17(5) of the CGST Act (motor vehicles, food/beverages, personal consumption).

### Net Tax Payable
- Computed as `Max(0, Outward Liability - Eligible ITC)` considering inter-head adjustment order (IGST offset first, then CGST/SGST).

---

## 5. Tamper-Evident SHA-256 Payload Hashing

Whenever a return payload is generated or submitted to the Sandbox API, SriLekh records the return state in `GSTFilingRecord`:
- **`payload_hash`**: `SHA256(canonical_json_string)`.
- **`ack_number`**: Reference acknowledgment provided by the GST Portal / Sandbox.
- **`state`**: Transitions from `DRAFT` -> `VALIDATED` -> `SUBMITTED` -> `FILED`.
- **Immutability Guarantee**: Once marked `FILED`, the record cannot be modified, ensuring non-repudiation during tax audits.
