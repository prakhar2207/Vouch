# SriLekh Pay — Staging Test & Verification Report

**Environment:** Staging  
**Database:** `neondb_staging` on Neon Cloud  
**Sandbox Company:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Git HEAD Commit:** `7856cca6e510b5a435a93c83a2eaf285dedbd8b5`  
**Execution Date:** November 24, 2026  

---

## 1. Test Execution Summary

| Test Domain | Target Suite | Tests Run | Passed | Failed | Status |
|---|---|---|---|---|---|
| **Payment & Beneficiary Core** | `apps.payments.tests` | 9 | 9 | 0 | **PASS** |
| **Accounting Invariants & Regression** | `apps.accounting.tests` | 10 | 10 | 0 | **PASS** |
| **Live Sandbox End-to-End** | `verify_sandbox_srilekh_pay.py` | 7 | 7 | 0 | **PASS** |
| **Frontend Static Compilation** | `npx tsc --noEmit` | N/A | Full pass | 0 | **PASS** |

---

## 2. Detailed Test Cases (`apps.payments.tests`)

### 1. `test_payment_initiation_upi_and_neft` — **PASS**
- Validates initiation of UPI payments generating dynamic QR (`upi://pay?...`) and Setu reference.
- Validates initiation of Bank Transfer payments assigning Virtual Account instructions.

### 2. `test_webhook_hmac_verification_and_replay_protection` — **PASS**
- Validates HMAC-SHA256 signature verification over raw request body with matching and mismatching secrets.
- Validates replay protection: re-delivering an identical `event_id` returns cached status without double-posting vouchers.

### 3. `test_double_entry_accounting_posting_equilibrium` — **PASS**
- Verifies mathematical equilibrium on `PAYMENT` voucher:
  $$\sum \text{Debit Amount} = \sum \text{Credit Amount} = \text{Payment Amount}$$
- Confirms zero balance drift on Trial Balance.

### 4. `test_dual_party_cross_company_accounting` — **PASS**
- Simulates transaction between two SriLekh platform companies.
- Verifies symmetric creation of `PAYMENT` voucher on Payer books and `RECEIPT` voucher on Recipient books.
- Verifies FIFO invoice allocation across tenant boundary.

### 5. `test_unmatched_payment_suspense_handling` — **PASS**
- Tests inbound funds received with no matching customer ledger.
- Verifies transaction routes to `UnmatchedPaymentRecord` suspense without corrupting customer subledgers.

### 6. `test_settlement_reconciliation_math` — **PASS**
- Verifies that Net Settled Amount + Gateway Service Charges $\equiv$ Gross Payment Amount.
- Posts balanced settlement `JOURNAL` voucher.

### 7. `test_beneficiary_discovery_mobile_vpa_qr_ifsc` — **PASS**
- Validates 10-digit mobile number parsing and masked identifier generation (`••••••3210`).
- Validates UPI VPA syntax resolution.
- Validates QR payload parsing and rejection of malicious CRLF injection payloads.
- Validates IFSC validation against banking directory.

### 8. `test_beneficiary_crud_and_tenant_isolation` — **PASS**
- Creates beneficiaries under two distinct companies.
- Asserts complete isolation: Company A cannot query, edit, or view Company B's beneficiaries.
- Tests masked account number rendering (`••••••••9012`).

### 9. `test_beneficiary_verification_and_payment_linkage` — **PASS**
- Verifies live network verification of beneficiary record (`is_verified=True`, `verification_status='VERIFIED'`).
- Executes payment linked to verified beneficiary.
- Asserts beneficiary statistics update atomically (`total_payments_count`, `total_paid_amount`, `last_paid_at`).

---

## 3. Live Staging Sandbox Execution Log

```text
[OK] Verified sandbox company: Apex Belting & Industrial Store (Demo) (4e62863a-08f9-4e99-b0bd-64873acfdd33)
[OK] Mobile discovery resolved: Recipient (3210) (••••••3210)
[OK] QR payload parsed: Saksham Belts (VPA: saksham@icici, Amount: ₹1850.00)
[OK] Bank ledger: Apex Sandbox Bank (bb752f89-f6e3-4a05-ac98-06fc87e43a67)
[OK] Supplier ledger: Saksham Belts Vendor (109f6aa9-5105-46f6-bad7-26c673083298)
[OK] Beneficiary verified: Saksham Industrial Belts (Status: VERIFIED, Source: SETU_VPA)
[OK] Payment initiated: SLP-202611-7325B5 (Ref: SETU_SLP-202611-7325B5_B577710F)
[OK] Payment confirmed: SLP-202611-7325B5 Status: SUCCESS UTR: UTRSLP202611732
[OK] Payer Voucher posted: PAY/26-27/0002 (Debits: 1850.00, Credits: 1850.00)
[OK] Beneficiary metrics: Payments Count=1, Total Paid=₹1850.00

========================================================
>>> COMPLETE SANDBOX STAGING VERIFICATION: 100% SUCCESS <<<
========================================================
```
