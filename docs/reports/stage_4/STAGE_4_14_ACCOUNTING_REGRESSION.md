# SRI LEKH — STAGE 4.14 ACCOUNTING REGRESSION REPORT

**Environment:** Live Render Staging (`https://vouch-u3u7.onrender.com`), Staging DB (`neondb_staging`), and Test DB (`test_neondb_staging`)  
**Commit SHA:** `990a13bd` (Live Render) + [tests_stage4_14_certification.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/tests_stage4_14_certification.py)  
**Database Fingerprint:** `6f4741bdaaf4` (`is_isolated=True`, `Maa Annapurna Belting Store` absent)  
**Execution Timestamp:** `2026-11-12 13:50–14:04 IST`

---

## 1. Automated Regression Verification

- **Stage 4.14 + Stage 4.13 Targeted PG Run (`test_neondb_staging`):**
  `python manage.py test apps.accounting.tests_stage4_14_certification apps.accounting.tests_stage4_13_stabilization --settings=config.settings_test_pg --keepdb --verbosity=2`
  - **Result:** **`11 / 11 OK`** (`183.462s`, `0` failures, `0` errors, `0` skipped).
- **Schema Consistency Check:** `python manage.py makemigrations --check --dry-run` -> `No changes detected` (exit `0`).
- **Baseline Stage 4.13 Full Suite Reference (no application accounting code modified since `2945375`):** `77 / 77 OK` PG backend + `12 / 12 pass` frontend (`tsc --noEmit` exit `0`).

---

## 2. Live Render HTTPS Write Lifecycle & All-Reports Parity (`Stage 4.14 Live Audit Sandbox`)

- **Procedure:** Executed via `stage4_14_live_render_audit.py` against `https://vouch-u3u7.onrender.com` using dedicated isolated synthetic tenant `e09b235c-fffa-4410-a162-cb212fc4b3b6` (`auto_reconcile=False` checked; zero mutations to the 5 pilot tenants confirmed with `pilot_unchanged: true`).
- **Expected Outcome:** Complete `DRAFT -> POST -> OCC Edit -> Stale OCC 409 -> Payment Receipt Duplicate 409 -> Canonical Reversal` reflected consistently across Trial Balance, Balance Sheet, P&L, Period TB, Period Statement, Ledger Statement, Receivables Aging, and Payables Aging with zero discrepancies.
- **Actual Outcome & Status (`PASS`):**
  - `POST /api/v1/accounting/sales-invoice/` (`post_immediately=False`): `HTTP 201`, status `DRAFT`
  - `GET /api/v1/accounting/vouchers/detail/<id>/`: `HTTP 200`, `DRAFT`
  - `PATCH /api/v1/accounting/vouchers/detail/<id>/` (`If-Match: "1"`, `post_immediately=True`): `HTTP 200`, status `POSTED`
  - `PATCH` posted voucher (`If-Match: "2"`): `HTTP 200` (`occ_edit_status: 200`)
  - Stale `PATCH` (`If-Match: "1"`): `HTTP 409 Conflict`
  - `POST /api/v1/accounting/payment-receipt/` (initial `500.00` `201`; repeat `409`; `EMPLOYEE` `allow_duplicate=True` `403`)
  - Canonical reversal (`REV-INV/26-27/0002`): Live `GET` confirms original `status: "REVERSED"` and reversal `status: "POSTED"`
  - **Live Reports Post-Reversal:**
    - Trial Balance (`200`): `is_balanced: true`, `total_debit: 500.0 == total_credit: 500.0`, **`discrepancies_detected: 0`**
    - Balance Sheet (`200`): `is_balanced: true`, `difference: "0.00"`
    - Profit & Loss (`200`): `net_profit: "0.00"`
    - Period Trial Balance (`200`): `is_closing_balanced: true`
    - Period Statement (`200`): `closing_balance: "500.00 CR"`
    - Ledger Statement (`200`): `closing_balance: "500.00"`
    - Receivables Aging (`200`): `total_outstanding: 0.0` | Payables Aging (`200`): `total_outstanding: 0.0`

---

## 3. Global & 5-Tenant Pilot Cohort Accounting Invariants (`neondb_staging`, `auto_reconcile=False`)

- **Command:** `stage4_14_pilot_soak_check.py` (read-only audit on `neondb_staging`)
- **Result (`PASS`):**
  - `zero_entry_posted`: **`0`**
  - `unbalanced_posted`: **`0`**
  - `orphan_entries`: **`0`**
  - `negative_or_zero_allocations`: **`0`**
  - **All 5 Canonical Pilot Tenants (`Garodia`, `Precision Agro`, `Shree Radhe`, `Beta Engineering`, `Alpha Belts`):**
    - Trial Balance balanced: **`5 / 5`**
    - `Trial Balance == Period Trial Balance`: **`5 / 5`** (`tb_eq_ptb: true`)
    - Balance Sheet balanced: **`5 / 5`** (`bs_balanced: true`)
    - Ledger cache discrepancies: **`0 / 113`** (`discrepancies: 0` across all 5 tenants)
    - CGST == SGST ledger cache symmetry: **`5 / 5`** (`20551.74`, `100802.67`, `19772.54`, `19808.86`, `15543.76`)

---

## Remaining Limitations

- Live reversal trigger was executed via `VoucherService.create_reversal_voucher` (verifying both original `REVERSED` and `REV-*` `POSTED` documents plus all 8 live report endpoints over HTTPS on Render) rather than a standalone `/reverse/` UI endpoint for invoices.
