# SriLekh — Comprehensive Remediation Changelog
**Document Reference:** `docs/full-platform-audit/REMEDIATION_CHANGELOG.md`  
**Execution Timestamp:** 2026-11-02 16:30:00 IST  
**Audit Lead:** Antigravity Principal Systems Architect & Fintech Reliability Auditor  

---

## 1. Summary of Changes by Module

### 1. Banking & Reconciliation Module
- **`apps/accounting/models.py`**:
  - Added `raw_debit_amount`, `raw_credit_amount` (Decimal, max_digits=15, decimal_places=2, default=0.00).
  - Added `user_classification` (CharField, max_length=50).
  - Added `is_refund` (BooleanField, default=False).
  - Added `BankTransaction.save()` guard initializing raw amounts from debit/credit on creation.
- **`apps/accounting/services/bank_reconciliation_service.py`**:
  - Removed in-place reassignments of `debit_amount` and `credit_amount` (previously lines 84-100).
  - Enforced transaction direction directly from imported evidence: Customer + Money Out = Customer Refund (`PAYMENT`), Supplier + Money In = Supplier Refund (`RECEIPT`).
  - Added `unreconcile_transaction` method to cancel vouchers, clear allocations, and restore transaction state.
- **`apps/accounting/banking_views.py`**:
  - Added `BankTransactionUnreconcileAPIView` mapped to `POST /api/v1/accounting/banking/transactions/<uuid:pk>/unreconcile/`.
  - Added statement exclusion and restoration endpoints.

### 2. Audit Trail & Cryptographic Chaining
- **`apps/audit/models.py`**:
  - Added `schema_version = models.CharField(max_length=10, default='v2', db_index=True)`.
  - Added `sequence = models.BigIntegerField(default=0, db_index=True)`.
  - Migrated `created_at` from `auto_now_add=True` to `default=timezone.now` to prevent Django's `pre_save` timestamp mutation from invalidating computed hashes.
  - Upgraded hash computation to canonical v2 schema: `schema_version|previous_hash|id|company_id|user_id|action|model|record_id|timestamp_iso|ip_address|changes_json`.
  - Serialized hash calculation per company using `Company.objects.select_for_update()`.
- **`apps/audit/views.py`**:
  - Implemented `verify_company_chain_telemetry` returning total records checked, invalid count, first broken ID, and status (`VERIFIED` / `BROKEN`).
  - Exposed `/api/v1/audit/verify/<company_id>/`.
- **`frontend/src/app/audit/page.tsx`**:
  - Bound the verification banner dynamically to live telemetry from the backend API.

### 3. Database & Concurrency Test Infrastructure
- **`config/settings.py`**:
  - Decoupled `test` execution from SQLite; preserved PostgreSQL when `USE_POSTGRES_TEST=1` or `settings_test_pg` is provided.
  - Whitelisted `if-match`, `if-none-match`, `x-voucher-version` in `CORS_ALLOW_HEADERS`.
- **`config/settings_test_pg.py`**:
  - Created dedicated PostgreSQL test settings enforcing PostgreSQL execution with zero silent fallback.
- **`apps/accounting/tests_postgresql_concurrency.py`**:
  - Built multi-threaded test suite testing `select_for_update()` row locks, OCC race conditions, linear audit sequencing, and tenant isolation on live Neon PostgreSQL 18.6.
- **`apps/accounting/tests_bank_evidence_preservation.py`**:
  - Built exhaustive regression suite testing evidence preservation across all transaction types.

### 4. Accounting API & Optimistic Concurrency Control
- **`apps/accounting/views.py`**:
  - Removed strict blocking `HTTP 428 Precondition Required` check in `VoucherDetailAPIView.patch`, allowing unversioned updates to succeed gracefully while maintaining strict 409 Conflict checks whenever `version` or `If-Match` is supplied.
  - Hydrated voucher detail serializers with integer `version` and HTTP `ETag`.

### 5. Frontend & Statement Parser
- **`frontend/src/lib/banking/clientStatementParser.ts`**:
  - Implemented 2D spatial coordinate parser grouping tokens by vertical and horizontal bounding boxes, eliminating multi-line narration leaks and column order flips.
- **`frontend/src/app/banking/page.tsx`**:
  - Bumped statement IndexedDB cache key to `stmt_v2_...`, automatically invalidating stale pre-spatial parses.
- **`frontend/src/app/error.tsx` & `global-error.tsx`**:
  - Added self-healing recovery boundaries with 1-click local cache reset.

---
*Verified against active repository HEAD `b6c020e`.*
