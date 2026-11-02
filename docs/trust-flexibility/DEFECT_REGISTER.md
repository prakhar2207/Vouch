# SriLekh — Master Defect Register
**Comprehensive Defect Tracking & Verification Ledger**  
*Document Ref:* `docs/trust-flexibility/DEFECT_REGISTER.md`  
*Branch:* `feature/critical-financial-integrity`  

---

## Master Defect Inventory

| Defect ID | Severity | Module / Area | Summary | Root Cause | Implemented Remediation | Test Verification Evidence | Status |
|---|:---:|---|---|---|---|---|:---:|
| **DEF-01** | `P0` | Banking Engine | Silent mutation of original imported bank statement debit/credit amounts | `resolve_transaction` forcibly overwrote `credit_amount` and `debit_amount` based on party type rather than preserving imported evidence | Removed all in-place mutations; added `raw_debit_amount`, `raw_credit_amount`, `user_classification`, and `is_refund`; separated interpretation from evidence | `tests_bank_evidence_preservation.py` (6/6 PASS on PostgreSQL) | **RESOLVED** |
| **DEF-02** | `P1` | Banking API | Statement exclusion modal returned `HTTP 404 Not Found` | Lacked explicit backend route handler for statement-level exclusion | Added `BankStatementImportDetailAPIView.post` and restore handlers in `banking_views.py` | `tests_banking_production.py` (11/11 PASS) | **RESOLVED** |
| **DEF-03** | `P1` | Accounting Engine | Voucher edit modal returned `HTTP 428 Precondition Required` | Backend enforced OCC version check but voucher detail serializers omitted `version` | Serialized integer `version` and HTTP `ETag`; hydrated modal state with version | `tests_hardening.py` (25/25 PASS) | **RESOLVED** |
| **DEF-04** | `P1` | API / CORS | PATCH requests failed with CORS preflight rejection on `If-Match` | Django `CORS_ALLOW_HEADERS` omitted conditional headers | Whitelisted `if-match`, `if-none-match`, `x-voucher-version` in `config/settings.py`; passed version in payload body | Simulated browser preflight | **RESOLVED** |
| **DEF-05** | `P2` | Frontend / PWA | Mobile PWA build rejected and desktop onboarding tour caused mobile crash loops | Cache query strings (`?v=...`) in manifest icons broke APK compilers; unshielded `localStorage` in tour | Sanitized manifest icons; desktop-guarded `OnboardingTour` ($\ge 768\text{px}$); added self-healing error boundary in `error.tsx` | Next.js Build (47/47 routes clean) | **RESOLVED** |
| **DEF-06** | `P0` | Multi-Tenant Security | Risk of automated test scripts mutating real user accounts (e.g. `Maa Annapurna Belting Store`) | Lack of mandatory company ID assertion across automated test runners | Strictly enforced `GEMINI.md` policy requiring all automated tests to assert sandbox ID `4e62863a-08f9-4e99-b0bd-64873acfdd33` | Verified zero mutations across all test runs | **VERIFIED** |
| **DEF-07** | `P1` | Database Reliability | SQLite test runner silently masked PostgreSQL concurrency and locking behaviour | `settings.py` unconditionally forced `django.db.backends.sqlite3` whenever `'test'` was in `sys.argv` | Created dedicated `config/settings_test_pg.py` and environment-driven PostgreSQL test harness; added multi-threaded concurrency suite | `tests_postgresql_concurrency.py` (4/4 PASS on live PostgreSQL) | **RESOLVED** |
| **DEF-08** | `P1` | Audit Trail & UI | Audit hash omitted actor, IP, timestamp; UI hardcoded "Verified" without checking backend | Incomplete hash formula (`v1`) and frontend static mock labels in `page.tsx` | Upgraded to canonical `v2` SHA-256 hash (actor, IP, timestamp, monotonic `sequence`); dynamically bound audit UI to backend telemetry | `apps/audit/tests.py` (4/4 PASS); Next.js build | **RESOLVED** |
| **DEF-09** | `P1` | Release Governance | Inflated 10/10 certification scores without verifiable production proof | Reports claimed 10/10 across all dimensions without distinguishing SQLite tests from PostgreSQL tests | Reconciled all documentation in `docs/trust-flexibility/`; established evidence-based scoring distinguishing tested from unverified items | `TEST_RESULTS.md`, `FINAL_SCORECARD.md` | **RESOLVED** |

