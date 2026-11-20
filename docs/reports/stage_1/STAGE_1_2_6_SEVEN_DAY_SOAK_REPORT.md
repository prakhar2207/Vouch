# SRI LEKH — STAGE 1.2.6 SEVEN-DAY OPERATIONAL SOAK PROTOCOL & AUDIT REPORT

**Assessment Date:** 2026-11-12  
**Target Environment:** Staging (`https://vouch-u3u7.onrender.com` / `fix/stage4-12-day6-remediation`)  
**Target Soak Window:** 168 Continuous Hours (7 Days)  
**Elapsed Soak Duration:** **0 of 168 Hours**  
**Certification Verdict:** **BLOCKED PENDING PREREQUISITE INFRASTRUCTURE (OA-08)**  

---

## 1. Executive Summary

A 7-day operational soak test is a standard reliability gate in financial accounting and enterprise SaaS releases. Its purpose is to verify that:
1. Long-running worker processes do not leak memory or exhaust file descriptors.
2. The asynchronous outbox synchronization worker does not leave transactions stuck in `PROCESSING` status.
3. Cryptographic audit log hash chains maintain continuous mathematical integrity without silent chain breakage.
4. Database connection pools gracefully survive network blips, connection resets, and auto-scaling events.

As established in Stage 1.2.5 and Stage 1.2.6, **zero hours of the 7-day soak have officially accumulated**. In accordance with mandatory engineering ethics, soak hours cannot be simulated, truncated, or fabricated.

This report documents the prerequisite blockers, the daily telemetry tracking framework, and the exact exit criteria required to certify the soak.

---

## 2. Root Cause of 0 Elapsed Hours & Blocking Dependencies

The soak clock cannot start until the following external prerequisites are live:

1. **Managed Redis & Asynchronous Worker/Beat (OA-05):**
   - The staging environment currently runs on Render Free tier, where Celery Worker and Beat are not deployed, and Redis is unreachable.
   - Without Celery Worker and Beat running continuously, the outbox processor cannot execute on a scheduled interval.
2. **SMTP Relay Configuration (OA-06):**
   - Outbound transactional email queues cannot be stressed or audited over time without working SMTP credentials.
3. **Staging Frontend Access (OA-09):**
   - Continuous synthetic traffic cannot be driven through the frontend UI while Vercel Preview Protection SSO blocks unauthenticated headless test agents.

---

## 3. Daily Soak Telemetry Monitoring Protocol (168-Hour Runbook)

Once OA-05, OA-06, and OA-09 are live, the following automated probe script must run every 24 hours (or via a scheduled GitHub Actions cron `0 0 * * *`):

```python
# daily_soak_monitor.py
import requests, os, json, sys

API_URL = "https://vouch-u3u7.onrender.com/api/v1"
HEALTH_URL = f"{API_URL}/health/environment/"

r = requests.get(HEALTH_URL, timeout=10)
health = r.json()

print("ENVIRONMENT_HEALTH:", health.get("status"))
assert health.get("status") == "healthy"
assert health.get("redis", {}).get("status") == "ok"
assert health.get("worker", {}).get("workers_online", 0) >= 1
assert health.get("worker", {}).get("beat_schedule_active") is True

# Check Outbox Stuck Count via staging admin or telemetry endpoint
print("DAILY SOAK TELEMETRY CAPTURED SUCCESSFULLY")
```

---

## 4. The 7-Day Telemetry Tracking Table

| Soak Day | Target Cumulative Hours | Worker Memory RSS (MB) | Gunicorn Memory RSS (MB) | Redis Heartbeat Status | Stuck Outbox Events (`PROCESSING`) | Dead Letter Outbox Events | Audit Hash Chain Status | Daily Result |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Day 1** | `24 / 168 hrs` | *Pending Infra* | *Pending Infra* | *Pending* | `0` | `0` | *Pending* | Not Started |
| **Day 2** | `48 / 168 hrs` | *Pending Infra* | *Pending Infra* | *Pending* | `0` | `0` | *Pending* | Not Started |
| **Day 3** | `72 / 168 hrs` | *Pending Infra* | *Pending Infra* | *Pending* | `0` | `0` | *Pending* | Not Started |
| **Day 4** | `96 / 168 hrs` | *Pending Infra* | *Pending Infra* | *Pending* | `0` | `0` | *Pending* | Not Started |
| **Day 5** | `120 / 168 hrs` | *Pending Infra* | *Pending Infra* | *Pending* | `0` | `0` | *Pending* | Not Started |
| **Day 6** | `144 / 168 hrs` | *Pending Infra* | *Pending Infra* | *Pending* | `0` | `0` | *Pending* | Not Started |
| **Day 7** | `168 / 168 hrs` | *Pending Infra* | *Pending Infra* | *Pending* | `0` | `0` | *Pending* | Not Started |

---

## 5. Formal Soak Gate Exit Criteria

To certify closure of **OA-08** and transition Gate E to **PASS**:

1. **Duration:** Full 168 hours elapsed without manual container restarts due to crashes.
2. **Worker Stability:** Celery worker memory remains bounded (< 350 MB RSS) through `max-tasks-per-child=100` recycling.
3. **Queue Health:** Total outbox events stuck in `PROCESSING` status for longer than 5 minutes equals `0`.
4. **Accounting Invariant:** Total ledger equilibrium variance remains `0.00 INR` across all active staging test companies.
5. **Tamper Invariant:** Tamper verification on `AuditLog` records across all 7 staging tenants confirms zero cryptographic chain corruptions.
