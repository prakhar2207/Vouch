# SRI LEKH — STAGE 4.14 DISASTER RECOVERY VERIFICATION

**Environment:** Source `neondb_staging` -> Disposable PostgreSQL Restore Target `neondb_staging_dr_restore_s414` (dropped post-drill)  
**Commit SHA:** `990a13bd` (`fix/stage4-12-day6-remediation`, [backup_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/common/services/backup_service.py))  
**Source Database Fingerprint:** `6f4741bdaaf4` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`)  
**Execution Timestamp:** `2026-11-12 13:58–14:03 IST`

---

## Verdict: **CONDITIONAL DR VERIFICATION (`Encrypted JSON Path PASS` / `Native pg_dump/pg_restore NOT VERIFIED`)**

---

## Path A — PostgreSQL-Native Backup & Restore (`pg_dump` / `pg_restore`)

- **Procedure:** Inspected host CLI tool availability via `shutil.which("pg_dump")`, `shutil.which("pg_restore")`, `shutil.which("psql")`.
- **Expected Outcome:** Verify native PostgreSQL custom-format dump (`PGDMP`) and `pg_restore`.
- **Actual Outcome:** **`pg_dump: None`**, **`pg_restore: None`**, **`psql: None`** (PostgreSQL client tools are not installed on the local Windows host, and local Docker Desktop daemon is inactive).
- **Pass/Fail:** **NOT EXECUTED / LIMITATION RECORDED** — Code support (`--format=custom`, `PGSSLMODE`, `PGDMP` detection) exists in [backup_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/common/services/backup_service.py), but native binary execution is unverified here and must be run on a host with `postgresql-client` installed before production promotion.

---

## Path B — Encrypted Deterministic JSON Fallback Backup & Disposable PostgreSQL Restore

- **Procedure:** Executed `scratch/run_stage4_14_dr_drill.py` (`task-50287`):
  1. Encrypted full backup of `neondb_staging` (`DatabaseBackupService.perform_backup`).
  2. Created empty Neon PostgreSQL database `neondb_staging_dr_restore_s414`.
  3. Executed full `manage.py migrate` on empty target.
  4. Restored encrypted archive into `neondb_staging_dr_restore_s414` with deferred FKs, hash-preserving `AuditLog` `bulk_create`, and `sequence_reset_sql`.
  5. Verified PK sets, row counts, sequences, per-company `AuditLog` hash chains, FKs, and 5-tenant financial parity; dropped `neondb_staging_dr_restore_s414` in `finally`.

- **Telemetry & Timing (`RPO` / `RTO`):**
  - **Backup Duration:** `29.121s` (`28.6s` backup step), **Archive Size:** `2.084 MB`
  - **SHA-256 Checksum:** `e4b3fd825754a1e7148f6101cc965af73c11a3fb8b7b7627c69640fcc99f2fbb`
  - **Disposable DB Create:** `0.422s` | **Migrate Empty DB:** `174.37s` | **Encrypted Restore:** `65.676s`
  - **Measured RTO (Create + Migrate + Restore):** **`240.468s` (~4 minutes)**
  - **RPO:** **24 hours** when relying on nightly `02:00 AM IST` Celery Beat snapshots (currently blocked on Render by inactive Beat/Redis), or **on-demand (`< 30s`)** via manual encrypted backup execution, supplemented by Neon PITR if enabled on Neon tier.
  - **Records Restored:** **`28,985`** | **Errors:** **`0`**

- **Exact Table & Integrity Parity Results (`PASS`):**

| Model / Check | Source Snapshot | Restored Target | Result |
|---|---:|---:|---|
| `audit.auditlog` (Count / Exact Snapshot PKs) | 1,231 | 1,232 (+1 post-restore telemetry log) | **1,231 / 1,231 exact PKs preserved** |
| `audit_hash_chain_breaks` (Per-company & global) | 0 | **0** | **PASS** |
| `accounting.syncevent` | 15,286 | 15,286 | **PASS** |
| `protocol.protocoloperation` | 1,134 | 1,134 | **PASS** |
| `protocol.protocoltransaction` | 584 | 584 | **PASS** |
| `accounting.voucher` | 1,251 | 1,251 | **PASS** |
| `accounting.voucheritem` | 862 | 862 | **PASS** |
| `accounting.ledgerentry` | 4,526 | 4,526 | **PASS** |
| `accounting.paymentallocation` | 101 | 101 | **PASS** |
| `inventory.inventoryentry` | 838 | 838 | **PASS** |
| `notifications.transactionaloutboxevent` | 1,009 | 1,009 | **PASS** |
| `notifications.emaildeliverylog` | 1,018 | 1,018 | **PASS** |
| `orphan_entries` / `orphan_items` / `unbalanced_posted` | 0 / 0 / 0 | **0 / 0 / 0** | **PASS** |
| `financial_parity_across_5_companies` | Baseline | **True (100% TB/P&L/BS parity)** | **PASS** |
| PostgreSQL Sequences (`syncevent` / `protocol_tx` / `protocol_op`) | max ID `16,181` / `584` / `1,134` | `last_value` **`16,181` / `584` / `1,134`** | **PASS** |

- **Cleanup Verified:** `neondb_staging_dr_restore_s414` dropped cleanly after verification.
