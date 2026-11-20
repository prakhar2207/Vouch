# SRI LEKH — STAGE 1.2.7 PRODUCTION CUTOVER READINESS & APPROVAL REQUEST

**Assessment Date:** 2026-11-12  
**Candidate Release Commit:** `d3f8e9f` on `feat/google-play-launch-readiness`  
**Target Production Branch:** `main` (`d39d481ac2eb545d0436fafa9dd2c593ceb7e946`)  
**Production API Target:** `https://vouch-api-752s.onrender.com`  
**Production Database Target:** `neondb` on AWS Neon Cluster `ep-lingering-boat-b3994i6f`  
**Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`)  
**Certification Verdict:** **READY FOR OWNER EXECUTION / STOPPED AT APPROVAL GATE (OA-01)**  

---

## 1. Safety Mandate & Invariants (Explicit Stop Gate)

> [!CAUTION]
> **PRODUCTION FREEZE IN FORCE**:
> Per Section 2 & Section 15 of the Stage 1.2.7 directive:
> - The automated agent is strictly forbidden from merging into `main`, running production database migrations, modifying production environment variables, or triggering production deployments without explicit written authorization from the system owner.
> - Under NO circumstances may any test script, mock data generator, or verification probe write, modify, or delete data in protected tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`).
>
> **The deployment is STOPPED at this gate awaiting your explicit approval.**

---

## 2. Pre-Cutover Readiness Assessment

| Verification Item | Target Standard | Observed Status on Release Candidate `d3f8e9f` | Gate Result |
| :--- | :--- | :--- | :--- |
| **Commit Baseline** | Verified feature branch | Commit `d3f8e9f` clean on `feat/google-play-launch-readiness` | **READY** |
| **Cloud CI Verification** | All jobs pass | GitHub Actions run `43267275998` completed successfully | **PASS** |
| **Python Dependency Audit** | Zero CVEs | `pip-audit --strict -r requirements.txt`: 0 vulnerabilities | **PASS** |
| **Backend Regression Suite** | Core security & DR pass | 26/26 Django tests passed (13.2s) | **PASS** |
| **Frontend TypeScript & Tests** | 0 TS errors, all tests pass | `npx tsc --noEmit` clean, 45/45 unit/integration tests passed | **PASS** |
| **Frontend Production Build** | Static generation clean | `npm run build`: 57/57 routes generated cleanly | **PASS** |
| **Database Migration Dry-Run** | Zero unapplied model diffs | `makemigrations --check --dry-run` reports no changes detected | **READY** |
| **Staging Populated DR** | Verified live on cluster | 100% parity, ₹0.00 variance, RTO 287s, RPO 0s (OA-07) | **PASS** |

---

## 3. Step-by-Step Production Cutover Execution Plan (Upon Approval)

When the owner authorizes deployment, execute in the following exact sequence:

### Phase 1: Capture Immutable Pre-Cutover Production Backup (T - 15 mins)
```bash
# Capture full custom-format binary backup of production database
export PROD_DB_URL="<NEONDB_PRODUCTION_CONNECTION_STRING>"
pg_dump -Fc --no-owner --no-privileges "$PROD_DB_URL" -f prod_pre_cutover_$(date +%Y%m%d_%H%M%S).dump

# Verify backup integrity
pg_restore --list prod_pre_cutover_*.dump > /dev/null && echo "PRE-CUTOVER BACKUP VERIFIED"
```
*Instant Cloud Alternative:*
In the Neon Console (`console.neon.tech`), create an instant branch named `backup-pre-stage12-cutover` from the `main` database branch.

---

### Phase 2: Fast-Forward Merge into Main Branch (T - 5 mins)
```bash
git checkout main
git pull origin main
git merge d3f8e9f --no-ff -m "chore(release): merge Stage 1.2.7 verified release candidate d3f8e9f into main"
git push origin main
```

---

### Phase 3: Backend Production Deployment & Migrations (T = 0)
1. Pushing to `origin main` automatically triggers Render build on service `vouch-api-752s`.
2. `./build.sh` runs:
   - `pip install -r requirements.txt`
   - `python manage.py collectstatic --noinput`
   - `python manage.py migrate --noinput`
3. Verify Render deployment logs report zero migration errors and Gunicorn worker startup.

---

### Phase 4: Frontend Production Deployment (T + 3 mins)
1. Pushing to `origin main` triggers Vercel production deployment for `www.srilekh.com`.
2. Verify production build succeeds (`npm run build`).

---

### Phase 5: Post-Deployment Smoke Probes (T + 5 mins)
```bash
# 1. Verify Production API Environment Health & Isolation
curl -s -f https://vouch-api-752s.onrender.com/api/v1/health/environment/ | jq .
# Expected: status="healthy", database.sanitized_target="neondb", database.is_isolated=true

# 2. Verify Public Statutory Compliance Pages (Must return HTTP 200, NOT 404)
curl -s -o /dev/null -w "%{http_code}\n" https://www.srilekh.com/privacy-policy
curl -s -o /dev/null -w "%{http_code}\n" https://www.srilekh.com/terms
curl -s -o /dev/null -w "%{http_code}\n" https://www.srilekh.com/contact
curl -s -o /dev/null -w "%{http_code}\n" https://www.srilekh.com/refund-policy
curl -s -o /dev/null -w "%{http_code}\n" https://www.srilekh.com/delete-account
curl -s -o /dev/null -w "%{http_code}\n" https://www.srilekh.com/pricing

# 3. Verify CORS Origin
curl -s -I -X OPTIONS https://vouch-api-752s.onrender.com/api/v1/health/ \
  -H "Origin: https://www.srilekh.com" \
  -H "Access-Control-Request-Method: GET"
```

---

## 4. Emergency Rollback Procedures & Decision Criteria

| Trigger Event | Severity | Immediate Action | SLA Target |
| :--- | :--- | :--- | :--- |
| **Migration Failure / Table Lock Timeout** | Critical | Abort cutover. Restore binary snapshot or revert Neon branch to `backup-pre-stage12-cutover`. | < 3 minutes |
| **Backend 500 Errors on Startup** | High | In Render Dashboard, click **Rollback to Previous Deploy** on `vouch-api-752s`. | < 1 minute |
| **Frontend SSR / Routing Failures** | Medium | In Vercel Dashboard, promote previous production deployment to Instant Rollback. | < 30 seconds |

### Emergency Command to Restore Pre-Cutover Production DB:
```bash
pg_restore --no-owner --no-privileges --clean --if-exists --single-transaction -d "$PROD_DB_URL" prod_pre_cutover_*.dump
```

---

## 5. Owner Decision Required

To proceed with production cutover, reply with:
> **"I approve production cutover of commit `d3f8e9f` to `main`."**