---

## Detailed Root Cause & Remediation Audits

### DEF-01: Original Bank Evidence Mutation
- **Source Reference:** `apps/accounting/services/bank_reconciliation_service.py:84-100`
- **Root Cause:** In an attempt to defensively guard against column-inverted OCR scans, the code unconditionally reassigned `bank_tx.credit_amount` and `bank_tx.debit_amount` when a customer or supplier was matched. This destroyed the raw bank evidence and prevented legitimate customer refunds (money out) and supplier refunds (money in).
- **Remediation:**
  1. Added immutable fields `raw_debit_amount` and `raw_credit_amount` to `BankTransaction`, populated on initial record creation.
  2. Removed all in-place mutations of `debit_amount` and `credit_amount` from `resolve_transaction`.
  3. Direction is strictly derived from imported evidence: Customer + Money Out = Customer Refund (`PAYMENT` voucher); Supplier + Money In = Supplier Refund (`RECEIPT` voucher).
  4. Added `user_classification`, `is_refund`, and `interpretation_history` tracking inside `match_notes`.
  5. Added `unreconcile_transaction` allowing safe reversal of matched vouchers without altering bank evidence.
- **Test Evidence:** `apps.accounting.tests_bank_evidence_preservation` (6/6 tests passing on PostgreSQL).

### DEF-07: PostgreSQL Test Verification
- **Source Reference:** `config/settings.py:162-167`, `config/settings_test_pg.py`
- **Root Cause:** Hardcoded `if 'test' in sys.argv: DATABASES['default'] = {'ENGINE': 'django.db.backends.sqlite3'}` silently diverted all test runs away from PostgreSQL. SQLite's database-level file lock masked PostgreSQL `select_for_update()` row-level locks and concurrency behaviour.
- **Remediation:**
  1. Decoupled test database selection in `config/settings.py` so PostgreSQL is preserved when `USE_POSTGRES_TEST=1` or `--settings=config.settings_test_pg` is specified.
  2. Created dedicated `config/settings_test_pg.py` enforcing PostgreSQL test execution.
  3. Created `apps/accounting/tests_postgresql_concurrency.py` verifying real PostgreSQL row-level locks across independent worker threads.
- **Test Evidence:** `python manage.py test apps.accounting.tests_postgresql_concurrency --keepdb --settings=config.settings_test_pg` (4/4 passing on PostgreSQL).

### DEF-08: Audit Hash Completeness & Dynamic UI Verification
- **Source Reference:** `apps/audit/models.py:53-61`, `apps/audit/views.py:80-102`, `frontend/src/app/audit/page.tsx:172-195`
- **Root Cause:** The SHA-256 hash omitted `user_id`, `ip_address`, and `created_at`. In addition, rapid multi-threaded writes in the same millisecond sorted out-of-order due to random UUID4 keys. The frontend audit page hardcoded static "Verified" badges without inspecting backend verification results.
- **Remediation:**
  1. Extended canonical hash payload (`v2`) to include `schema_version`, `previous_hash`, `event_id`, `company_id`, `user_id`, `action`, `model_name`, `record_id`, `timestamp_iso`, `ip_address`, and deterministic JSON.
  2. Added monotonic integer `sequence` field to `AuditLog`, ensuring mathematical linearity during concurrent execution.
  3. Changed `created_at` to `default=timezone.now` to prevent Django's `auto_now_add` from mutating the timestamp after hash calculation.
  4. Implemented `verify_company_chain_telemetry` returning structured telemetry (status, records checked, invalid count, first tampered ID).
  5. Wired `frontend/src/app/audit/page.tsx` dynamically to display actual verification status from backend API.
- **Test Evidence:** `apps.audit.tests` (4/4 passing); Next.js production build clean.

---
*Maintained by SriLekh Quality Assurance & Core Reliability Engineering.*
