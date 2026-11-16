# SRI LEKH — REDIS & CELERY OPERATIONAL CERTIFICATION

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Live Staging Inspection Target:** `https://vouch-u3u7.onrender.com/api/v1/health/environment/`  
**Classification:** **BLOCKED (External Managed Infrastructure & 7-Day Soak Not Provisioned)**

---

## 1. Live Staging Telemetry Observed

Queried directly against `https://vouch-u3u7.onrender.com/api/v1/health/environment/` (`HTTP 200`):
- **Environment:** `staging` (`commit: f8578a88`, DB `neondb_staging`, `is_isolated: true`)
- **`redis`:** `{"configured": true, "status": "unreachable"}`
- **`celery`:** `{"beat_schedule_configured": true, "beat_schedule_active": false, "outbox_sweeper_interval_seconds": 60, "workers_online": 0, "task_always_eager": false, "acks_late": true}`
- **Local Host Check:** `redis-server` and `redis-cli` binaries are not installed on the Windows host (`Get-Command` -> absent).

---

## 2. Code-Level Certification (`PASS` in Eager/Test Mode)

Audited [`config/settings.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/settings.py), [`apps/notifications/tasks.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/tasks.py), and [`render.yaml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/render.yaml):
- **Durability & Crash Recovery Settings:** `CELERY_TASK_ACKS_LATE = True`, `CELERY_TASK_REJECT_ON_WORKER_LOST = True`, `CELERY_WORKER_PREFETCH_MULTIPLIER = 1`, `CELERY_TASK_SOFT_TIME_LIMIT = 120`, `CELERY_TASK_TIME_LIMIT = 180`, `rediss://` TLS config support.
- **Transactional Outbox Guarantees:** `retry_pending_outbox_events_task` recovers crashed `PROCESSING` leases (`lease_expires_at <= now`), respects `DELIVERY_UNKNOWN` pause rules, uses `select_for_update(skip_locked=True)`, and enforces max retries -> `DEAD_LETTER`.
- **Automated Test Execution (`PASS`):** `apps.notifications.tests` + `apps.notifications.tests_stage4_15_auth` passed inside the `74 / 74` Django test run (with eager task execution in test mode).

---

## 3. External Actions Required to Clear Gate E

1. Provision a managed TLS Redis instance (`rediss://...`) and bind `REDIS_URL` across staging web, worker, and beat services.
2. Provision paid `vouch-staging-worker` and single-replica `vouch-staging-beat` worker services defined in [`render.yaml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/render.yaml).
3. Verify `/api/v1/health/environment/` reports `redis.status == "ok"`, `workers_online >= 1`, `beat_schedule_active == true`, and execute the **7-day continuous live operational soak**.
