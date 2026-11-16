# SRI LEKH — STAGE 1.2.6 POPULATED DATABASE & DISASTER RECOVERY CERTIFICATION

**Assessment Date:** 2026-11-12  
**Evaluated Environment:** `neondb_staging` (`ep-silent-feather-a590v8yq-pooler.us-east-2.aws.neon.tech`)  
**Safety Invariant:** Zero test writes executed; read-only inspection against `neondb_staging` only; `neondb` production untouched  
**Certification Verdict:** **PARTIALLY VERIFIED (CI Binary DR Certified; Live Staging Accounting Integrity 100% Verified; Populated Restore Pending Owner Cloud/PG Tools - OA-07)**  

---

## 1. Executive Summary

This certification report provides objective verification across two disaster recovery and accounting integrity dimensions:
1. **Live Read-Only Accounting, Sync, and Outbox Integrity Audit** across the entire populated `neondb_staging` database (`1,252` vouchers, `4,530` ledger entries, `7` companies).
2. **PostgreSQL 18 Binary Backup & Restore Proof** in Cloud CI (`1` second RTO) paired with the operational runbook required to perform the same binary dump/restore test against populated `neondb_staging` into an ephemeral scratch database.

---

## 2. Live Staging Database Read-Only Audit (`neondb_staging`)

A read-only Python/Django inspection harness queried `neondb_staging` directly (strictly enforcing `DATABASE_URL` isolation checks to guarantee `neondb` production was not targeted).

### 2.1 Global Table & Queue Census
| Entity / Table | Live Staging Count | Operational Status |
| :--- | :--- | :--- |
| `Company` | `7` | Healthy |
| `Voucher` | `1,252` | Healthy |
| `LedgerEntry` | `4,530` | Healthy |
| `InventoryEntry` | `839` | Healthy |
| `AuditLog` | `1,239` | Healthy |
| `SyncEvent` | `15,385` | Healthy |
| `OutboxEvent` (Total) | `1,009` | Healthy |
| `OutboxEvent` (`PROCESSING`) | `0` | **0 Stuck Rows** |
| `OutboxEvent` (`FAILED`) | `0` | **0 Failed Rows** |

---

### 2.2 Per-Company Double-Entry & Tamper-Chain Verification

Every single company in `neondb_staging` was verified using `ReportService.generate_trial_balance` and `ReportService.generate_balance_sheet`, alongside SHA-256 hash chain verification on `AuditLog`.

| # | Company Name | TB Debit (INR) | TB Credit (INR) | TB Variance | TB Equilibrium | BS Equilibrium | AuditLog Records | SHA-256 Chain Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **Staging MSME Alpha Belts Pvt Ltd** | `831,328.66` | `831,328.66` | `0.00` | **BALANCED** | **BALANCED (0.00)** | `468` | **VERIFIED (0 invalid)** |
| 2 | **Staging Beta Engineering Supplies Ltd** | `287,835.00` | `287,835.00` | `0.00` | **BALANCED** | **BALANCED (0.00)** | `52` | **VERIFIED (0 invalid)** |
| 3 | **Precision Agro Tools Pvt Ltd** | `1,694,738.70` | `1,694,738.70` | `0.00` | **BALANCED** | **BALANCED (0.00)** | `559` | **VERIFIED (0 invalid)** |
| 4 | **Garodia Bearing & Power Transmission** | `678,241.20` | `678,241.20` | `0.00` | **BALANCED** | **BALANCED (0.00)** | `73` | **VERIFIED (0 invalid)** |
| 5 | **Shree Radhe Industrial Hardware** | `505,813.79` | `505,813.79` | `0.00` | **BALANCED** | **BALANCED (0.00)** | `68` | **VERIFIED (0 invalid)** |
| 6 | **Stage 4.14 Live Audit Sandbox** | `500.00` | `500.00` | `0.00` | **BALANCED** | **BALANCED (0.00)** | `15` | *Intentional Tamper Fixture (`1` invalid from Stage 4.14)* |
| 7 | **Stage 125 Live Staging Cert Co 8** | `0.00` | `0.00` | `0.00` | **BALANCED** | **BALANCED (0.00)** | `1` | **VERIFIED (0 invalid)** |

