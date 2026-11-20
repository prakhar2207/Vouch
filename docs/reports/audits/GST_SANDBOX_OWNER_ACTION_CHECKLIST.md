# SriLekh — Sandbox by Quicko Business Owner Action Checklist

## 1. Overview

While the technical architecture, models, serializers, views, services, frontend components, and automated test suites are **100% complete and verified**, activating live GST API services against government portals requires administrative and commercial actions that can only be performed by the registered business owner.

This checklist provides step-by-step instructions for the business owner to transition SriLekh from staging/mock mode to live production operation.

---

## 2. Step-by-Step Onboarding Checklist

### Step 1: Create Quicko Sandbox Developer Account
1. Visit the Sandbox Developer Portal: https://developer.sandbox.co.in
2. Sign up with the official company email (e.g. `admin@srilekh.com`).
3. Complete organization verification and KYC details.
4. Navigate to **API Keys** in the dashboard and note down:
   - Organization API Key (`x-api-key`)
   - Organization API Secret (`x-api-secret`)

### Step 2: Subscribe to Sandbox GST Product
1. In the Sandbox console, select the **GST** product (`https://sandbox.co.in/gst`).
2. Review pricing tiers based on projected monthly transaction volume:
   - Public GSTIN Search calls (pay-per-call or bundle).
   - e-Invoice & e-Way Bill generation bundle.
   - GSTR Return filing & GSTR-2B download feeds.
3. Fund the Sandbox wallet or set up monthly invoicing.

### Step 3: Enable Taxpayer API Access on Government GST Portal
For each GSTIN belonging to the company or client tenants that will file returns, generate e-Invoices, or sync 2B:
1. Log in to the official **GST Portal** (`https://www.gst.gov.in`).
2. Navigate to: **My Profile** -> **Manage API Access**.
3. Set **Enable API Access** to **Yes**.
4. Select the duration for session access (e.g., 6 hours or 30 days).
5. For e-Invoicing / E-Way Bills:
   - Log in to `https://einvoice1.gst.gov.in` and `https://ewaybillgst.gov.in`.
   - Go to **API Registration** -> **Create API User** -> Select **Through GSP** -> Choose **Quicko Infosoft Pvt Ltd** (or registered Sandbox GSP name).
   - Set the API username and password.

### Step 4: Configure Staging Environment Variables on Render
1. Open the Render Dashboard for Staging Web Service (`vouch-u3u7`).
2. Under **Environment**, populate:
   ```bash
   SANDBOX_BASE_URL="https://test-api.sandbox.co.in"
   SANDBOX_API_KEY="<YOUR_TEST_API_KEY>"
   SANDBOX_API_SECRET="<YOUR_TEST_API_SECRET>"
   GST_CREDENTIAL_ENCRYPTION_KEY="<YOUR_32_BYTE_BASE64_KEY>"
   ENABLE_GST_LIVE_SYNC="True"
   ```
3. Trigger a staging deployment and verify `GET /api/v1/gst/health/` returns `HEALTHY`.

### Step 5: Run Pilot Smoke Tests in Staging
1. Perform 1 live GSTIN lookup for a known business.
2. In the Next.js GST Center (`/gst`), verify that taxpayer profile is fetched and cached.
3. Generate a test e-Invoice on a sandbox sales voucher.
4. Generate a test E-Way Bill and update vehicle number.
5. Download GSTR-1 JSON and verify offline compatibility.

### Step 6: Production Promotion Gate
Once the pilot in Step 5 passes:
1. Obtain production API keys from `developer.sandbox.co.in`.
2. Configure production Render environment variables (`SANDBOX_BASE_URL="https://api.sandbox.co.in"`).
3. Switch `ENABLE_GST_LIVE_SYNC="True"`.
4. Follow standard release management procedures to merge into `main`.

---

## 3. Rollback & Fail-Safe Plan

If Sandbox experiences unexpected third-party downtime or government portal outages:
1. Set `ENABLE_GST_LIVE_SYNC="False"` in Render environment variables.
2. SriLekh automatically falls back to offline mode:
   - GSTR-1 returns can still be downloaded as JSON files for manual upload via the government offline tool.
   - Public GSTIN searches fall back to local database cache.
   - Core double-entry invoicing and accounting remain 100% operational and completely unaffected.
