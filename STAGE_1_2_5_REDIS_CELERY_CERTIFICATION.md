# SRI LEKH — STAGE 1.2.5 REDIS & CELERY ASYNC WORKER CERTIFICATION

**Assessment Date:** 2026-11-12  
**Branch / Commit:** `feat/google-play-launch-readiness` @ `c160fca0`  
**Overall Gate Verdict (Gate E — Async Queue Readiness):** **PARTIALLY VERIFIED / STAGING INFRA BLOCKED** *(Live Redis 7 + real non-eager Celery worker roundtrip proved in Cloud CI; live Render staging remains on Free tier without Redis/Worker/Beat services)*

---

## 1. Live Redis 7 + Celery Worker Certification (Cloud CI Evidence)

In Stage 1.2.4, Celery tasks had only been exercised in `CELERY_TASK_ALWAYS_EAGER=True` mode or via SQLite/PG model simulation because local Windows lacked `redis-server`. In Stage 1.2.5, Cloud CI Job `131328026519` (`Run #43259891989`, Step 9 `Verify Live Redis 7 & Celery Worker Roundtrip` on `c160fca0`) verified real asynchronous broker execution:

- **Broker Service:** `redis:7-alpine` (`Redis 7.4.12`, port `6379`)
- **Configuration:** `ENVIRONMENT=staging`, `DEBUG=False`, `CELERY_TASK_ALWAYS_EAGER=False`, backed by `PostgreSQL 18.6` (`neondb_ci_staging`)
- **Observed Worker Proof:**
  1. Launched detached worker: `celery -A config worker --loglevel=info --concurrency=1 --detach`
  2. `redis.from_url(REDIS_URL).ping()` -> **`True`**
  3. `celery_app.control.inspect(timeout=5).stats()` -> Detected active worker **`['celery@runnervmwuk1x']`**
  4. Dispatched `retry_pending_outbox_events_task.delay()` asynchronously over Redis -> `.get(timeout=15)` completed cleanly (`CI_OUTBOX_TASK_RESULT: None`, **exit `0`**, step `completed success`)

---

## 2. Live Render Staging Infrastructure Posture (`https://vouch-u3u7.onrender.com`)

Probing `GET https://vouch-u3u7.onrender.com/api/v1/health/environment/` returned:
- `redis`: `{"configured": true, "status": "unreachable"}`
- `celery`: `{"beat_schedule_configured": true, "beat_schedule_active": false, "outbox_sweeper_interval_seconds": 60, "workers_online": 0, "task_always_eager": false, "acks_late": true}`

As documented in [`render.yaml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/render.yaml#L1-L60), `vouch-staging-worker` and `vouch-staging-beat` require paid Render Starter+ worker instances (unavailable on Free tier) plus a managed Redis URL.

---

## 3. Remaining Owner Actions (`OA-05`)

1. Provision managed TLS Redis (`rediss://...` e.g. Upstash or Render Key Value) and set `REDIS_URL` on Render web, worker, and beat services.
2. Deploy `vouch-staging-worker` and **exactly 1** `vouch-staging-beat` instance per [`render.yaml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/render.yaml#L26-L60).
3. Confirm `GET /api/v1/health/environment/` reports `redis.status == "ok"`, `workers_online >= 1`, and `beat_schedule_active == true`.
