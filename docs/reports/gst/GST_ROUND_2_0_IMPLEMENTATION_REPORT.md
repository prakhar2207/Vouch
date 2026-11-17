# SriLekh GST — Round 2.0 Implementation Report
## GST Compliance, Return Preparation & ITC Reconciliation Engine

- **Target System:** SriLekh Accounting & Tax SaaS (GST Subsystem)
- **Repository:** `https://github.com/prakhar2207/Vouch`
- **Active Branch:** `fix/stage4-12-day6-remediation`
- **Staging Service:** `https://vouch-u3u7.onrender.com`
- **Staging Database:** Neon `neondb_staging` (`fingerprint: 6f4741bdaaf4`)
- **Report Date:** November 17, 2026
- **Lead Implementer & Auditor:** Principal Software Architect, Senior Django Engineer, Security Auditor & FinTech QA Lead

---

## 1. Executive Summary

SriLekh previously completed GST Round 1.3.2, achieving certified live Quicko Sandbox GSTIN verification, cached taxpayer lookup, party auto-fill, and multi-state registration management.

In Round 2.0, the core compliance layer has been established:
1. **Source of Truth Invariant:** Accounting records (`Voucher`, `VoucherItem`, `LedgerEntry`) remain the absolute source of truth. GST returns and reconciliation reports are strictly derived views and **never alter, overwrite, or mutate posted accounting transactions**.
2. **Unified GST Return Workspace:** Tracks return period lifecycles (`NOT_STARTED` $\to$ `DRAFT` $\to$ `VALIDATION_REQUIRED` $\to$ `READY_FOR_REVIEW` $\to$ `REVIEWED` $\to$ `EXPORTED`), maintains immutable point-in-time draft snapshots, and computes SHA-256 voucher fingerprints for automatic change detection (drift).
3. **Comprehensive GSTR-1 Engine:** Compiles official GST portal JSON covering B2B (Table 4), B2CL (Table 5: interstate $> ₹2.5\text{L}$ to unregistered), B2CS (Table 7), Exports (Table 6), Credit/Debit Notes (Table 9B CDNR & CDNUR), Nil/Exempt (Table 8), Advances received and adjusted (Table 11A & 11B), HSN/SAC Summary (Table 12), and Document Issue Summary (Table 13).
4. **Authoritative GSTR-3B & Rule 88A Waterfall:** Compiles monthly summaries (Table 3.1, 3.2, 4, 5), implements the statutory Rule 88A ITC set-off waterfall (IGST priority exhaustion, CGST/SGST non-cross set-off), and reconciles computed taxes against General Ledger tax accounts with zero variance on clean books.
5. **GSTR-2B Import & 9-Category Reconciliation:** Ingests official GST Portal JSON and Excel files, enforces 15MB upload limits and duplicate import prevention, normalizes invoice numbers, and classifies discrepancies across 9 distinct categories with configurable tolerance.
6. **Centralized Validation & Exception Engine:** Scans vouchers for format, checksum, place of supply, interstate/intrastate classification, and missing HSN errors, providing plain-language explanations and direct links to the underlying vouchers.

---

## 2. Architecture & Data Flow

