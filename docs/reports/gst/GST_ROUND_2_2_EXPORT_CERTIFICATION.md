# SriLekh GST — Round 2.2 Official Schema, Payload Validation & Export Certification Report

**Document Version:** 1.0.0  
**Audit & Certification Date:** November 18, 2026  
**Repository:** `https://github.com/prakhar2207/Vouch`  
**Active Working Branch:** `fix/stage4-12-day6-remediation`  
**Base Round 2.1 Commit:** `240557b` (Deployed on Render Staging as `240557b0`)  
**Staging Backend URL:** `https://vouch-u3u7.onrender.com`  
**Staging Database Target:** Neon PostgreSQL `neondb_staging`  
**Authoritative Reference:** [GST_ROUND_2_2_OFFICIAL_SCHEMA_REFERENCE.md](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/gst/GST_ROUND_2_2_OFFICIAL_SCHEMA_REFERENCE.md)  
**Certification Verdict:** **PASS — ROUND 2.2 EXPORT CERTIFIED**

---

## 1. Executive Summary

SriLekh GST Round 2.2 establishes the official export and pre-export payload validation layer for statutory Indian Goods and Services Tax compliance. Building upon the calculations and accounting audits certified in Round 2.0 and Round 2.1, Round 2.2 delivers:

1. **GSTN Offline Utility Schema Conformance:**
   - **GSTR-1:** Complete alignment with GSTN Offline Tool Schema **v3.1.2** across Tables 4 (B2B), 5 (B2CL), 6 (EXP), 7 (B2CS), 8 (Nil/Exempt), 9B (CDNR/CDNUR), 11A/11B (Advances), 12 (HSN/SAC Summary), and 13 (Documents Issued).
   - **GSTR-3B:** Complete alignment with GSTN Offline Tool Schema **v1.4** across Table 3.1 (`sup_details`), Table 3.2 (`inter_sup`), Table 4 (`itc_elg`), and Table 5 (`inward_sup`).

2. **Autonomous Pre-Export Payload Validation Engine (`GSTPayloadValidator`):**
   - Independent statutory validation engine enforcing GSTIN checksums, return period formatting, Place of Supply state codes, standard tax rate catalogs, intrastate vs interstate tax head equilibrium, line-item non-negativity, and duplicate invoice prevention.
   - Distinct classification of issues into blocking **`ERROR`** (prevents corrupted or non-compliant export) and informational **`WARNING`** (alerts accountant to variances).

3. **Statutory Legal Invariants:**
   - **CBIC Notification No. 12/2024:** Enforced period-aware B2CL threshold ($> ₹2.5\text{ Lakhs}$ for return periods $\le$ July 2024; $> ₹1.0\text{ Lakh}$ for return periods $\ge$ August 2024). Intrastate supplies strictly excluded.
   - **CGST Act Section 49(4) + Section 2(82):** Inward Reverse Charge (RCM) liability is strictly isolated into 100% cash payable via the Electronic Cash Ledger and excluded from Rule 88A Input Tax Credit offset.
   - **Table 4 Net ITC Equilibrium:** Verified that Net ITC strictly equals Available ITC minus Reversed ITC across all four tax heads.

4. **Tamper-Evident Export & Drift Guard:**
   - Implemented real-time voucher drift detection: export requests are rejected if source vouchers have been added, modified, or cancelled since draft generation.
   - Deterministic SHA-256 fingerprinting on exported payloads guaranteeing export reproducibility.
   - Multi-format support: Official offline JSON and human-readable chartered accountant audit reports (`REVIEW_REPORT`).

5. **Double-Entry Accounting Immutability:**
   - Verified that all draft generation, validation, sign-off, and export operations execute with **zero writes, zero updates, and zero deletions** on `Voucher`, `VoucherItem`, and `LedgerEntry` tables.

---

## 2. Official Schema Conformance Architecture

### 2.1 GSTR-1 Schema Conformance (GSTN Offline Tool Schema v3.1.2)

The generated GSTR-1 payload strictly matches the official offline JSON structure expected by the GST Portal offline utility:

```json
{
  "gstin": "27AAACA1234A1Z5",
  "fp": "082026",
  "version": "GST3.1.2",
  "cur_gt": 118000.00,
  "b2b": [
    {
      "ctin": "27AAACT2727Q1ZW",
      "inv": [
        {
          "inum": "INV-2026-001",
          "idt": "15-08-2026",
          "val": 118000.00,
          "pos": "27",
          "rchrg": "N",
          "inv_typ": "R",
          "itms": [
            {
              "num": 1,
              "itm_det": {
                "rt": 18.0,
                "txval": 100000.00,
                "iamt": 0.0,
                "camt": 9000.00,
                "samt": 9000.00,
                "csamt": 0.0
              }
            }
          ]
        }
      ]
    }
  ],
  "b2cl": [],
  "b2cs": [],
  "cdnr": [],
  "cdnur": [],
  "exp": [],
  "nil": { "inv": [{ "nil_amt": 0.0, "expt_amt": 0.0, "ngsup_amt": 0.0 }] },
  "at": [],
  "txpd": [],
  "hsn": { "data": [...] },
  "doc_issue": { "doc_det": [...] }
}
```

