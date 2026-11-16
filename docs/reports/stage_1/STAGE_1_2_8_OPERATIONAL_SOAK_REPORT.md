# SRI LEKH — STAGE 1.2.8 OPERATIONAL SOAK PROTOCOL & RELIABILITY REPORT

**Assessment Date:** 2026-11-13  
**Target Environment:** Staging (`https://vouch-u3u7.onrender.com` / `fix/stage4-12-day6-remediation`)  
**Target Duration:** 168 Continuous Hours (7 Days)  
**Accumulated Duration:** **0 of 168 Hours**  
**Certification Verdict:** **BLOCKED PENDING PREREQUISITE INFRASTRUCTURE (OA-08)**  

---

## 1. Executive Summary

A continuous 7-day (168-hour) operational soak test in the staging environment is a mandatory quality gate designed to prove that long-running system daemons maintain operational integrity under persistent execution.

Specific operational failure modes tested by the soak include:
- Gunicorn or Celery worker process memory growth (detecting uncollected task objects).
- Outbox sweeper queue stalls (detecting transactions stuck in `PROCESSING` status).
- Redis broker reconnection recovery after network timeouts.
- Database connection pool exhaustion.
- Tamper-evident cryptographic audit chain integrity.

As documented in Stage 1.2.6 and reaffirmed in Stage 1.2.8, **0 hours of the 168-hour soak have accumulated**. Soak duration cannot be simulated or fabricated.

This report establishes the prerequisite blockers that prevent timer initiation, the daily telemetry tracking framework, and the formal exit criteria.

---

## 2. Root Blockers Preventing Soak Clock Initiation

The 168-hour soak cannot begin until the staging infrastructure is live and operational:

1. **Managed Redis & Celery Background Workers (OA-05):**
   - The staging environment currently runs on Render Free tier, where Celery Worker and Beat are not running, and Redis is unreachable.
   - Without a 24/7 Celery Beat scheduler and asynchronous worker, periodic outbox sweeps and background retries cannot run continuously.
2. **SMTP Relay Configuration (OA-06):**
   - Transactional email dispatch queues cannot be soaked without authenticating SMTP credentials.
3. **Staging Frontend Public Access (OA-09):**
   - Automated synthetic client load cannot hit preview deployments while the Vercel SSO login wall blocks headless test agents.

---

## 3. The 168-Hour Daily Monitoring Protocol

Once OA-05, OA-06, and OA-09 are online, an automated GitHub Actions cron workflow (`.github/workflows/daily-soak-monitor.yml`) or scheduled script will probe the staging stack every 24 hours:

```python
# daily_soak_probe.py
import requests, os, sys

HEALTH_URL = "https://vouch-u3u7.onrender.com/api/v1/health/environment/"
r = requests.get(HEALTH_URL, timeout=10)
health = r.json()

assert health["status"] == "healthy"
assert health["redis"]["status"] == "ok"
assert health["celery"]["workers_online"] >= 1
assert health["celery"]["beat_schedule_active"] is True
assert health["migrations"]["unapplied_count"] == 0
```

---

## 4. Daily Soak Telemetry Record (Day 1 through Day 7)

| Soak Day | Target Cumulative Hours | Worker RSS Memory (MB) | Web Service RSS Memory (MB) | Redis Heartbeat Status | Stuck Outbox Rows (`PROCESSING`) | Dead Letter Outbox Events | Audit Hash Chain Status | Daily Verification Result |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Day 1** | `24 / 168 hrs` | *Pending OA-05* | *Pending OA-05* | *Pending* | `0` | `0` | *Pending* | Not Started |
| **Day 2** | `48 / 168 hrs` | *Pending OA-05* | *Pending OA-05* | *Pending* | `0` | `0` | *Pending* | Not Started |
| **Day 3** | `72 / 168 hrs` | *Pending OA-05* | *Pending OA-05* | *Pending* | `0` | `0` | *Pending* | Not Started |
| **Day 4** | `96 / 168 hrs` | *Pending OA-05* | *Pending OA-05* | *Pending* | `0` | `0` | *Pending* | Not Started |
| **Day 5** | `120 / 168 hrs` | *Pending OA-05* | *Pending OA-05* | *Pending* | `0` | `0` | *Pending* | Not Started |
| **Day 6** | `144 / 168 hrs` | *Pending OA-05* | *Pending OA-05* | *Pending* | `0` | `0` | *Pending* | Not Started |
| **Day 7** | `168 / 168 hrs` | *Pending OA-05* | *Pending OA-05* | *Pending* | `0` | `0` | *Pending* | Not Started |

---

## 5. Formal Soak Gate Exit Criteria for Gate E Transition

To certify closure of **OA-08** and transition Gate E to **PASS**:
1. Full 168 continuous hours elapsed without manual intervention or process crashes.
2. Celery worker RSS memory remains bounded (< 350 MB) through `max-tasks-per-child=100` recycling.
3. Total outbox items stuck in `PROCESSING` status for longer than 5 minutes equals `0`.
4. Total financial variance across all active staging test companies equals `₹0.00`.
5. Cryptographic `AuditLog` hash chains confirm zero unauthorized tamper corruption across all 7 staging companies.
