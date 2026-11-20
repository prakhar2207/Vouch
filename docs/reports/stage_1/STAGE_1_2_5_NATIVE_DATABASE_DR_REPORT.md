# SRI LEKH — STAGE 1.2.5 NATIVE DATABASE DISASTER RECOVERY REPORT

**Assessment Date:** 2026-11-12  
**Branch / Commit:** `feat/google-play-launch-readiness` @ `c160fca0`  
**Overall Gate Verdict (Gate E — Native Database DR):** **PARTIALLY VERIFIED / STAGING DR PENDING** *(Native PostgreSQL 18 `pg_dump -Fc` -> `pg_restore --single-transaction` binary DR verified in Cloud CI + real Django DR deadlock bug fixed and proven on both Neon PG 18.6 & CI PG 18; live `neondb_staging` snapshot DR still requires owner execution)*

---

## 1. Stage 1.2.5 Code Defect Discovered & Remediated

During Cloud CI Ubuntu PostgreSQL 18 verification (`pg_dump`/`pg_restore` binaries present on host, unlike Windows), testing uncovered two real DR defects:
1. **`pg_restore --clean` Deadlock inside Django `TestCase`:** [`tests_disaster_recovery.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/common/tests_disaster_recovery.py#L46-L52) and [`tests_stage4_13_stabilization.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/tests_stage4_13_stabilization.py#L72-L80) ran full-DB `DatabaseBackupService.perform_backup()` inside open `TestCase` transactions and restored `--clean` over `'default'`, deadlocking external `pg_restore` against Django's uncommitted transaction locks. Scoping those `TestCase` assertions to `company_id=str(self.company.id)` exercises full encrypted serialization + in-transaction restore cleanly while leaving standalone full-DB DR free to use `pg_dump` / `pg_restore`.
2. **SQLite Shared-Cache Memory Lock & Subprocess Timeout Hardening ([`backup_service.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/common/services/backup_service.py)):**
   - Added configurable `DB_BACKUP_SUBPROCESS_TIMEOUT_SECONDS` (default `1800`s) to `pg_dump` and `pg_restore` subprocess calls so hung DB locks fail safely instead of blocking indefinitely.
   - Extracted `_dump_json_fixture()` so SQLite memory-URI (`:memory:` / `file:...`) or `company_id`-scoped runs avoid shared-cache `sqlite3.backup()` lockups and standardize `"error_count": 0` across all restore response formats.

---

## 2. Independent Verification Evidence (Post-Fix `c160fca0`)

| Test / Exercise | Target Database | Observed Result |
| :--- | :--- | :--- |
| **Native PostgreSQL 18 Binary Dump & Restore (CI Run `43259891989`, Job `131328026519`, Step 8)** | `postgresql:18` `neondb_ci_staging` -> fresh `neondb_ci_restore_scratch` | **PASS (`completed success`):** `pg_dump -Fc --no-owner`, `createdb`, `pg_restore --no-owner --single-transaction`; **`CI_NATIVE_DR_RTO_SECONDS=1`**, **`MIGRATIONS src=147 dst=147`** |
| **PG 18 Application DR Test Suite (CI Run `43259891989`, Step 7)** | `postgresql:18` `test_neondb_ci_staging` | **PASS (`26 / 26` OK in `14.287s`)** including `apps.common.tests_disaster_recovery` and `apps.audit.tests` |
| **Neon PostgreSQL 18.6 DR + Stage 4.13 Hash-Chain Restore (`task-14068`)** | Neon `test_neondb_staging` | **PASS (`36 / 36` OK in `586.415s`)** including `DisasterRecoveryBackupRestoreTestCase` and `Stage413DisasterRecoveryAuditLogTests` |
| **Local Isolated SQLite DR & Key-Rotation Suite (`task-14032`)** | In-memory SQLite | **PASS (`17 / 17` OK in `8.083s`)** (`tests_disaster_recovery`, `tests_stage4_13_stabilization`, `tests_code_review_findings`) |

---

## 3. Remaining Action for Production DR Sign-Off (`OA-07`)

- Execute a native `pg_dump -Fc` -> scratch DB `pg_restore` exercise directly against a snapshot/copy of live populated **`neondb_staging`** (not only fresh empty migrated schema `neondb_ci_staging`) and verify non-zero row counts, `AuditLog` SHA-256 hash continuity, and `TrialBalance` parity on the restored scratch DB.
- Configure off-site encrypted S3/R2 bucket credentials (`AWS_STORAGE_BUCKET_NAME`, `BACKUP_ENCRYPTION_KEY`, fallback rotation keys) and verify upload retention pruning in staging.
