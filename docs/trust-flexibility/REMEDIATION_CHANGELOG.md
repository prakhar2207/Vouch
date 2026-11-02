# SriLekh — Critical Financial Integrity Remediation Changelog
**Detailed Record of Implemented Remediation Engineering**  
*Document Ref:* `docs/trust-flexibility/REMEDIATION_CHANGELOG.md`  
*Branch:* `feature/critical-financial-integrity`  

---

## [Unreleased / Production-Candidate] — 2026-11-02

### Added
- **Immutable Bank Evidence Model Fields (`BankTransaction`):**
  - Added `raw_debit_amount` and `raw_credit_amount` to preserve raw imported statement numbers permanently.
  - Added `user_classification` (e.g. `CUSTOMER_RECEIPT`, `CUSTOMER_REFUND`, `SUPPLIER_PAYMENT`, `SUPPLIER_REFUND`, `EXPENSE`, `CONTRA`) and `is_refund` boolean.
  - Added `save()` guard initializing raw amounts on initial creation.
  - Migration: `apps/accounting/migrations/0043_banktransaction_is_refund_and_more.py`.
- **Audited Unreconcile Workflow:**
  - Added `BankReconciliationService.unreconcile_transaction` allowing users to safely reverse auto-created vouchers and return bank transactions to `UNRESOLVED` state without modifying bank evidence.
  - Added `POST /api/v1/accounting/banking/transactions/<uuid:pk>/unreconcile/` view in `apps/accounting/banking_views.py`.
- **Dedicated PostgreSQL Test Configuration & Suite:**
  - Added `config/settings_test_pg.py` configuring PostgreSQL test execution without silent SQLite fallback.
  - Added `apps/accounting/tests_postgresql_concurrency.py` testing multi-threaded `select_for_update()` row-level locks, concurrent audit hash chaining, and tenant isolation on live Neon PostgreSQL 18.6.
  - Added `apps/accounting/tests_bank_evidence_preservation.py` verifying customer/supplier payments and refunds against PostgreSQL.
- **Audit Hash Payload Completeness (v2 Scheme):**
  - Added `schema_version = models.CharField(max_length=10, default='v2', db_index=True)` to `AuditLog`.
  - Added monotonic `sequence = models.BigIntegerField(default=0, db_index=True)` to ensure strictly linear, tamper-evident ordering under concurrent writes.
  - Extended canonical SHA-256 v2 hash to bind `schema_version`, `previous_hash`, `event_id`, `company_id`, `user_id` (actor attribution), `action`, `model_name`, `record_id`, `timestamp_iso`, `ip_address`, and deterministic JSON.
  - Changed `created_at` to `default=timezone.now` to prevent Django `auto_now_add` mutation from breaking the hash during `pre_save`.
  - Migrations: `0005`, `0006`, and `0007` in `apps/audit/migrations/`.
- **Dynamic Audit Verification API & UI Telemetry:**
  - Added `AuditVerificationAPIView` at `/api/v1/audit/verify/<company_id>/` returning structured telemetry (status, records checked, invalid count, first tampered ID).
  - Updated `frontend/src/app/audit/page.tsx` to dynamically render backend verification status, eliminating hardcoded mock badges.

### Changed
- **Bank Reconciliation Engine (`BankReconciliationService.resolve_transaction`):**
  - Completely removed in-place mutations of `bank_tx.credit_amount` and `bank_tx.debit_amount`.
  - Derived transaction direction strictly from imported bank statement evidence.
  - Separated accounting interpretation from imported source evidence: customer money out resolves to Customer Refund (`PAYMENT` voucher); supplier money in resolves to Supplier Refund/Rebate (`RECEIPT` voucher).
- **Django Test Database Selection (`config/settings.py`):**
  - Decoupled `test` in `sys.argv` so that when `USE_POSTGRES_TEST=1` or `config.settings_test_pg` is specified, PostgreSQL is preserved rather than falling back to SQLite.

### Fixed
- **DEF-01:** Silent mutation of original imported bank statement debit/credit amounts.
- **DEF-07:** SQLite test runner masking PostgreSQL concurrency and row-level locking behaviour.
- **DEF-08:** Incomplete audit hash payload and static mock verification claims in audit UI.
- **DEF-09:** Inflated documentation scorecard claims lacking verifiable runtime evidence.

---
*Maintained by SriLekh Quality Assurance & Core Reliability Engineering.*
