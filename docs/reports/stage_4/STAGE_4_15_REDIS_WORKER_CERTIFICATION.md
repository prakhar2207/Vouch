# SRI LEKH — STAGE 4.15 REDIS, CELERY WORKER & BEAT CERTIFICATION

**Environment:** Live Render Staging (`https://vouch-u3u7.onrender.com`) + Local Host Inspection  
**Live Commit SHA:** `c15a64fb` (`fix/stage4-12-day6-remediation`)  
**Database Fingerprint:** `6f4741bdaaf4` (`neondb_staging`, `ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`)  
**Execution Timestamp:** `2026-11-12 12:39–14:45 IST`

---

## Verdict: **FAIL / BLOCKED FOR PRODUCTION PROMOTION (External Redis & Paid Render Worker/Beat Required)**

Per Stage 4.15 Rules 8–10, neither Redis nor Celery Worker nor Celery Beat may be marked operational without live broker PING, online worker inspection, and observed real scheduled task execution.

---

## 1. Configuration Inspection

- **[config/settings.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/settings.py):**
  - `CELERY_BROKER_URL = env('REDIS_URL', default='redis://127.0.0.1:6379/0')`
  - Reliability flags verified active (`990a13b` / `c15a64fb`): `CELERY_TASK_ACKS_LATE = True`, `CELERY_TASK_REJECT_ON_WORKER_LOST = True`, `CELERY_WORKER_PREFETCH_MULTIPLIER = 1`, `CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True`, `CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True`, `CELERY_TASK_TRACK_STARTED = True`, `CELERY_TASK_SOFT_TIME_LIMIT = 120`, `CELERY_TASK_TIME_LIMIT = 180`, `CELERY_BROKER_TRANSPORT_OPTIONS` (`visibility_timeout: 1800`, `health_check_interval: 30`, `socket_keepalive: True`), and automatic `rediss://` TLS `CELERY_BROKER_USE_SSL`.
  - `CELERY_BEAT_SCHEDULE`: `nightly-disaster-recovery-backup` (`crontab(hour=20, minute=30)` UTC / `02:00 AM IST`) and `sweep-and-retry-outbox-notifications` (`60.0s`, `expires=55.0`).
- **[config/celery.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/celery.py):** Initializes `Celery('backend')`, loads `CELERY_` namespace, calls `autodiscover_tasks()` (`7` tasks discovered across `apps.accounting.tasks` and `apps.notifications.tasks`).
- **[Procfile](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/Procfile) & [render.yaml](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/render.yaml):**
  - Web: `MALLOC_ARENA_MAX=2 gunicorn config.wsgi:application --workers 1 --threads 4 --timeout 180 --max-requests 500 --max-requests-jitter 50`
  - Worker: `MALLOC_ARENA_MAX=2 celery -A config worker --loglevel=info --concurrency=2 --prefetch-multiplier=1 --max-tasks-per-child=100`
  - Beat (single instance): `celery -A config beat --loglevel=info --pidfile=/tmp/celerybeat.pid --schedule=/tmp/celerybeat-schedule`

---

## 2. Live Redis & Render Telemetry Verification

| Check | Procedure / Command | Expected Result | Actual Result | Pass/Fail |
|---|---|---|---|---|
| Local Redis Broker Connectivity | `redis.from_url('redis://127.0.0.1:6379/0', socket_connect_timeout=2).ping()` | `True` (PONG) | `redis.exceptions.TimeoutError: Timeout connecting to server` | **FAIL** |
| Local Docker / Redis Service | `Get-Service -Name '*redis*','*docker*'` | Running Redis / Docker daemon | `com.docker.service: Stopped` (no Redis service installed) | **BLOCKED** |
| Live Render Staging Health Telemetry (`c15a64fb`) | `GET https://vouch-u3u7.onrender.com/api/v1/health/environment/` | `redis.status == "active"`, `workers_online >= 1`, `beat_schedule_active == true` | `"redis": {"configured": true, "status": "unreachable"}`, `"celery": {"beat_schedule_configured": true, "beat_schedule_active": false, "workers_online": 0, "task_always_eager": false, "acks_late": true}` | **FAIL** |
| Celery Task Autodiscovery | `app.loader.import_default_modules()` | `7` project tasks + `2` Beat schedules | Verified `7` tasks + `2` schedules | **PASS (Code)** |

---

## 3. Outbox Reliability Status (Code / DB vs Live Worker)

- Queue on `neondb_staging`: **`0` `PENDING`**, `9` historical synthetic `DEAD_LETTER` rows preserved, `0` duplicate email sends.
- All 10 Section 6 outbox scenarios remain verified at PostgreSQL level (`apps.accounting.tests_stage4_14_certification`: `7/7 OK` + `apps.notifications.tests`: `16/16 OK` in `task-50430`), proving lease enforcement, crash/expired-lease recovery, `DELIVERY_UNKNOWN` freeze, transient backoff retry, permanent dead-lettering, missing-recipient `SKIPPED` without affecting posted vouchers, and 2-thread PostgreSQL concurrent execution.

---

## External Provisioning Required Before Re-Test

1. Provision a dedicated staging TLS Redis instance (Render Key Value / Upstash) and set staging `REDIS_URL` (separate from production).
2. Provision paid Starter+ Render services for `vouch-staging-worker` and single-instance `vouch-staging-beat` using [render.yaml](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/render.yaml).
3. Observe `/api/v1/health/environment/` reporting `redis.status == "active"`, `workers_online >= 1`, `beat_schedule_active == true`, plus real live task IDs & Beat sweep execution logs.
