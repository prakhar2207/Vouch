# SRI LEKH — STAGE 4.13 DISASTER RECOVERY CERTIFICATION

**Date:** 2026-11-12  
**Source Database:** `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`, fingerprint `6f4741bdaaf4`)  
**Disposable Restore Target:** `neondb_staging_dr_restore_s413` (created on staging cluster, verified, and dropped post-drill)  
**Service Remediated:** [apps/common/services/backup_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/common/services/backup_service.py)

---

## 1. Root Cause Analysis of Stage 4.12 DR Defect

In Stage 4.12, backup/restore left `AuditLog` (`auditlog`) missing or excluded, breaking compliance auditability:
1. `_EXCLUDED_MODELS` in `DatabaseBackupService` explicitly excluded `auditlog`, `syncevent`, and `permission`.
2. `_log_audit_event()` invoked `AuditLog.objects.create(..., details=...)`, which raised an exception because `AuditLog` uses `model_name`, `record_id`, and `changes` rather than `details`.
3. `AuditLog.save()` (`apps/audit/models.py`) rejects updates when `self.pk` exists and recomputes `sequence`, `previous_hash`, and `current_hash`, which would alter historical tamper-evident hashes if restored via normal `.save()`.
4. Circular foreign keys (such as `Voucher.reversal_voucher` referencing reversal vouchers) require single-transaction restore with `SET CONSTRAINTS ALL DEFERRED` and deterministic ordering (`('sequence', 'created_at', pk_name)` for `AuditLog`, `pk_name` for all other models).
5. `BigAutoField` sequences needed `connection.ops.sequence_reset_sql(...)` execution after PK-preserving inserts.
6. Local environment lacks `pg_dump`/`pg_restore` binaries (Docker Desktop daemon also inactive), so deterministic encrypted batch JSON fallback paths are used locally while native `--format=custom` + `PGSSLMODE` is supported wherever `pg_dump`/`pg_restore` exist.

---

## 2. Backup & Disposable PostgreSQL DR Drill Telemetry

| Metric | Observed Value |
|---|---|
| Backup Elapsed Time | **`29.34s`** |
| Encrypted Artifact Size | **`2.069 MB`** |
| Artifact SHA-256 Checksum | `e64b0ff35ac2211d31552947396119bbc665527fd7dc74e2ee71d3f4e00dbd87` |
| Disposable DB Creation Time | `0.513s` |
| Django `migrate` on Empty DB | `180.941s` |
| Full Encrypted Restore Time | `46.987s` |
| **Total RTO (Create + Migrate + Restore)** | **`228.441s` (~3m 48s)** |
| Records Restored | **`28,815`** |
| Restore Errors | **`0`** |

---

## 3. Model-by-Model Count & PK Parity Verification

| Model | Source Snapshot Count | Restored Count | Notes |
|---|---|---|---|
| `audit.auditlog` | **1,221** | **1,222** | All **1,221 / 1,221** exact snapshot PKs preserved (`auditlog_pk_subset_exact=1221`); `+1` row is the post-restore DR telemetry `AuditLog` (`action='RESOLVE'`) |
| `protocol.protocoloperation` | 1,131 | 1,131 | Exact parity |
| `protocol.protocoltransaction` | 584 | 584 | Exact parity |
| `accounting.voucher` | 1,246 | 1,246 | Exact parity (circular `reversal_voucher` FKs preserved) |
| `accounting.voucheritem` | 860 | 860 | Exact parity (`orphan_items=0`) |
| `accounting.ledgerentry` | 4,508 | 4,508 | Exact parity (`orphan_entries=0`, `unbalanced_posted=0`) |
| `accounting.paymentallocation` | 101 | 101 | Exact parity |
| `accounting.syncevent` | 15,198 | 15,198 | Exact parity |
| `inventory.inventoryentry` | 838 | 838 | Exact parity |
| `notifications.transactionaloutboxevent` | 1,009 | 1,009 | Exact parity |
| `notifications.emaildeliverylog` | 1,018 | 1,018 | Exact parity |

---

## 4. PostgreSQL Sequence, Referential, Hash-Chain & Financial Parity Checks

- **PK Parity Verified:** `True` (`1,221 / 1,221` snapshot `AuditLog` PKs matched in `neondb_staging_dr_restore_s413`).
- **PostgreSQL `BigAutoField` Sequence Parity (`sequence_reset_sql`):**
  - `accounting_syncevent`: max PK `16,093` -> restored sequence `last_value = 16,093`
  - `protocol_transactions`: max PK `584` -> restored sequence `last_value = 584`
  - `protocol_operations`: max PK `1,131` -> restored sequence `last_value = 1,131`
- **Referential Integrity Post-Restore:** `orphan_entries = 0`, `orphan_items = 0`, `unbalanced_posted = 0`.
- **Financial Parity Across All 5 Cohort Tenants:** `financial_parity_across_5_companies = True` (Trial Balance, P&L net profit, and Balance Sheet matched source 100%).
- **Source `neondb_staging` Per-Company `AuditLog` Hash-Chain Continuity:** Audited across all `1,222` `AuditLog` records (`52` Beta, `468` Alpha, `559` Precision Agro, `73` Garodia, `68` Shree Radhe, `2` global/None) with **`0` hash-chain breaks**.
- **Disposable DB Cleanup:** `neondb_staging_dr_restore_s413` dropped and confirmed absent (`databases_present`: `neondb`, `neondb_staging`, `postgres`, `test_neondb_staging`).
- **Automated Regression Guard:** `Stage413DisasterRecoveryAuditLogTests.test_backup_includes_auditlog_and_syncevent_and_preserves_hashes_on_restore` verified passing on PostgreSQL (`test_neondb_staging`).
