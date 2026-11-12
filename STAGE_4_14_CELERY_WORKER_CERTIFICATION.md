# SRI LEKH — STAGE 4.14 CELERY WORKER & OUTBOX CERTIFICATION

**Environment:** Live Render Staging (`https://vouch-u3u7.onrender.com`) + PostgreSQL Test DB (`test_neondb_staging`, fingerprint `6f4741bdaaf4`)  
**Commit SHA Tested:** `990a13bd` (`fix/stage4-12-day6-remediation`) + [tests_stage4_14_certification.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/tests_stage4_14_certification.py)  
**Database Fingerprint:** `6f4741bdaaf4`  
**Execution Timestamp:** `2026-11-12 13:54–14:04 IST`

---

## Executive Certification Finding: **`FAIL` LIVE ON RENDER / `PASS` IN CODE & POSTGRESQL SIMULATION**

Per Stage 4.14 certification standards ("Never claim a worker is operational without observing actual task execution"), **live Celery background processing on Render staging is NOT operational (`FAIL`)**. All Celery/Outbox logic, task autodiscovery, acks/retry settings, and all 10 resilience scenarios are **verified at code + PostgreSQL transaction level (`7/7` tests `OK`)**, while live Render lacks Redis and active worker/beat dynos.

---

## 1. Configuration Inspection & Hardening Applied (`990a13b`)

- **[Procfile](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/Procfile):** Added `worker` (`celery -A config worker --loglevel=info --concurrency=2 --prefetch-multiplier=1 --max-tasks-per-child=100`) and single-instance `beat` (`celery -A config beat --loglevel=info --pidfile=/tmp/celerybeat.pid --schedule=/tmp/celerybeat-schedule`) alongside `web`.
- **[render.yaml](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/render.yaml):** Defined `vouch-staging-api` (`web`), `vouch-staging-worker` (`worker`), and `vouch-staging-beat` (`worker`), explicitly noting Render Background Workers require Starter+ paid plans.
- **[config/settings.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/settings.py):** Configured `CELERY_TASK_ACKS_LATE = True`, `CELERY_TASK_REJECT_ON_WORKER_LOST = True`, `CELERY_WORKER_PREFETCH_MULTIPLIER = 1`, `CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True`, `CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True`, `CELERY_TASK_TRACK_STARTED = True`, `CELERY_TASK_SOFT_TIME_LIMIT = 120`, `CELERY_TASK_TIME_LIMIT = 180`, `CELERY_BROKER_TRANSPORT_OPTIONS`, and `rediss://` TLS handling.
- **[apps/notifications/tasks.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/tasks.py):** Updated `@shared_task(bind=True, acks_late=True, max_retries=3, default_retry_delay=60)` on `process_outbox_event_task` and `@shared_task(acks_late=True, ignore_result=True)` on `retry_pending_outbox_events_task`.
- **[config/environment_guard.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/environment_guard.py):** Removed hardcoded fake `"status": "active"` / `"beat_schedule_active": True`; replaced with real `redis.ping(timeout=0.5)` and `celery_app.control.inspect(timeout=0.5).ping()` telemetry.

---

## 2. Live Render Broker & Worker Evidence (`https://vouch-u3u7.onrender.com`)

- **Procedure:** `GET https://vouch-u3u7.onrender.com/api/v1/health/environment/`
- **Expected Outcome (for worker-ready cert):** `redis.status == "active"`, `workers_online >= 1`, `beat_schedule_active == true`.
- **Actual Outcome:**
  ```json
  "redis": { "configured": true, "status": "unreachable" },
  "celery": {
    "beat_schedule_configured": true,
    "beat_schedule_active": false,
    "outbox_sweeper_interval_seconds": 60,
    "workers_online": 0,
    "task_always_eager": false,
    "acks_late": true
  }
  ```
- **Pass/Fail:** **FAIL** (No Redis broker reachable and 0 workers online on Render).

---

## 3. Code-Level & PostgreSQL Outbox Scenario Verification (Scenarios 1–10)

Command run on `test_neondb_staging`:
`python manage.py test apps.accounting.tests_stage4_14_certification --settings=config.settings_test_pg --keepdb --verbosity=2`

- **Expected Outcome:** All 7 tests covering Celery autodiscovery/settings and Outbox Scenarios 1–10 pass without duplicate sends or accounting mutations.
- **Actual Outcome:** **7 / 7 `OK`** (run combined with Stage 4.13 suite: `11 / 11 OK` in `183.462s`, `0` failures, `0` skipped).

| Scenario (Section 5) | Test Method | Verified Behavior | Result |
|---|---|---|---|
| Autodiscovery & Config | `test_01_celery_autodiscovery_and_reliability_settings` | All `7` tasks discovered; `2` Beat entries (`nightly-disaster-recovery-backup`, `sweep-and-retry-outbox-notifications`); `acks_late=True`, `reject_on_worker_lost=True`, `prefetch=1` | **PASS** |
| 1 & 7: Valid Recipient + Duplicate Dispatch | `test_02_valid_recipient_and_duplicate_dispatch_idempotency` | `PROCESSED`, 1 `EmailDeliveryLog SENT`, second call short-circuits idempotently, 0 extra vouchers/entries | **PASS** |
| 2: Missing Recipient | `test_03_missing_recipient_skips_safely_preserving_voucher` | Safely transitions to `SKIPPED` (`EmailDeliveryLog SKIPPED`); `Voucher.status` stays `POSTED` & accessible | **PASS** |
| 3: Invalid Payload | `test_04_invalid_payload_transitions_to_dead_letter` | Non-dict list payload & missing voucher UUID transition to `DEAD_LETTER` | **PASS** |
| 4, 5, 6: Active Lease, Crash/Restart, Expired Lease, `DELIVERY_UNKNOWN` | `test_05_worker_interruption_active_lease_and_restart_expired_lease_recovery` | Active unexpired lease suppresses duplicate (`False`); expired lease + `SENT` advances to `PROCESSED`; expired lease + no send moves to `RETRY_PENDING`; `DELIVERY_UNKNOWN` halts auto-retry | **PASS** |
| 8 & 9: Temporary Failure Retry + Permanent `DEAD_LETTER` | `test_06_temporary_failure_retries_and_recovers_while_permanent_dead_letters` | Transient `421` failure sets `RETRY_PENDING`, retry succeeds `PROCESSED`; `max_retries` `SMTPException` sets `DEAD_LETTER` | **PASS** |
| 10: Concurrent Workers | `Stage414ConcurrentOutboxWorkerTests.test_concurrent_workers_send_exactly_once` | 2 concurrent PostgreSQL threads via `ThreadPoolExecutor` produce `send_count == 1` & `SENT == 1` | **PASS** |

---

## Remaining Limitations

1. Live Redis + Render Worker + single-instance Beat must be provisioned (paid Starter+ Render instances or external Redis + cron/worker) and observed executing `retry_pending_outbox_events_task` on staging before live worker certification can pass.
2. Local Docker Desktop daemon was not running, so live multi-process Redis broker execution was verified via PostgreSQL concurrency locks rather than a live Redis daemon.
