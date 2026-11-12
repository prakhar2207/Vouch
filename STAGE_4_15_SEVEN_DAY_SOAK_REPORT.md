# SRI LEKH — STAGE 4.15 SEVEN-DAY OPERATIONAL SOAK REPORT

**Environment:** `https://vouch-u3u7.onrender.com` & `neondb_staging`  
**Live Commit SHA:** `c15a64fb` (`fix/stage4-12-day6-remediation`)  
**Database Fingerprint:** `6f4741bdaaf4` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`, `Maa Annapurna Belting Store` absent)  
**Observation Timestamp:** `2026-11-12 13:55–14:45 IST`

---

## Verdict: **NOT STARTED / BLOCKED ON LIVE WORKER INFRASTRUCTURE**

Per Stage 4.15 Rules 11–12 ("A seven-day continuous soak must begin only after Redis, Worker and Beat are operational. Do not claim a seven-day soak from point-in-time checks"), the mandatory 7-day continuous live worker-enabled soak has **not yet begun** because Redis, Celery Worker, and Celery Beat are offline on Render staging (`redis.status: "unreachable"`, `workers_online: 0`, `beat_schedule_active: false`).

---

## 1. Pre-Soak Entry Telemetry Baseline (`2026-11-12`)

| Monitoring Dimension | Observed Metric | Readiness for Soak Entry |
|---|---|---|
| Staging Web API (`vouch-u3u7` @ `c15a64fb`) | `HTTP 200` healthy, `environment: "staging"`, `unapplied_count: 0` | **READY** *(Free-tier idle spin-down causes ~44s cold wake)* |
| Managed Staging Redis | `"redis": {"configured": true, "status": "unreachable"}` | **BLOCKED** |
| Celery Worker / Beat Scheduler | `"workers_online": 0`, `"beat_schedule_active": false` | **BLOCKED** |
| Outbox Queue Baseline | `0 PENDING`, `9` historical synthetic `DEAD_LETTER`, `0` duplicate sends | **READY** |
| DB Connections (`pg_stat_activity`) | `1` active connection during snapshot check | **READY** |
| Accounting Global Invariants | `0` zero-entry posted, `0` unbalanced posted, `0` orphan entries, `0` negative/over-allocated FIFO invoices | **READY** |
| Notification Auth Security (`c15a64fb`) | Live Render `200` own / `403` cross-tenant / `404` unknown / `400` malformed / `403` `VIEWER` verified | **READY** |

---

## 2. Five-Tenant Cohort Baseline Census (`auto_reconcile=False`)

| Tenant | Vouchers (`POST/DRF/REV`) | TB Dr == Cr (Rs) | BS Balanced (`Assets`, Rs) | `TB == PTB` | Drifts | `AuditLog` / Chain Breaks | Outbox (`PROC/SKIP/DL`) | Email (`SENT/SKIP`) |
|---|---:|---:|---:|---|---:|---:|---|---|
| `Garodia Bearing & Power Transmission` | `62 / 1 / 0` | `678,241.20` | `True` (`849,310.20`) | `True` | `0` | `73 / 0` | `55 / 1 / 0` | `55 / 1` |
| `Precision Agro Tools Pvt Ltd` | `523 / 11 / 0` | `1,694,738.70` | `True` (`1,845,954.26`) | `True` | `0` | `559 / 0` | `82 / 391 / 9` | `82 / 391` |
| `Shree Radhe Industrial Hardware` | `60 / 0 / 0` | `505,813.79` | `True` (`672,482.00`) | `True` | `0` | `68 / 0` | `54 / 0 / 0` | `54 / 0` |
| `Staging Beta Engineering Supplies Ltd` | `42 / 0 / 4` | `287,835.00` | `True` (`417,193.00`) | `True` | `0` | `52 / 0` | `36 / 0 / 0` | `36 / 0` |
| `Staging MSME Alpha Belts Pvt Ltd` | `444 / 92 / 7` | `831,328.66` | `True` (`947,429.66`) | `True` | `0` | `468 / 0` | `376 / 5 / 0` | `376 / 5` |

*Day 1–Day 7 daily uptime/worker/beat/outbox tracking rows remain pending until live Render Redis + Worker + Beat are provisioned.*
