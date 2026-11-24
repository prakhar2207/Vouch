# SriLekh Pay — Staging Deployment Report

**Date:** November 24, 2026  
**Environment:** Staging  
**Service:** Render `vouch-staging-api` & `vouch-staging-worker`  
**Deployment Blueprint:** `render.yaml`  

---

## 1. Staging Environment Topology

| Component | Target System | Configured URL / Host | Branch | Status |
|---|---|---|---|---|
| **Staging API** | Render Web Service | `https://vouch-api-staging.onrender.com` | `main` | Configured & Active |
| **Staging Workers** | Render Worker / Beat | Celery worker & beat | `main` | Configured |
| **Staging Frontend** | Next.js / PWA | `https://staging.srilekh.com` / `https://vouch-pi-one.vercel.app` | `main` | Verified |
| **Staging Database** | Neon PostgreSQL | `ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech` / `neondb_staging` | N/A | Connected & Migrated |
| **Sandbox Tenant** | Staging Company | `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`) | N/A | Active & Verified |

---

## 2. Migrations Applied on Staging

The following database migrations have been executed against `neondb_staging`:
1. `apps.payments.0001_initial`:
   - `MerchantPaymentAccount`
   - `PaymentRequest`
   - `PaymentWebhookEvent`
   - `PaymentRefund`
   - `UnmatchedPaymentRecord`
2. `apps.payments.0002_alter_paymentrefund_status_and_more`:
   - `Beneficiary` model with composite indexes
   - `beneficiary` foreign key on `PaymentRequest`

All migrations applied with status **OK** and 0 errors.

---

## 3. Build & Healthcheck Specifications

- **Build Script (`build.sh`)**:
  - `python -m pip install -r requirements.txt`
  - `python manage.py collectstatic --no-input`
  - `python manage.py migrate`
- **Application Startup**:
  - `gunicorn config.wsgi:application --workers 1 --threads 4 --timeout 180`
- **Healthcheck Path**:
  - `GET /api/v1/health/environment/` (returns HTTP 200 with DB & Redis ping)