### Key Analytical Takeaway:
Across `1,252` operational vouchers and `4,530` double-entry legs spanning 7 companies, total financial variance is **0.00 INR**. Double-entry accounting invariants and outbox integrity are completely intact.

---

## 3. PostgreSQL 18 Binary Disaster Recovery Proof (Cloud CI)

In `.github/workflows/stage-verification-ci.yml`, native PostgreSQL 18 client binaries were executed against an ephemeral migrated schema:
```bash
START_TS=$(date +%s)
pg_dump -Fc --no-owner -h 127.0.0.1 -U srilekh_ci -d neondb_ci_staging -f /tmp/ci_staging.dump
createdb -h 127.0.0.1 -U srilekh_ci neondb_ci_restore_scratch
pg_restore --no-owner --single-transaction -h 127.0.0.1 -U srilekh_ci -d neondb_ci_restore_scratch /tmp/ci_staging.dump
END_TS=$(date +%s)
```

### Observed CI Telemetry:
- **Dump Format:** PostgreSQL Custom Format (`-Fc`, compressed binary)
- **Restore Atomicity:** `--single-transaction` (all-or-nothing schema + data replay)
- **Recorded RTO:** `1` second
- **Migration Parity:** `147 / 147` (`django_migrations` row count match `100%`)

---

## 4. Why Full Populated Staging DR Remains Partially Open (Local Environment Audit)

An audit of the execution workstation detected the following binary absences:
- `pg_dump`: Not installed (`False`)
- `pg_restore`: Not installed (`False`)
- `psql`: Not installed (`False`)
- `docker`: Installed, but daemon is stopped/uninitialized (`returncode: 1`)

Because native PostgreSQL client utilities are absent on this Windows workstation and Docker is stopped, executing a live binary `pg_dump -Fc` snapshot of the populated `neondb_staging` cloud database and restoring it into a populated scratch target must be executed either via a cloud runner (with `STAGING_DATABASE_URL` secret) or an admin machine with PostgreSQL 17/18 client tools installed.

---

## 5. Owner / DevOps Populated Database DR & Off-Site Backup Runbook (OA-07)

To close **OA-07**, the owner or DevOps engineer must execute the following procedure from a machine with PostgreSQL 17/18 tools (or a GitHub Actions workflow using a scratch Neon branch):

### Step 1: Capture Populated Staging Binary Snapshot
```bash
export STAGING_DB_URL="<neondb_staging connection string>"
export SCRATCH_DB_URL="<neondb_scratch_restore connection string>"

pg_dump -Fc --no-owner --no-privileges "$STAGING_DB_URL" -f staging_backup_$(date +%F).dump
```

### Step 2: Restore to Ephemeral Scratch Database & Measure RTO
```bash
START_TS=$(date +%s)
pg_restore --no-owner --no-privileges --clean --if-exists --single-transaction -d "$SCRATCH_DB_URL" staging_backup_$(date +%F).dump
END_TS=$(date +%s)
echo "Populated DR RTO: $((END_TS - START_TS)) seconds"
```

### Step 3: Verify Parity on Restored Scratch Database
```bash
psql "$SCRATCH_DB_URL" -c "
  SELECT
    (SELECT count(*) FROM companies_company) AS companies,
    (SELECT count(*) FROM accounting_voucher) AS vouchers,
    (SELECT count(*) FROM accounting_ledgerentry) AS ledger_entries,
    (SELECT count(*) FROM audit_auditlog) AS audit_logs,
    (SELECT count(*) FROM notifications_outboxevent WHERE status='PROCESSING') AS stuck_outbox;
"
```
**Expected Output:**
`companies: 7 | vouchers: 1252 | ledger_entries: 4530 | audit_logs: 1239 | stuck_outbox: 0`

### Step 4: Configure Off-Site S3 Retention Policy
1. Provision encrypted AWS S3 / Cloudflare R2 bucket (`srilekh-db-backups-prod`).
2. Configure automated daily cron or GitHub Actions schedule executing `pg_dump -Fc` -> AES-256 SSE upload -> 30-day lifecycle expiration rule (`30d` hot, `365d` Glacier archive for financial audit compliance).
3. Restrict IAM policy to `PutObject` only (append-only protection against ransomware/accidental deletion).