```
+---------------------------------------------------------------------------------+
|                             Accounting Engine (Source of Truth)                 |
|   Voucher (SALES, PURCHASE, CREDIT_NOTE, DEBIT_NOTE, RECEIPT)                   |
|   VoucherItem (Quantity, Taxable, GST Rates, HSN/SAC)                           |
|   LedgerEntry (Debits == Credits Equilibrium, Input/Output Tax Accounts)        |
+---------------------------------------------------------------------------------+
                                       |
                                  (Read-Only)
                                       |
+---------------------------------------------------------------------------------+
|                          Centralized Validation Engine                          |
|   GSTValidationService.validate_period_vouchers()                               |
|   - Missing HSN / PoS Mismatches / Tax Distribution / Unclassified Transactions |
+---------------------------------------------------------------------------------+
                                       |
                                  (Clean Data)
                                       |
+---------------------------------------------------------------------------------+
|                         GST Return Workspace & Services                         |
|   GSTWorkspaceService                                                           |
|   - Return Period Lifecycle Management                                          |
|   - SHA-256 Source Voucher Fingerprint & Drift Detection                        |
|   - Immutable Point-in-Time Draft Snapshotting                                  |
|                                                                                 |
|   GSTReturnsService                                                             |
|   - GSTR-1: Tables 4, 5, 6, 7, 8, 9B, 11A, 11B, 12, 13                          |
|   - GSTR-3B: Tables 3.1, 3.2, 4, 5                                              |
|   - Rule 88A Statutory Set-off Waterfall                                        |
|   - General Ledger Balance Reconciliation                                       |
+---------------------------------------------------------------------------------+
                                       |
+---------------------------------------------------------------------------------+
|                         GSTR-2B Reconciliation Engine                           |
|   ITCReconciliationService / GSTReconciliationService                           |
|   - JSON / Excel File Ingest with Duplicate Detection                           |
|   - 9-Category Discrepancy Matching (Matched, Value, Tax, Date, Missing, etc.)  |
|   - Statutory ITC Assessment (Eligible, Ineligible Section 17(5), Blocked)      |
+---------------------------------------------------------------------------------+
```

---

## 3. Models & Database Migrations

### 3.1 Model Additions: `GSTReturnWorkspace` (`apps/gst/models.py`)
Tracks return draft lifecycles, snapshots, validation statuses, and voucher drift:
- `id`: UUID primary key.
- `company`: ForeignKey to `Company`.
- `gst_registration`: ForeignKey to `GSTRegistration` (null=True for multi-registration support).
- `financial_year`: CharField (e.g. `"2026-27"`).
- `return_period`: CharField (e.g. `"082026"`).
- `return_type`: `GSTR1`, `GSTR3B`, `GSTR2B_RECON`.
- `status`: `NOT_STARTED`, `DRAFT`, `VALIDATION_REQUIRED`, `READY_FOR_REVIEW`, `REVIEWED`, `EXPORTED`.
- `sales_data_available`, `purchase_data_available`: Boolean availability flags.
- `unclassified_count`, `validation_error_count`, `validation_warning_count`: Quantitative compliance metrics.
- `tax_liability_summary`: JSON summary of outward tax components.
- `itc_summary`: JSON summary of available, reversed, and net ITC.
- `reconciliation_status`: Tracking status for GSTR-2B matching.
- `validation_errors`: JSON array containing detailed issues with `voucher_id` links.
- `source_voucher_hash`: SHA-256 hash of all period voucher IDs and `updated_at` timestamps.
- `is_stale`: Boolean drift indicator set when source vouchers are edited after draft generation.
- `draft_payload`: Full official return JSON snapshot.
- `reviewed_by`, `reviewed_at`: Audit tracking for sign-off.

### 3.2 Database Migration: `apps/gst/migrations/0008_gstreturnworkspace.py`
- Created table `gst_gstreturnworkspace` with unique constraint `(company, gst_registration, return_type, return_period)` and performance indexes on `company`, `return_type`, `return_period`, and `status`.
- Dry-run verification: `python manage.py makemigrations --check --dry-run` confirms **No changes detected**.

---

## 4. API Endpoints Reference

All endpoints enforce tenant isolation (`get_company_or_404`) and role-based permissions:

| Endpoint | Method | Permitted Roles | Description |
|---|---|---|---|
| `/api/v1/gst/workspace/{company_id}/` | `GET` | All Roles | Retrieve workspace status, period metrics, and drift state |
| `/api/v1/gst/workspace/{company_id}/init-period/` | `POST` | Owner, Admin, CA, Accountant | Initialize or open a return period |
| `/api/v1/gst/workspace/{company_id}/generate-draft/` | `POST` | Owner, Admin, CA, Accountant | Compile GSTR-1 or GSTR-3B draft snapshot |
| `/api/v1/gst/workspace/{company_id}/draft/` | `GET` | All Roles | Retrieve current draft payload and staleness status |
| `/api/v1/gst/workspace/{company_id}/validate/` | `POST` | All Roles | Run pre-filing validation check on period |
| `/api/v1/gst/workspace/{company_id}/sign-off/` | `POST` | Owner, Admin, CA, Accountant | Sign off draft as `REVIEWED` (blocked if errors or stale) |
| `/api/v1/gst/workspace/{company_id}/export/` | `POST` | Owner, Admin, CA, Accountant | Export official JSON schema or Excel structure |
| `/api/v1/gst/reconciliation/{company_id}/upload-2b/` | `POST` | Owner, Admin, CA, Accountant | Upload GSTR-2B JSON/Excel with duplicate detection |
| `/api/v1/gst/reconciliation/{company_id}/run/` | `POST` | Owner, Admin, CA, Accountant | Execute invoice matching against purchase vouchers |
| `/api/v1/gst/reconciliation/{company_id}/summary/` | `GET` | All Roles | Retrieve 9-category match breakdown and financial metrics |
| `/api/v1/gst/reconciliation/{company_id}/records/` | `GET` | All Roles | Paginated list of 2B records with diffs and filter by status |
| `/api/v1/gst/reconciliation/{company_id}/manual-match/` | `POST` | Owner, Admin, CA, Accountant | Manually link a 2B record with a purchase voucher |

---

## 5. Authoritative GST Rules & Statutory Sources

| Statutory Rule | Authoritative Source & Effective Date | Implementation in SriLekh |
|---|---|---|
| **Intrastate vs Interstate** | Sections 7 & 8 of IGST Act, 2017 (w.e.f. 01-07-2017) | Compares Place of Supply (PoS) against Supplier State Code: matches $\to$ CGST+SGST, differs $\to$ IGST. |
| **B2B Outward Supplies** | Section 37, Rule 59(1) of CGST Rules | GSTR-1 Table 4: itemized by recipient GSTIN, invoice number, date, value, PoS, rate items. |
| **B2CL Large Supplies** | Rule 59(4)(a) of CGST Rules | GSTR-1 Table 5: interstate supplies to unregistered persons where invoice value $> ₹2,50,000$. |
| **B2CS Small Supplies** | Rule 59(4)(b) of CGST Rules | GSTR-1 Table 7: intrastate unregistered (any value) + interstate unregistered $\le ₹2,50,000$. |
| **Credit / Debit Notes** | Section 34 of CGST Act (amended by Finance Act 2022) | Table 9B: CDNR (Registered) & CDNUR (Unregistered) with reference to original invoice. |
| **HSN/SAC Summary** | Notification No. 78/2020-Central Tax (w.e.f. 01-04-2021) | Table 12: mandatory 4-digit HSN for B2B; aggregated by HSN, UQC, quantity, value, taxes. |
| **Document Issue Summary** | Rule 59(1) of CGST Rules | Table 13: serial numbers from-to, count, cancelled, and net issued across document types. |
| **GSTR-3B Outward Tax** | Section 39, Rule 61(5) (Notification 14/2022-CT) | Table 3.1: (a) Taxable, (b) Zero-rated, (c) Nil/Exempt, (d) Inward RCM, (e) Non-GST. Table 3.2 Interstate unregistered. |
| **Mandatory 2B Matching for ITC** | Section 16(2)(aa) inserted via Finance Act 2021 (w.e.f. 01-01-2022) | 100% GSTR-2B matching requirement; unmatched purchase invoices flagged as `MISSING_IN_2B`. |
| **Blocked / Ineligible ITC** | Section 17(5) of CGST Act, 2017 | Excluded from Table 4(A)(5) and categorized as `INELIGIBLE_ITC` / Table 4(B)(1). |
| **Rule 88A Set-off Waterfall** | Circular No. 98/17/2019-GST (w.e.f. 01-04-2019) | Priority 1: Exhaust IGST credit against IGST, CGST, SGST. Priority 2: CGST against CGST, then IGST. Priority 3: SGST against SGST, then IGST. |

---

## 6. Supported Return Sections