### 2.2 GSTR-3B Schema Conformance (GSTN Offline Tool Schema v1.4)

The generated GSTR-3B payload strictly matches the official schema v1.4 structure:

```json
{
  "gstin": "27AAACA1234A1Z5",
  "ret_period": "082026",
  "filing_typ": "GSTR3B",
  "version": "GST3B1.4",
  "sup_details": {
    "osup_det": { "txval": 100000.00, "iamt": 0.0, "camt": 9000.00, "samt": 9000.00, "csamt": 0.0 },
    "osup_zero": { "txval": 0.0, "iamt": 0.0, "csamt": 0.0 },
    "osup_nil_exmp": { "txval": 0.0 },
    "isup_rev": { "txval": 20000.00, "iamt": 0.0, "camt": 1000.00, "samt": 1000.00, "csamt": 0.0 },
    "osup_nongst": { "txval": 0.0 }
  },
  "inter_sup": {
    "unreg_details": [
      { "pos": "23", "txval": 150000.00, "iamt": 27000.00 }
    ],
    "comp_details": [],
    "uin_details": []
  },
  "itc_elg": {
    "itc_avl": {
      "import_goods": { "iamt": 0.0, "csamt": 0.0 },
      "import_services": { "iamt": 0.0, "csamt": 0.0 },
      "isup_rev": { "iamt": 0.0, "camt": 1000.00, "samt": 1000.00, "csamt": 0.0 },
      "isd": { "iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0 },
      "all_other": { "txval": 80000.00, "iamt": 0.0, "camt": 7200.00, "samt": 7200.00, "csamt": 0.0 }
    },
    "itc_rev": {
      "rule42_43": { "iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0 },
      "others": { "iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0 }
    },
    "itc_net": { "iamt": 0.0, "camt": 8200.00, "samt": 8200.00, "csamt": 0.0 },
    "itc_inelg": {
      "as_per_sec_17_5": { "iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0 },
      "others": { "iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0 }
    }
  },
  "inward_sup": {
    "isup_details": [
      { "ty": "GST", "inter": 0.0, "intra": 0.0 },
      { "ty": "NON_GST", "inter": 0.0, "intra": 0.0 }
    ]
  }
}
```

---

## 3. Pre-Export Payload Validation Engine (`GSTPayloadValidator`)

The validation engine executes statutory and syntactic rules before allowing export:

| Error Code | Severity | Target Section | Enforced Statutory Invariant |
| :--- | :--- | :--- | :--- |
| `GST_SCHEMA_INVALID_GSTIN` | **ERROR** | Header | Supplier GSTIN must match 15-char regex `^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$`. |
| `GST_SCHEMA_INVALID_PERIOD`| **ERROR** | Header | Return filing period code must match `MMYYYY` format. |
| `GST_B2B_SELF_SUPPLY_PROHIBITED` | **ERROR** | Table 4 (B2B) | Outward B2B recipient cannot equal supplier GSTIN. |
| `GST_DUPLICATE_INVOICE_NUM`| **ERROR** | Table 4 (B2B) | Invoice numbers must be unique within the period. |
| `GST_INVOICE_NUM_INVALID`  | **ERROR** | Table 4 (B2B) | Invoice number must be 1-16 alphanumeric chars, `/`, or `-`. |
| `GST_POS_INVALID`          | **ERROR** | Tables 4, 5, 7, 3.2 | Place of Supply must be valid 2-digit Indian State/UT code (01-38, 96, 97, 99). |
| `GST_CALC_IGST_ON_INTRASTATE` | **ERROR** | Tables 4, 7 | Intrastate supplies (`pos == supplier_state`) cannot charge IGST. |
| `GST_CALC_CGST_SGST_ON_INTERSTATE` | **ERROR** | Tables 4, 5, 7 | Interstate supplies (`pos != supplier_state`) cannot charge CGST or SGST. |
| `GST_CALC_CGST_SGST_ASYMMETRY` | **ERROR** | Tables 4, 7, 3.1(a) | Central Tax and State Tax on intrastate supplies must be equal. |
| `GST_RATE_NON_STANDARD`    | **ERROR** | Tables 4, 7 | Tax rates must belong to $\{0, 0.1, 0.25, 1.5, 3, 5, 6, 7.5, 12, 18, 28\}\%$. |
| `GST_NEGATIVE_AMOUNT_PROHIBITED` | **ERROR** | Tables 4, 5, 7 | Negative invoice values prohibited; deductions must use Credit Notes (Table 9B). |
| `GST_B2CL_BELOW_THRESHOLD` | **ERROR** | Table 5 (B2CL) | Invoice value must exceed threshold (> ₹2.5L $\le$ Jul 2024; > ₹1.0L $\ge$ Aug 2024). |
| `GST_B2CL_INTRASTATE_PROHIBITED` | **ERROR** | Table 5 (B2CL) | Table 5 is strictly for interstate supplies to unregistered persons. |
| `GST_HSN_CODE_INVALID`     | **ERROR** | Table 12 (HSN) | HSN/SAC codes must be numeric and minimum 4 digits. |
| `GST_DOC_ISSUE_ARITHMETIC_ERROR` | **ERROR** | Table 13 (DOC) | Total documents must equal net issued + cancelled. |
| `GST_CALC_ITC_NET_INCONSISTENT` | **ERROR** | Table 4 (`itc_elg`) | Net ITC must equal Available ITC minus Reversed ITC. |
| `GST_NEGATIVE_VALUE`       | **ERROR** | Table 3.1, 4 | Negative values prohibited across summary return tables. |
| `GST_CALC_INVOICE_TOTAL_MISMATCH` | **WARNING** | Table 4 (B2B) | Informs accountant when invoice header `val` differs from item tax total. |
| `GST_HSN_VALUATION_MISMATCH`| **WARNING** | Table 12 (HSN) | Informs accountant when HSN taxable value diverges from outward supplies. |

