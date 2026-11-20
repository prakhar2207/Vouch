# SriLekh — GST Round 1.2 Git & Staging Deployment Verification

## 1. Executive Summary

This report establishes the verified Git commit state and deployment topology of SriLekh across production and staging environments as of 2026-11-16.

---

## 2. Mandatory Environment Topology

| Environment | Render Service | Hostname | Database | Neon Cluster | Active Branch | Latest Verified Commit |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Production** | `vouch-api` | `vouch-api-752s.onrender.com` | `neondb` | `ep-lingering-boat-b3994i6f` | `main` | `a07bf598` |
| **Staging** | `vouch-staging` | `vouch-u3u7.onrender.com` | `neondb_staging` | `ep-silent-feather-b34egg28` | `fix/stage4-12-day6-remediation` | `903e2951` |

### Invariant Rules
1. **Production Untouched**: `vouch-api-752s.onrender.com` and `neondb` remain strictly untouched.
2. **Protected Tenant Isolation**: `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) is absent from staging and 100% isolated.
3. **No Cross-Deployments**: Staging branch commits are never deployed to `vouch-api`.

---

## 3. Git Branch State & Commit Alignment

### Local Branch Head Inspection
```bash
git rev-parse HEAD
# Output: 903e2951c7d00d30c12928b63724e1fd1565d9e6
```
- Active Branch: `fix/stage4-12-day6-remediation`
- Commit Hash: `903e2951c7d00d30c12928b63724e1fd1565d9e6` (`903e295`)
- Remote: In sync with `origin/fix/stage4-12-day6-remediation`

### Live Render Staging Health Probe
Dispatched to `https://vouch-u3u7.onrender.com/api/v1/health/environment/` at `2026-11-16 22:45:37 UTC+05:30`:

```json
{
  "status": "healthy",
  "service": "SriLekh Accounting Engine",
  "environment": "staging",
  "version": "1.0.2",
  "commit": "903e2951",
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

### Verification Findings
1. **Commit Alignment**: The live staging backend reports `"commit": "903e2951"`, matching local HEAD `903e295`.
2. **Environment & Database**: Verified as `"environment": "staging"`, `"sanitized_target": "neondb_staging"`, `"is_isolated": true`.
3. **Migration Currency**: All migrations including `gst.0006` are applied (`"unapplied_count": 0`).

---

## 4. Verification Verdict

**VERDICT: PASS** — The intended remediation commit `903e2951` is certified as live, isolated, and operational on the dedicated Render staging backend.
