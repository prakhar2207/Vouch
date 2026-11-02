# SriLekh — Defect Register
**Master Defect Tracking & Resolution Ledger**  
*Document Ref:* `docs/trust-flexibility/DEFECT_REGISTER.md`  
*Branch:* `feature/trust-flexibility-remediation`  

---

## Defect Inventory

| Defect ID | Module | Severity | Summary | Root Cause | Resolution | Status |
|---|---|:---:|---|---|---|:---:|
| **DEF-01** | Banking | `P1` | 1D line grouping scrambled passbook columns, lost payee `SATYAM AND CO`, and inverted debit/credit | Simple vertical line clustering failed on dense multi-column bank passbook tables | 2D spatial coordinate bounding (`xDep`, `xWdl`, `xBal`) and delimiter grouping by `Chq:` markers in `clientStatementParser.ts` | **RESOLVED** |
| **DEF-02** | Banking | `P1` | Statement exclusion modal returned `HTTP 404 Not Found` | Lacked explicit backend route handler for statement exclusion | Added `BankStatementImportDetailAPIView.post` and restore view in `apps/accounting/banking_views.py` | **RESOLVED** |
| **DEF-03** | Accounting | `P1` | Voucher edit modal returned `HTTP 428 Precondition Required` | Backend required OCC version but serializer omitted `version` from frontend responses | Exposed `version` and `ETag`, maintained version state in edit modals, transmitted `payload.version` | **RESOLVED** |
| **DEF-04** | API / CORS | `P1` | PATCH requests blocked with CORS error on `If-Match` header | Django `CORS_ALLOW_HEADERS` did not whitelist `if-match` | Added `if-match`, `if-none-match`, `x-voucher-version` to `CORS_ALLOW_HEADERS`; passed version in JSON body | **RESOLVED** |
| **DEF-05** | Frontend / PWA | `P2` | Mobile PWA build failed and desktop onboarding tour caused mobile crash loops | Cache query strings in manifest icons broke APK packaging; unshielded `localStorage` in tour | Sanitized manifest icons; desktop-guarded `OnboardingTour`; upgraded `error.tsx` with self-healing reload | **RESOLVED** |
| **DEF-06** | Security | `P0` | Risk of automated test scripts polluting real tenant accounts | Absence of mandatory assertion barrier across test runners | Enforced strict test isolation invariant targeting sandbox `Apex Belting Store` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`) | **VERIFIED** |

---

## Detailed Defect Resolution Audit

### DEF-01: Spatial Statement Parsing
- **Test File:** `C:\Users\prakh\Downloads\canara_epassbook_2026-11-01 133109.707715.pdf`
- **Before:**
  - Row 49: ₹11,161.00 tagged as credit `+11,161.00`.
  - Description: `11,161.00 -9,44,379.18 32924784679 PAYMENT Chq: 0 page 6 Date Particulars Deposits Withdrawals Balance SC NEFT OTHER THAN SB IMB`.
  - Payee `SATYAM AND CO` lost.
- **After:**
  - Row 49: Debit ₹11,161.00 (withdrawal), credit ₹0.00.
  - Description: `MB NEFT DR CNRBH00171484971 SATYAM AND CO SBIN0001080 32924784679 PAYMENT Chq: 0`.
  - Reference: `CNRBH00171484971`.
  - Reconciled with party ledger `Satyam & Co` as Supplier Payment.

### DEF-02: Audited Statement Exclusion
- **Endpoint:** `POST /api/v1/accounting/banking/statements/<id>/exclude/`
- **Test Suite:** `apps.accounting.tests_banking_production.BankingProductionIntegrationTests.test_statement_and_transaction_audited_exclusion`
- **Result:** Statement marked `is_excluded=True`, child transactions marked `is_excluded=True`, reversing vouchers generated where applicable, audit log recorded. HTTP 200 OK.

### DEF-03 & DEF-04: Concurrency & CORS Preflight
- **Endpoints:** `PATCH /api/v1/vouchers/<id>/`, `PATCH /api/v1/accounting/vouchers/<id>/`
- **Headers:** `CORS_ALLOW_HEADERS = [..., 'if-match', 'if-none-match', 'x-voucher-version']`
- **Payload Contract:** `{ ..., "version": 1 }`
- **Result:** Preflight succeeds with 200 OK. Voucher updates execute atomically with optimistic locking.

### DEF-05: PWA Manifest & Touch Screen Stability
- **Manifest URLs:** Clean paths without `?v=...` query strings.
- **Screen Guard:** `if (window.innerWidth < 768) return null;`
- **Build Status:** 47/47 Next.js routes compiled cleanly.

---
*Maintained by SriLekh Quality Assurance & Core Reliability Engineering.*
