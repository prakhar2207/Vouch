# SRI LEKH — STAGE 1.2.6 PRODUCTION CUTOVER RUNBOOK

**Target Feature Commit:** `c160fca0` on `feat/google-play-launch-readiness`  
**Target Production Branch:** `main` (`d39d481ac2eb545d0436fafa9dd2c593ceb7e946`)  
**Production API:** `https://vouch-api-752s.onrender.com`  
**Production Database:** `neondb` (Neon AWS US-East-2 Ohio)  
**Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`)  
**Certification Verdict:** **READY FOR OWNER EXECUTION (OA-01)**  

---

## 1. Safety Rules & Invariants (Non-Negotiable)

1. **Owner Sign-Off Mandatory:** No merge into `main`, production deployment, or production database migration may be executed without explicit written authorization from the system owner.
2. **Tenant Protection:** Under NO circumstances may any test script, mock generator, or automated health check write, update, or delete records in tenant `Maa Annapurna Belting Store`.
3. **Pre-Cutover Production Backup:** Before merging code or applying migrations to `neondb`, an immutable custom-format binary backup (`pg_dump -Fc`) must be captured and verified.
4. **Zero Downtime Target:** Maximum allowable cutover disruption window is `< 120` seconds. Maximum allowable data loss (RPO) is `0` seconds.

---

## 2. Pre-Flight Checklist

Before executing the cutover, verify:
- [ ] Staging tests pass 100% on `c160fca0` (CI pipeline `stage-verification-ci.yml` green).
- [ ] Legal placeholders resolved via `STAGE_1_2_6_LEGAL_OWNER_INPUT_REGISTER.md`.
- [ ] Owner has access to Render Dashboard (`https://dashboard.render.com`) and Vercel Dashboard (`https://vercel.com`).
- [ ] Neon DB console is accessible for instant point-in-time branch creation.
- [ ] Workstation executing the backup has `pg_dump` 16+ or Neon branching permissions.

---

## 3. Step-by-Step Cutover Execution Procedure

### Phase 1: Capture Production Pre-Cutover Backup (T - 15 minutes)
```bash
# Capture full binary backup of production database
export PROD_DB_URL="<PROD_NEONDB_CONNECTION_STRING>"
pg_dump -Fc --no-owner --no-privileges "$PROD_DB_URL" -f prod_pre_cutover_$(date +%Y%m%d_%H%M%S).dump

# Verify backup integrity
pg_restore --list prod_pre_cutover_*.dump > /dev/null && echo "BACKUP INTEGRITY VERIFIED"
```
*Alternative (Instant Neon Snapshot):*
In the Neon Console (`console.neon.tech`), create a branch named `backup-pre-stage1-2-cutover` from the `main` branch. This provides an instantaneous, zero-overhead point-in-time recovery target.

---

### Phase 2: Merge Feature Branch into Main (T - 5 minutes)
```bash
# Switch to main and pull latest production state
git checkout main
git pull origin main

# Fast-forward or merge verified release candidate commit c160fca0
git merge c160fca0 --no-ff -m "chore(release): merge Stage 1.2.6 verified release candidate c160fca0 into main"

# Push to origin main (triggers automated production webhooks)
git push origin main
```

---

### Phase 3: Backend Production Deployment & Migration Execution (T = 0)
1. Monitor Render deployment logs for service `vouch-api-752s` (`https://vouch-api-752s.onrender.com`).
2. Build script `./build.sh` runs automatically:
   - `pip install -r requirements.txt`
   - `python manage.py collectstatic --noinput`
   - `python manage.py migrate --noinput`
3. Verify Render logs confirm all migrations applied without table lock timeouts:
   ```
   Operations to perform:
     Apply all migrations: accounts, accounting, audit, companies, notifications
   Running migrations:
     Applying ... OK
   ```

---

### Phase 4: Frontend Production Deployment (T + 3 minutes)
1. Monitor Vercel deployment dashboard for project `vouch` (or `srilekh`).
2. Verify production build succeeds (`npm run build`).
3. Verify custom domain aliases resolve:
   - `https://www.srilekh.com`
   - `https://srilekh.com`

---

### Phase 5: Post-Deployment Smoke Verification (T + 5 minutes)

Execute the production health probe suite:

```bash
# 1. API Health & Database Isolation
curl -s -f https://vouch-api-752s.onrender.com/api/v1/health/environment/ | jq .
# Expected: "status": "healthy", "database": {"status": "connected", "name": "neondb", "is_isolated": true}

# 2. Public Statutory Pages (Must return HTTP 200, NOT 404)
curl -s -o /dev/null -w "%{http_code}\n" https://www.srilekh.com/privacy-policy
curl -s -o /dev/null -w "%{http_code}\n" https://www.srilekh.com/terms
curl -s -o /dev/null -w "%{http_code}\n" https://www.srilekh.com/contact
curl -s -o /dev/null -w "%{http_code}\n" https://www.srilekh.com/refund-policy
curl -s -o /dev/null -w "%{http_code}\n" https://www.srilekh.com/delete-account
curl -s -o /dev/null -w "%{http_code}\n" https://www.srilekh.com/pricing

# 3. CORS Pre-Flight Validation
curl -s -I -X OPTIONS https://vouch-api-752s.onrender.com/api/v1/health/ \
  -H "Origin: https://www.srilekh.com" \
  -H "Access-Control-Request-Method: GET"
# Expected: HTTP 200 with Access-Control-Allow-Origin: https://www.srilekh.com
```

---

## 4. Rollback Decision Matrix & Emergency Procedures

| Trigger Event | Severity | Action | RTO Target |
| :--- | :--- | :--- | :--- |
| **Database Migration Crash / Schema Lock** | Critical | Abort deployment. Restore DB snapshot or switch Neon branch back to `backup-pre-stage1-2-cutover`. | < 3 minutes |
| **Backend 500 Errors on Startup** | High | In Render Dashboard, click **Rollback to Previous Deploy** on `vouch-api-752s`. | < 1 minute |
| **Frontend SSR / Static Page Routing Failures** | Medium | In Vercel Dashboard, promote previous production deployment to Instant Rollback. | < 30 seconds |
| **CORS / Cookie Authentication Mismatch** | High | Revert `main` branch commit via `git revert -m 1 HEAD && git push origin main`. | < 2 minutes |

### Emergency Database Rollback Script:
```bash
# In emergency, restore clean state to production DB
pg_restore --no-owner --no-privileges --clean --if-exists --single-transaction -d "$PROD_DB_URL" prod_pre_cutover_*.dump
```
