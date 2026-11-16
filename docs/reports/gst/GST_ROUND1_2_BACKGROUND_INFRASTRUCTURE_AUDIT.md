# SriLekh — GST Round 1.2 Background Infrastructure Audit (Redis & Celery)

## 1. Executive Summary

This audit investigates the background processing infrastructure on SriLekh's Render staging environment.

The staging health endpoint currently reports:
```json
{
  "redis": {
    "configured": true,
    "status": "unreachable"
  },
  "celery": {
    "beat_schedule_configured": true,
    "beat_schedule_active": false,
    "outbox_sweeper_interval_seconds": 60,
    "workers_online": 0,
    "task_always_eager": false,
    "acks_late": true
  }
}
```

---

## 2. Infrastructure Investigation & Root Cause

### Root Cause on Render Free Tier
1. **Render Free Tier Limitations**:
   - Render's Free tier provides only Web Services with auto-spin-down upon 15 minutes of inactivity.
   - Background Workers (`celery worker` and `celery beat`) and persistent managed Redis cannot run on the Render Free tier (they require Render's paid Starter tier at \$7/month per service).
2. **Current Service Topology**:
   - `render.yaml` defines a blueprint with `vouch-staging-worker` and `vouch-staging-beat`. However, without a paid instance credit, Render cannot boot worker containers.
   - The web container defines `REDIS_URL` pointing to an internal Redis hostname that is not provisioned or active on the free tier.

---

## 3. Dependency Analysis: Does GST Depend on Redis / Celery?

| Capability in SriLekh | Depends on Celery / Redis? | Operational Impact |
| :--- | :---: | :--- |
| **GSTIN Verification (Sandbox)** | **NO (100% Synchronous)** | **Zero impact**. Executes synchronous HTTP request to Sandbox API with sub-millisecond local caching in PostgreSQL (`GSTTaxpayerCache`). |
| **Party Master Enrichment** | **NO (100% Synchronous)** | **Zero impact**. Updates party metadata directly in PostgreSQL transaction. |
| **Multi-GSTIN Management** | **NO (100% Synchronous)** | **Zero impact**. Standard Django ORM operations on `GSTRegistration`. |
| **Outbox Invoice Email Sweeper** | **YES (Async Task)** | When Celery is offline, outbox events queue in `notifications_outboxevent` table and are processed when workers come online or via manual management command (`python manage.py process_outbox`). |
| **Nightly Disaster Recovery Backup**| **YES (Celery Beat)** | Scheduled at 02:00 AM IST. Backups can also be triggered manually via `python manage.py backup_database`. |

---

## 4. Staging Remediation: In-Process Eager Mode

To eliminate the "unreachable Redis" dependency on staging without incurring unnecessary provider costs:

1. **Enable Eager Execution for Staging**:
   In `config/settings.py`:
   ```python
   # In development or staging without a paid Redis broker, allow in-process eager execution
   CELERY_TASK_ALWAYS_EAGER = env.bool(
       'CELERY_TASK_ALWAYS_EAGER',
       default=(DEBUG or ENVIRONMENT == 'staging' or not env.str('REDIS_URL', default=''))
   )
   ```
2. **Provider Cost Estimate for Full Production Redis/Celery**:
   If the business owner chooses to run dedicated background processes on Render:
   - 1x Render Redis (256 MB): \$7.00 / month
   - 1x Render Background Worker (`celery worker`): \$7.00 / month
   - 1x Render Background Worker (`celery beat`): \$7.00 / month
   - **Total Estimated Cost**: ~\$21.00 / month.

---

## 5. Audit Verdict

- **GSTIN & Multi-GSTIN Independence**: **PASS** (Zero dependency on Celery/Redis).
- **Background Worker Status**: **BLOCKED (Requires Paid Tier or Eager Mode)** for staging.
