# SRI LEKH — RAZORPAY DEPLOYMENT RUNBOOK

This runbook outlines the operational steps to deploy, migrate, and verify the Razorpay subscription infrastructure on Render Staging (`vouch-u3u7.onrender.com`).

---

## 1. Staging Deployment Steps

1. **Commit and Push to Staging Branch:**
   ```bash
   git add apps/billing/ config/ requirements.txt frontend/
   git commit -m "feat(billing): complete Razorpay payment gateway, subscriptions, and entitlement engine"
   git push origin fix/stage4-12-day6-remediation
   ```
2. **Render Staging Auto-Deploy or Manual Trigger:**
   - Service: `vouch-u3u7` (`https://vouch-u3u7.onrender.com`)
   - Branch: `fix/stage4-12-day6-remediation`
   - Build Command: `pip install -r requirements.txt && python manage.py collectstatic --no-input`
3. **Run Staging Migrations:**
   In Render Staging Shell or via build command:
   ```bash
   python manage.py migrate billing
   ```
4. **Seed Commercial Plans:**
   ```bash
   python manage.py shell -c "from apps.billing.services.entitlement_service import EntitlementService; print('Plans synced:', EntitlementService.sync_default_plans())"
   ```

---

## 2. Staging Health & Verification Check

1. **Verify Environment Isolation:**
   ```bash
   curl -s https://vouch-u3u7.onrender.com/api/v1/health/environment/ | jq .
   ```
   Assert: `database.is_isolated == true`, `sanitized_target == "neondb_staging"`.

2. **Verify Public Plans Endpoint:**
   ```bash
   curl -s https://vouch-u3u7.onrender.com/api/v1/billing/plans/ | jq .
   ```
   Assert: Returns 4 plans (`starter`, `growth`, `pro_ai`, `enterprise`).

3. **Verify Webhook Rejection of Unsigned Requests:**
   ```bash
   curl -s -X POST https://vouch-u3u7.onrender.com/api/v1/billing/webhooks/razorpay/ -d '{"test": true}'
   ```
   Assert: Returns HTTP 400 Bad Request (`Missing X-Razorpay-Signature header`).

---

## 3. Rollback Procedure

If an issue occurs on Staging:
1. Revert Render deployment to previous commit `c160fca0ae69a5dc1bc6398aa95e3185da024bb4`.
2. Rollback billing database migrations:
   ```bash
   python manage.py migrate billing zero
   ```
3. Core double-entry accounting is completely decoupled and remains unaffected.