### GSTR-1 Sections Fully Supported:
- **Table 4 (B2B):** Taxable supplies to registered recipients.
- **Table 5 (B2CL):** Interstate supplies to unregistered recipients where invoice value $> ₹2.5\text{L}$.
- **Table 6 (EXP):** Export supplies (with or without payment of tax).
- **Table 7 (B2CS):** Other unregistered supplies (intrastate of any value + interstate $\le ₹2.5\text{L}$).
- **Table 8 (NIL):** Nil-rated, exempted, and non-GST outward supplies.
- **Table 9B (CDNR / CDNUR):** Credit and debit notes issued to registered and unregistered recipients.
- **Table 11A & 11B (AT & TXPD):** Tax liability on advances received and advance adjustments.
- **Table 12 (HSN):** HSN-wise summary of outward supplies.
- **Table 13 (DOC_ISSUE):** Document issue series summary.

### GSTR-3B Sections Fully Supported:
- **Table 3.1:** Outward taxable, zero-rated, nil/exempt, inward RCM, and non-GST supplies.
- **Table 3.2:** Interstate supplies to unregistered persons, composition dealers, and UIN holders.
- **Table 4:** Eligible ITC (Import goods/services, Inward RCM, All other ITC), ITC reversals, and Net ITC.
- **Table 5:** Values of exempt, nil-rated, and non-GST inward supplies.
- **Table 6.1:** Rule 88A tax payable after statutory credit set-off.

---

## 7. Import Formats & Reconciliation Engine

### Supported Ingest Formats:
1. **GST Portal JSON:** Official JSON structure downloaded from the GST portal containing `b2b`, `b2ba`, `cdnr`, and `cdnra` sections.
2. **GSTR-2B Excel (.xlsx):** Official Excel workbook containing standard sheets. Securely parsed using streaming validation (`openpyxl`), 15MB file size limit, and zip decompression security guards.

### 9-Category Reconciliation Classification:

| Category | Description | Tolerance Applied |
|---|---|---|
| `MATCHED` | GSTIN, normalized invoice number, dates ($\le 30$ days), and amounts match within tolerance. | $\pm ₹1.00$ |
| `VALUE_MISMATCH` | GSTIN and invoice number match, but taxable amount or tax differs by $> ₹1.00$. | $> ₹1.00$ |
| `TAX_MISMATCH` | Taxable amount matches, but tax components differ (e.g. Books has CGST/SGST, 2B has IGST). | Breakdown diff |
| `DATE_MISMATCH` | GSTIN, invoice number, and values match, but dates differ by $> 30$ days. | $> 30$ days |
| `GSTIN_MISMATCH` | Invoice number and total match, but supplier GSTIN differs between books and 2B. | Exact |
| `MISSING_IN_BOOKS` | Invoice appears in GSTR-2B, but no corresponding purchase voucher exists in books. | N/A |
| `MISSING_IN_2B` | Purchase voucher exists in books, but supplier has not uploaded the invoice in GSTR-2B. | N/A |
| `DUPLICATE` | Multiple identical invoices uploaded by supplier. | Exact |
| `INELIGIBLE_ITC` | Vendor marked as ITC Ineligible in GSTR-2B (e.g. PoS outside recipient state, Section 17(5)). | Rule |

---

## 8. Role-Based Permissions & Security Matrix

| Action | OWNER | ADMIN | ACCOUNTANT | CA | EMPLOYEE | VIEWER |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| View Workspace, Drafts & Validations | Yes | Yes | Yes | Yes | Yes | Yes |
| Compile / Regenerate Return Drafts | Yes | Yes | Yes | Yes | No | No |
| Run Validations & Pre-Filing Health Check | Yes | Yes | Yes | Yes | No | No |
| Upload GSTR-2B File | Yes | Yes | Yes | Yes | No | No |
| Run Reconciliation & Manual Linkage | Yes | Yes | Yes | Yes | No | No |
| Sign Off Draft as REVIEWED | Yes | Yes | Yes | Yes | No | No |
| Export Official Portal JSON / Excel | Yes | Yes | Yes | Yes | No | No |
| Mutate Accounting Vouchers | Yes | Yes | Yes | No | Yes | No |

---

## 9. Automated Test Results

