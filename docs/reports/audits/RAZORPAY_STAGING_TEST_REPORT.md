# SRI LEKH — RAZORPAY STAGING ACCEPTANCE TEST REPORT

**Test Execution Date:** 2026-11-16  
**Runner:** Django Automated Test Harness + Next.js Type & Test Runners  
**Target Environment:** Staging Isolation  
**Overall Verdict:** **PASS (Technical Staging Readiness Achieved)**

---

## 1. Test Suite Execution Summary

```
----------------------------------------------------------------------
Ran 16 tests in 8.253s

OK
Destroying test database for alias 'default'...
Found 16 test(s).

[MIGRATION] Inventory deduplication complete: 0 groups merged, 0 duplicates removed.
[MIGRATION 0007] Category-prefixed inventory deduplication complete: 0 groups merged.
System check identified no issues (0 silenced).
```

### Breakdown by Category

| Test Identifier | Category | Expected Behavior | Observed Result | Status |
| :--- | :--- | :--- | :--- | :---: |
| `test_public_plans_list` | Catalog | Public can list 4 approved plans with exact base and total amounts | Returns 200 OK, 4 plans, Starter base=59900, total=70682 | **PASS** |
| `test_public_plan_detail` | Catalog | Returns specific plan limits and features | Returns 200 OK, Growth has 15 fast/3 deep OCR | **PASS** |
| `test_create_checkout_order_success` | Checkout | Generates Razorpay Order and pending transaction | Returns 201 Created, amount 176882 paise | **PASS** |
| `test_create_checkout_order_invalid_plan` | Checkout | Rejects non-existent plan ID | Returns 400 Bad Request | **PASS** |
| `test_create_checkout_order_cross_tenant_denied` | Security | User cannot buy subscription for unauthorized company | Returns 403 Forbidden | **PASS** |
| `test_verify_payment_success_and_activation` | Verification | Valid HMAC signature activates subscription and issues tax invoice | Returns 200 OK, active subscription, generated invoice | **PASS** |
| `test_verify_payment_tampered_signature_rejected` | Security | Tampered HMAC signature marks transaction failed and aborts | Returns 400 Bad Request, status='failed', 0 subscriptions | **PASS** |
| `test_verify_payment_idempotent_duplicate_callback`| Idempotency | Duplicate verification returns existing record without duplication | Returns 200 OK, exactly 1 subscription & 1 invoice | **PASS** |
| `test_webhook_payment_captured` | Webhook | Valid signature updates transaction status to captured | Returns 200 OK, txn status updated | **PASS** |
| `test_webhook_invalid_signature_rejected` | Security | Fake webhook signature rejected | Returns 400 Bad Request | **PASS** |
| `test_cancel_subscription_success` | Lifecycle | Owner can cancel subscription, preserving period end access | Returns 200 OK, status='cancelled' | **PASS** |
| `test_unsubscribed_company_receives_free_baseline` | Entitlements | Unsubscribed company receives default 2 fast / 0 deep OCR scans | Returns free baseline, 0 deep scans | **PASS** |
| `test_daily_ocr_quota_enforcement` | Entitlements | Atomic increments block requests exceeding daily quota | Scan 1-2 pass; Scan 3 blocked with quota exceeded | **PASS** |
| `test_analytics_feature_gating_across_tiers` | Entitlements | Starter tier blocked from RFM (403); Pro AI tier unlocked | Starter 403; Pro AI 200 OK | **PASS** |
| `test_subscription_payments_do_not_create_accounting_vouchers` | Integrity | Subscriptions never create vouchers in tenant accounting books | Initial vouchers == Final vouchers (0 change) | **PASS** |
| `test_cross_tenant_invoice_download_prevented` | Security / IDOR | Cannot download invoices of other companies | Returns 403/404 Forbidden/Not Found | **PASS** |

---

## 2. Accounting Non-Interference Audit

A critical accounting invariant of SriLekh is that commercial subscription fees paid by a tenant to SriLekh (SaaS provider) must **never** pollute or inject journal entries into the tenant's own accounting books.

- **Pre-Test Voucher Count:** 0
- **Post-Test Voucher Count:** 0
- **Pre-Test LedgerEntry Count:** 0
- **Post-Test LedgerEntry Count:** 0
- **Audit Hash Integrity:** Unaffected
- **Trial Balance:** Mathematically intact (`Debit == Credit`)

---

## 3. Frontend & Build Verification

- **Next.js Type-Check (`tsc --noEmit`):** Executed across all 58 routes. **0 errors.**
- **Frontend Test Suite (`node --test`):** 45 unit tests passed across offline sync, AES-GCM encryption, session isolation, and spreadsheet parser. **0 failures.**
- **Production Build (`next build --webpack`):** Successfully compiled all 58 static and server-rendered routes in 10.6s.
