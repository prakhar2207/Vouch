# SRI LEKH — STAGE 4.15 NATIVE POSTGRESQL DR CERTIFICATION

**Environment:** Local Windows Host + `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`)  
**Commit SHA:** `c15a64fb` (`fix/stage4-12-day6-remediation`, [backup_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/common/services/backup_service.py))  
**Source Database Fingerprint:** `6f4741bdaaf4`  
**Execution Timestamp:** `2026-11-12 14:15 IST` (CLI inspection) / `2026-11-12 13:58–14:03 IST` (Encrypted JSON DR Drill)

---

## Verdict: **NATIVE BINARY DR `UNVERIFIED / BLOCKED` (`pg_dump`/`pg_restore` Unavailable Here) — ENCRYPTED JSON DR `PASS`**

Per Stage 4.15 Section 9 & Rule 11 ("If native tooling remains unavailable, report it as unverified. Do not claim native DR PASS based on JSON fallback tests"), **native PostgreSQL DR certification remains `UNVERIFIED / BLOCKED`** until executed on a host or CI runner with PostgreSQL client binaries (`postgresql-client`) installed.

---

## 1. Native PostgreSQL CLI Inspection

- **Commands Checked:**
  - `shutil.which("pg_dump")` -> **`None`**
  - `shutil.which("pg_restore")` -> **`None`**
  - `shutil.which("psql")` -> **`None`**
  - `Test-Path 'C:\Program Files\PostgreSQL'` -> **`False`**
  - `Get-Service -Name '*postgres*','*docker*'` -> **`com.docker.service: Stopped`** (no local PostgreSQL service)
- **Code Inspection of [backup_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/common/services/backup_service.py):**
  - Native dump invokes `pg_dump --format=custom --no-owner --no-acl -f <tmp_dump>` with `PGPASSWORD` and `PGSSLMODE=require` passed safely via subprocess `env` (without exposing passwords in CLI args), followed by gzip + optional Fernet AES encryption.
  - Native restore detects `PGDMP` header after decryption/decompression and invokes `pg_restore --clean --if-exists --no-owner --no-acl --single-transaction -d <target>` via `PGPASSWORD` / `PGSSLMODE`.
  - **Limitation:** Binary execution of `pg_dump` and `pg_restore` against Neon PostgreSQL 18 could not run on this workstation because `postgresql-client` binaries are absent.

---

## 2. Encrypted JSON Fallback DR Verification Baseline (Observed `2026-11-12`)

Executed against disposable Neon database `neondb_staging_dr_restore_s414` (dropped post-drill):
- **Archive Format / Size / SHA-256:** Encrypted gzipped deterministic JSON batch archive | **`2.084 MB`** | `e4b3fd825754a1e7148f6101cc965af73c11a3fb8b7b7627c69640fcc99f2fbb`
- **Measured RTO:** **`240.468s`** (Create `0.422s` + Migrate `174.37s` + Restore `65.676s`)
- **RPO:** 24h automated nightly schedule (once Beat/Redis are active on Render) / `<30s` on-demand snapshot (`backup_elapsed_s: 29.121s`)
- **Record & Parity Summary:**
  - `records_restored`: **`28,985`** | `error_count`: **`0`**
  - `audit.auditlog`: **`1,231 / 1,231`** exact snapshot PKs preserved (`1,232` restored including 1 post-restore telemetry entry), `audit_hash_chain_breaks: 0`
  - `accounting.syncevent`: `15,286 / 15,286` | `protocol.protocoloperation`: `1,134 / 1,134` | `protocol.protocoltransaction`: `584 / 584`
  - `accounting.voucher`: `1,251 / 1,251` | `accounting.voucheritem`: `862 / 862` | `accounting.ledgerentry`: `4,526 / 4,526` | `accounting.paymentallocation`: `101 / 101` | `inventory.inventoryentry`: `838 / 838` | `notifications.transactionaloutboxevent`: `1,009 / 1,009` | `notifications.emaildeliverylog`: `1,018 / 1,018`
  - `orphan_entries: 0` | `orphan_items: 0` | `unbalanced_posted: 0` | `financial_parity_across_5_companies: True`
  - PostgreSQL sequences (`sequence_reset_sql`): `accounting_syncevent=16,181`, `protocol_transactions=584`, `protocol_operations=1,134`
- **Automated Regression Guard:** `apps.common.tests_disaster_recovery` (`1/1 OK`) and `Stage413DisasterRecoveryAuditLogTests` (`1/1 OK`) passing on `test_neondb_staging`.

---

## Required Action for Native DR Sign-Off

Run a disposable native drill (`neondb_staging` -> `neondb_staging_dr_native_check`) on an isolated Ubuntu/GitHub Actions/PostgreSQL-18 client host with `pg_dump`/`pg_restore` installed (`pg_dump --format=custom`), verify `PGDMP` header, restore into an empty DB, assert `AuditLog` hash chains, sequences, and 5-tenant financial parity, record native RTO/RPO, and drop the disposable DB.
