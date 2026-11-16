# SriLekh — GST Round 1.1 Render Staging Deployment Report

## 1. Executive Summary

This report delivers the root cause investigation of the Render build failure displayed in the user's dashboard screenshot, confirms the live status of the dedicated staging deployment, and provides instructions for production vs. staging service topology.

---

## 2. Root Cause Analysis: The 52.8s Build Failure on `vouch-api`

### Context from Dashboard Screenshot
- **Service Name**: `vouch-api` (`srv-dsbgvah5efls73ao02cg`)
- **Render Service URL**: `https://vouch-api-752s.onrender.com`
- **Dashboard Breadcrumb**: `My Workspace > Vouch > Production > vouch-api > Deploys`
- **Attempted Commit**: `990a13b` on branch `fix/stage4-12-day6-remediation`
- **Failure Duration**: 52.8 seconds
- **Render Build Error Log**:
  ```
  01:24:19 PM Traceback (most recent call last):
  ...
  File "/opt/render/project/src/config/settings.py", line 185, in <module>
    validate_environment_database_isolation(
  File "/opt/render/project/src/config/environment_guard.py", line 70, in validate_environment_database_isolation
    raise ImproperlyConfigured(
  django.core.exceptions.ImproperlyConfigured: FATAL ISOLATION DEFECT: Environment is configured as 'staging', 
  but database name is 'neondb' (production target). Staging backend MUST connect to a dedicated staging 
  database (e.g., 'neondb_staging'). Refusing to start.
  ==> Build failed 😞
  ```

### Forensic Finding
1. **The Service is Production**: `vouch-api` (`https://vouch-api-752s.onrender.com`) is configured with the Neon production database `neondb`.
2. **The Blueprint Conflict**: Commit `990a13b` added `render.yaml`, defining `ENVIRONMENT: staging`.
3. **The Fail-Closed Safety Intercept**: When Render attempted to build the staging branch on this production service, `build.sh` executed `python manage.py collectstatic --no-input`. Django loaded `config.settings`, which invoked SriLekh’s strict `environment_guard.py`.
4. **Disaster Averted**: The guard detected that a service claiming to be `staging` was pointing to the production database `neondb`. To prevent staging migrations from executing against production data, the guard aborted startup immediately.
5. **Rollback State**: Render retained the previous operational deployment: `vouch-api-752s.onrender.com` is actively serving commit `a07bf598` (`main` branch) in `production` mode against `neondb`.

---

## 3. Live Staging Service Status (`vouch-u3u7.onrender.com`)

The dedicated staging service is `https://vouch-u3u7.onrender.com`.

### Live Verification Probe
A probe against `https://vouch-u3u7.onrender.com/api/v1/health/environment/` was executed at `2026-11-16 21:36:58 UTC+05:30`:

```json
{
  "status": "healthy",
  "service": "SriLekh Accounting Engine",
  "environment": "staging",
  "version": "1.0.2",
  "commit": "8adc8da2",
  "database": {
    "engine": "postgresql",
    "sanitized_target": "neondb_staging",
    "identity_fingerprint": "6f4741bdaaf4",
    "is_isolated": true
  },
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
  },
  "migrations": {
    "status": "up_to_date",
    "unapplied_count": 0
  }
}
```

### Staging Verification Facts
- **Active Commit**: `8adc8da2` (Round 1 commit is **LIVE on staging**).
- **Target Database**: `neondb_staging` on cluster `ep-silent-feather-b34egg28`.
- **Database Isolation**: `is_isolated: true`.
- **Migrations**: `up_to_date`, 0 unapplied.
- **Service Health**: `healthy` (HTTP 200).

---

## 4. Owner Actions & Render Topology Recommendations

1. **For Production Service (`vouch-api`)**:
   - In Render Dashboard $\rightarrow$ `vouch-api` $\rightarrow$ **Settings**:
   - Verify that **Branch** is set to `main` (not `fix/stage4-12-day6-remediation`).
   - Do not deploy staging branches to this service.

2. **For Staging Service (`vouch-u3u7`)**:
   - In Render Dashboard $\rightarrow$ `vouch-staging` (`vouch-u3u7`):
   - Confirm **Branch** is set to `fix/stage4-12-day6-remediation`.
   - When deploying new commits, trigger **Manual Deploy** $\rightarrow$ **Deploy latest commit** on `vouch-u3u7`.

---

## 5. Deployment Verdict

**VERDICT: PASS** — The Round 1 code (`8adc8da2`) is verified as running live and healthy on the dedicated Render staging environment (`https://vouch-u3u7.onrender.com`).
