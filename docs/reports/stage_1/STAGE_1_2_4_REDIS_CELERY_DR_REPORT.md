# SRI LEKH — STAGE 1.2.4 REDIS, CELERY & DISASTER RECOVERY REPORT

**Assessment Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Overall Gate Status (Gate E):** **BLOCKED (External Managed Infrastructure & Host PostgreSQL Client Tools Absent)**  
**Application DR & Outbox Worker Logic:** **PASS** *(Verified on SQLite & Neon PostgreSQL 18.6)*

---

## 1. Live Staging Infrastructure Observation

Directly queried `https://vouch-u3u7.onrender.com/api/v1/health/environment/` (`HTTP 200`):
- `environment`: `"staging"` (`version: "1.0.2"`, `commit: "f8578a88"`)
- `database`: `{"engine": "postgresql", "sanitized_target": "neondb_staging", "identity_fingerprint": "6f4741bdaaf4", "is_isolated": true}`
- `redis`: `{"configured": true, "status": "unreachable"}`
- `celery`: `{"beat_schedule_configured": true, "beat_schedule_active": false, "outbox_sweeper_interval_seconds": 60, "workers_online": 0, "task_always_eager": false, "acks_late": true}`
- `migrations`: `{"status": "up_to_date", "unapplied_count": 0}`

---

## 2. Host Binary Tooling Audit (`MISSING`)

Verified directly via PowerShell `Get-Command`:
- `pg_dump`, `pg_restore`, `psql`: **`MISSING`** on Windows host.
- `redis-server`, `redis-cli`: **`MISSING`** on Windows host.
- Docker Desktop CLI (`C:\Program Files\Docker\Docker\resources\bin\docker.exe`) is installed without an active WSL daemon (`docker-desktop` `Stopped`; `docker info` returned client version only with no server section).
- Therefore, native `PGDMP` binary backup (`pg_dump -Fc`) and restore (`pg_restore --single-transaction`) and live Redis/Celery broker failover tests could **not** execute locally and remain **BLOCKED / NOT TESTED**.

---

## 3. Code & Database Verification Observed (`PASS` in Automated Scope)

1. **Celery Configuration & Concurrent Outbox Recovery (Neon PostgreSQL 18.6):**
   - Verified inside `62 / 62` Neon PG run (`apps.accounting.tests_stage4_14_certification`):
     - `CELERY_ACKS_LATE = True`, `CELERY_TASK_REJECT_ON_WORKER_LOST = True`, `CELERY_WORKER_PREFETCH_MULTIPLIER = 1`, `CELERY_TASK_SOFT_TIME_LIMIT = 120`, `CELERY_TASK_TIME_LIMIT = 180`.
     - Concurrent outbox workers cleanly claim rows via `select_for_update(skip_locked=True)` with zero duplicate dispatches, recover expired `PROCESSING` leases (`lease_expires_at <= now`), skip missing recipient emails without breaking voucher commits, and transition poison payloads to `DEAD_LETTER`.
2. **Application-Level MultiFernet Encrypted Disaster Recovery:**
   - Verified `apps.common.tests_disaster_recovery` + `apps.common.tests_code_review_findings`: **`13 / 13` passed (`OK`)** on SQLite (including `MultiFernet` key-rotation decryption & encrypted backup/restore).
   - Verified `Stage413DisasterRecoveryAuditLogTests.test_backup_includes_auditlog_and_syncevent_and_preserves_hashes_on_restore` directly on **Neon PostgreSQL 18.6 (`test_neondb_staging`)**: completed encrypted chunked backup + restore preserving `AuditLog` SHA-256 hash chains and `SyncEvent` rows cleanly.
3. **Seven-Day Operational Soak Status:** **NOT STARTED** (requires paid managed TLS Redis, active `vouch-staging-worker`, active single-replica `vouch-staging-beat` from [`render.yaml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/render.yaml), and 7 continuous days of live health monitoring).