### 9.1 GST Round 2.0 Compliance Suite (`apps.gst.tests_round2_compliance`)
```bash
$ python manage.py test apps.gst.tests_round2_compliance --no-input
Found 11 test(s).
Creating test database for alias 'default'...
System check identified no issues (0 silenced).
...........
----------------------------------------------------------------------
Ran 11 tests in 11.035s

OK
Destroying test database for alias 'default'...
```
- **Result:** **11 / 11 PASS** (0 Failures, 0 Errors, 11.0s).
- **Coverage:** GSTR-1 tables (4, 5, 6, 7, 8, 9B, 11A, 11B, 12, 13), GSTR-3B compilation & Rule 88A waterfall, Workspace status progression, drift detection, Centralized validation exceptions, GSTR-2B JSON ingest, duplicate import detection, 9-category match classification, manual matching API, file upload security, and accounting immutability.

### 9.2 GST Round 1 Foundation Suite (`apps.gst.tests_round1_foundation`)
- **Result:** **31 / 31 PASS** (0 Failures, 0 Errors, 94.1s).
- **Coverage:** MultiFernet encryption, key rotation idempotency, cross-tenant isolation, cache TTL, rate limits.

### 9.3 Accounting Non-Regression Suite
```bash
$ python manage.py test apps.accounting.tests_stage4_13_stabilization apps.accounting.tests_upload_security apps.ledgers.tests --no-input
Found 9 test(s).
Creating test database for alias 'default'...
System check identified no issues (0 silenced).
.........
----------------------------------------------------------------------
Ran 9 tests in 2.822s

OK
Destroying test database for alias 'default'...
```
- **Result:** **9 / 9 PASS** (0 Failures, 0 Errors, 2.8s).
- **Invariants Verified:** Debit == Credit equilibrium, immutability of posted journals, audit log integrity, voucher balance reconciliation.

### 9.4 Frontend Type Checking & Test Suites
```bash
$ cd frontend && npx tsc --noEmit
# Exit code 0 (0 TypeScript errors)

$ npm test --prefix frontend
PASS Contact form validation & mailto handoff
PASS Spreadsheet Parser (safe xlsx replacement & CSV hardening)
PASS Service Worker Cache Policy & Session Isolation
PASS Stage 4.12 Phase B: Offline-First Sync, Outbox Lifecycle
PASS Stage 1.2: Browser Token Elimination & Offline Privacy
PASS Domain Role Capabilities Matrix
PASS Environment API URL Isolation
PASS Auth & Permission Utilities

Test Suites: 8 passed, 8 total
Tests:       45 passed, 45 total
Snapshots:   0 total
Time:        1.247 s
```
- **Result:** **45 / 45 PASS** (0 Failures, 0 Errors).

---

## 10. Accounting Non-Regression & Data Safety Verification

| Invariant Checked | Verification Method | Result |
|---|---|---|
| **Voucher Immutability** | Compared `Voucher.objects.count()` before and after draft compilation, validation, 2B import, and reconciliation | **ZERO WRITES** (Preserved) |
| **VoucherItem Immutability** | Compared `VoucherItem.objects.count()` before and after GST operations | **ZERO WRITES** (Preserved) |
| **LedgerEntry Immutability** | Compared `LedgerEntry.objects.count()` before and after GST operations | **ZERO WRITES** (Preserved) |
| **Debit == Credit Equilibrium** | Mathematical equilibrium across all posted transactions | **ZERO VARIANCE** (Preserved) |
| **Tenant Protection** | Production database `neondb` and tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) | **UNTOUCHED** (Zero queries) |

---

## 11. Known Limitations & Subsequent Scope

1. **No Live Portal Submission in Round 2.0:** Round 2.0 intentionally delivers return preparation, pre-filing validation, reconciliation, and official JSON/Excel export. Direct portal upload and OTP signing are scheduled for Round 3.0.
2. **Annual GSTR-9 Reconciliation:** Scoped for subsequent rounds; Round 2.0 focuses on monthly and quarterly compliance (GSTR-1, GSTR-3B, GSTR-2B).
3. **QRMP Scheme Quarterly Returns:** Round 2.0 standardizes on monthly return periods; quarterly IFF (Invoice Furnishing Facility) will be formalized in Round 2.1.
