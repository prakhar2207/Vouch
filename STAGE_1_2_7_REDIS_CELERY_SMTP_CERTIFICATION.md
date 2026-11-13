# SRI LEKH — STAGE 1.2.7 ASYNCHRONOUS TASKS (REDIS & CELERY) & SMTP RELAY CERTIFICATION

**Assessment Date:** 2026-11-12  
**Target Environments:**  
- Staging API: `https://vouch-u3u7.onrender.com` (`fix/stage4-12-day6-remediation`)  
- Transactional Email Domain: `srilekh.com` (GoDaddy DNS Nameservers)  
**Certification Verdict:** **PARTIALLY VERIFIED IN CI / STAGING INFRASTRUCTURE BLOCKED (OA-05 & OA-06)**  

---

## 1. Executive Summary

This report certifies the asynchronous processing architecture (Redis broker, Celery worker, Celery beat scheduler, and transactional outbox sweeper) and the transactional email subsystem (SMTP relay, SPF, DKIM, and DMARC alignment).

### Key Status Summary:
1. **Asynchronous Architecture in CI:** **100% VERIFIED PASS.** GitHub Actions pipeline verified live `redis:7-alpine` container connectivity, detached Celery worker registration (`celery@runnervmwuk1x`), and asynchronous task execution (`ALWAYS_EAGER=False`).
2. **Live Render Staging Worker/Beat Status:** **BLOCKED BY PLAN TIER (OA-05).** The Render staging web service runs on the Free tier, where managed Redis is unreachable (`redis.status: "unreachable"`) and background worker processes (`vouch-staging-worker` and `vouch-staging-beat`) are not supported without a paid Starter instance.
3. **SMTP Relay & DNS Authentication Status:** **BLOCKED PENDING OWNER CREDENTIALS & DNS (OA-06).** Live DNS query revealed strict SPF `v=spf1 include:secureserver.net -all` and DMARC `p=quarantine`, while Django defaults to `smtp.gmail.com` with empty credentials.

---

## 2. Asynchronous Architecture & Live Diagnostics

### 2.1 Live Staging Endpoint Telemetry
Probing `https://vouch-u3u7.onrender.com/api/v1/health/environment/` on 2026-11-12:
```json
{
  "status": "healthy",
  "service": "SriLekh Accounting Engine",
  "environment": "staging",
  "version": "1.0.2",
  "commit": "c160fca0",
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

### 2.2 Analysis & Render Blueprint Specification
- The application code, Celery task definitions, outbox retry worker, and database models are completely sound.
- Render Free tier permits only HTTP Web Services, not Background Workers or Beat daemons.
- The repository provides the production-ready Infrastructure-as-Code blueprint in [`render.yaml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/render.yaml):
  - `vouch-staging-worker`: Celery worker (`--concurrency=2 --prefetch-multiplier=1 --max-tasks-per-child=100`)
  - `vouch-staging-beat`: Single Celery beat scheduler (`--pidfile=/tmp/celerybeat.pid --schedule=/tmp/celerybeat-schedule`)
- Owner provisioning instructions are documented in Section 4.

---

## 3. Transactional Email & DNS Deliverability Analysis

### 3.1 Live DNS Records on `srilekh.com`
Live DNS query to public resolver (`8.8.8.8`):
```
srilekh.com  text = "v=spf1 include:secureserver.net -all"
_dmarc.srilekh.com  text = "v=DMARC1; p=quarantine; adkim=r; aspf=r; rua=mailto:dmarc_rua@onsecureserver.net;"
srilekh.com  MX preference = 0, mail exchanger = smtp.secureserver.net
srilekh.com  MX preference = 10, mail exchanger = mailstore1.secureserver.net
*** dns.google can't find default._domainkey.srilekh.com: Non-existent domain
```

### 3.2 The Deliverability Hazard
1. In [`config/settings.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/settings.py#L466-L476), `DEFAULT_FROM_EMAIL = 'SriLekh <admin@srilekh.com>'`, but default `EMAIL_HOST = 'smtp.gmail.com'`.
2. Because GoDaddy's SPF record ends with strict `-all` (Hardfail), any email sent from non-Secureserver IPs with sender `@srilekh.com` will result in **SPF HARDFAIL**.
3. With no DKIM signature published to salvage alignment, DMARC evaluates to **FAIL (Quarantine)**.
4. Emails (signup OTPs, password resets, account deletion links) will be rejected or placed into recipient Spam folders.

---

## 4. Owner Action Runbooks

### Runbook 1: Deploy Render Redis & Celery Workers (OA-05)
1. In Render Dashboard (`https://dashboard.render.com`), click **New +** -> **Redis**.
   - Name: `srilekh-staging-redis`
   - Plan: Free or Starter
   - Copy internal Redis connection string (e.g., `redis://red-xxxx:6379`).
2. Update Web Service `vouch-u3u7` Environment Variables:
   - `REDIS_URL` = `<internal Redis connection string>`
3. Click **New +** -> **Background Worker**:
   - Name: `vouch-staging-worker`
   - Branch: `fix/stage4-12-day6-remediation`
   - Start Command: `MALLOC_ARENA_MAX=2 celery -A config worker --loglevel=info --concurrency=2 --prefetch-multiplier=1 --max-tasks-per-child=100`
   - Instance Type: Starter ($7/month)
   - Add environment variables: `ENVIRONMENT=staging`, `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`.
4. Click **New +** -> **Background Worker**:
   - Name: `vouch-staging-beat`
   - Branch: `fix/stage4-12-day6-remediation`
   - Start Command: `celery -A config beat --loglevel=info --pidfile=/tmp/celerybeat.pid --schedule=/tmp/celerybeat-schedule`
   - Instance Type: Starter ($7/month)
   - Add environment variables matching the worker.

---

### Runbook 2: Configure SMTP Relay (OA-06)

#### Recommended Fast Path (GoDaddy Secureserver — 0 DNS Changes Required):
In Render Dashboard for `vouch-u3u7` and `vouch-staging-worker`, set:
```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtpout.secureserver.net
EMAIL_PORT=465
EMAIL_USE_SSL=True
EMAIL_USE_TLS=False
EMAIL_HOST_USER=admin@srilekh.com
EMAIL_HOST_PASSWORD=<Owner_GoDaddy_Mail_Password>
DEFAULT_FROM_EMAIL=SriLekh <admin@srilekh.com>
EMAIL_REPLY_TO=support@srilekh.com
```
*Rationale:* `smtpout.secureserver.net` sends from IPs covered by `include:secureserver.net`. SPF alignment is 100% immediate with zero DNS modifications.

#### Dedicated Transactional Provider Path (AWS SES / Resend / Postmark):
1. Provision AWS SES / Resend domain verification for `srilekh.com`.
2. Add provider-supplied DKIM CNAME/TXT records to GoDaddy DNS.
3. Update GoDaddy SPF TXT to:
   ```
   v=spf1 include:secureserver.net include:amazonses.com -all
   ```
4. Set provider SMTP host, port 587, and credentials in Render environment variables.

---

## 5. Verification Criteria for Closure

- **OA-05 Closure Evidence:**
  `curl -s https://vouch-u3u7.onrender.com/api/v1/health/environment/ | jq .` returns:
  `redis.status: "ok"`, `celery.workers_online >= 1`, `celery.beat_schedule_active: true`.
- **OA-06 Closure Evidence:**
  Automated password reset or signup OTP delivers to an external inbox in `< 10` seconds; raw email headers inspect to `spf=pass`, `dmarc=pass`.