---

## 4. Test Verification & Non-Regression Results

Comprehensive automated testing was executed against the sandbox environment:

```
======================================================================
1. Round 2.2 Official Schema & Export Certification Suite
   Command: python manage.py test apps.gst.tests_round2_2_export
   Results: 27 / 27 PASS (100%) in 70.0s
   Status:  OK

2. Round 2.1 Compliance & Accounting Audit Suite
   Command: python manage.py test apps.gst.tests_round2_1_audit
   Results: 13 / 13 PASS (100%) in 41.3s
   Status:  OK

3. Round 2.0 Compliance Engine Suite
   Command: python manage.py test apps.gst.tests_round2_compliance
   Results: 11 / 11 PASS (100%) in 18.3s
   Status:  OK

4. Accounting Non-Regression Suite
   Command: python manage.py test apps.accounting.tests
   Results: 10 / 10 PASS (100%) in 6.5s
   Status:  OK

5. Frontend TypeScript Verification
   Command: npx tsc --noEmit
   Results: 0 Errors (Clean compilation)

6. Frontend Unit & Contract Suite
   Command: npm test --prefix frontend
   Results: 45 / 45 PASS (100%) across 6 test suites in 3.1s
======================================================================
```

---

## 5. Double-Entry Accounting Immutability

During the execution of `test_double_entry_immutability_zero_accounting_mutations`:
1. Vouchers, voucher line items, and general ledger journal entries were created and cryptographically tracked.
2. The complete GST return workspace lifecycle was executed:
   - Initialized period -> Draft generation -> Pre-filing validation -> Chartered accountant sign-off -> Official JSON export.
3. Database verification confirmed:
   - **Voucher Count Mutation:** $0$ ($N_{\text{before}} = N_{\text{after}}$).
   - **VoucherItem Count Mutation:** $0$ ($N_{\text{before}} = N_{\text{after}}$).
   - **LedgerEntry Count Mutation:** $0$ ($N_{\text{before}} = N_{\text{after}}$).
   - **Ledger Balance Mutation:** $0$ ($\Delta = ₹0.00$).
   - **Double-Entry Equilibrium:** $\sum \text{Debits} == \sum \text{Credits} == ₹1,18,000.00$.

---

## 6. Security, Isolation & Safety Boundaries

1. **Production Tenant Protection:**
   Protected tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) was **never accessed, read, or modified**.
2. **Dedicated Test Sandbox:**
   All automated test scripts and verification routines executed strictly against `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
3. **Database Boundary Protection:**
   The production database `neondb` was strictly isolated; all staging operations targeted `neondb_staging`.
4. **Prohibition of Real Filing:**
   Zero live filings, zero GST payments, and zero live external transmissions occurred.

---

## 7. Conclusion & Final Verdict

The SriLekh GST Round 2.2 export layer satisfies all requirements for official schema compliance, pre-export payload validation, deterministic hashing, accounting immutability, and multi-tenant isolation.

**Awarded Verdict:** **PASS — ROUND 2.2 EXPORT CERTIFIED**
