# SRI LEKH — STAGE 4.15 EXTERNAL INFRASTRUCTURE BLOCKERS STATUS

**Date:** 2026-11-12  
**Live Staging Target Checked:** `https://vouch-u3u7.onrender.com/api/v1/health/environment/`  
**Scope:** Re-verify current status of Stage 4.15 external blockers without purchasing paid infrastructure or fabricating operational telemetry.

---

## 1. Current Observed Status on Render Staging (`https://vouch-u3u7.onrender.com`)

Queried live during this assessment (`HTTP 200`):

- **Branch / Commit Deployed on Staging Render (`vouch-u3u7`):** `fix/stage4-12-day6-remediation` (`f8578a88`)
- **Database Target:** `neondb_staging` (`identity_fingerprint: "6f4741bdaaf4"`, `is_isolated: true`)
- **Redis (`redis`):** `{"configured": true, "status": "unreachable"}` -> **STILL BLOCKED**
- **Celery (`celery`):** `{"beat_schedule_configured": true, "beat_schedule_active": false, "outbox_sweeper_interval_seconds": 60, "workers_online": 0, "task_always_eager": false, "acks_late": true}` -> **STILL BLOCKED**
- **Native PostgreSQL CLI on Host (`pg_dump`, `pg_restore`, `psql`):** Still absent from Windows host -> **STILL BLOCKED / UNVERIFIED**
- **Seven-Day Live Operational Soak:** Cannot initiate without live Redis, Celery Worker, and Celery Beat -> **NOT STARTED (BLOCKED)**

---

## 2. Required External Actions Before Production GO

| Blocker | Current State | Exact Action / Configuration Required (Do Not Auto-Purchase) |
| :--- | :--- | :--- |
| **A. Managed Redis + Celery Worker + Celery Beat** | [`render.yaml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/render.yaml) already defines `vouch-staging-worker` (`celery -A config worker ...`) and `vouch-staging-beat` (`celery -A config beat ...`), plus `REDIS_URL` binding, but Render Free tier cannot host background worker dynos. | 1. Provision managed TLS Redis (e.g., Upstash / Render Key Value) and set `REDIS_URL=rediss://...` on web, worker, and beat services.<br>2. Provision 1x Starter (or higher) `worker` service (`vouch-staging-worker`) and 1x single-replica Starter `worker` service (`vouch-staging-beat`).<br>3. Verify `workers_online >= 1`, `beat_schedule_active: true`, `redis.status: "ok"` on `/api/v1/health/environment/`. |
| **B. Outbound SMTP Relay / Non-Blocking Reset Email** | `POST /api/v1/auth/password/reset/request/` previously blocked >45s on Render waiting on synchronous SMTP (`smtp.gmail.com:587`). `EMAIL_TIMEOUT=10` & exception safety are now added in code, but actual delivery to a real test mailbox on staging still requires verified SMTP/relay credentials (`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD` or HTTP API/Resend/Postmark + `EMAIL_BACKEND`). | Configure valid staging SMTP / transactional email provider credentials on Render and verify live password reset email delivery to a controlled inbox + `EmailDeliveryLog.status == 'SENT'`. |
| **C. Native `pg_dump` / `pg_restore` Certification** | Encrypted JSON DR passed earlier (`28,985` records, `0` errors, RTO `240.468s`), whereas native binary `PGDMP` DR lacked PostgreSQL client binaries on Windows. | On an isolated Linux/CI host with PostgreSQL 18 client tools:<br>`pg_dump -Fc --no-owner "$STAGING_DB_URL" -f staging.dump`<br>`createdb "$DR_SCRATCH_DB_URL"` (isolated scratch DB — never `neondb` or `neondb_staging`)<br>`pg_restore --no-owner --single-transaction -d "$DR_SCRATCH_DB_URL" staging.dump`<br>Verify row counts, Balance Sheet parity (`0.00`), `AuditLog` hash chain, and record RPO/RTO. |
| **D. Seven-Day Live Operational Soak** | Not started (`workers_online=0`). | Once Redis, Worker, Beat, and SMTP are live on staging for 7 consecutive days, record continuous health checks, outbox sweep completion, email retry recovery, zero cross-tenant leakage, and Balance Sheet equilibrium across synthetic traffic. |
