# SriLekh — Sandbox by Quicko Owner Setup Checklist

## 1. Overview

SriLekh integrates with **Sandbox by Quicko** (`https://sandbox.co.in` / `https://developer.sandbox.co.in`) to provide automated GSTIN verification, taxpayer profile enrichment, multi-state GST registration tracking, and future GST return & e-Invoice services for Indian MSMEs.

Follow this checklist to provision and activate your Sandbox provider credentials.

---

## 2. Step-by-Step Onboarding Checklist

### Step 1: Create a Developer Account
- [ ] Visit [developer.sandbox.co.in](https://developer.sandbox.co.in) and register using your business email.
- [ ] Verify your email and complete phone/OTP authentication.

### Step 2: Create an Application in Developer Console
- [ ] In the Sandbox Dashboard, navigate to **Applications** $\rightarrow$ **Create New App**.
- [ ] Name your application (e.g., `SriLekh Staging` or `SriLekh Production`).
- [ ] Under **Products**, select and enable **GST** (`Compliance & Verification`).

### Step 3: Obtain API Credentials
- [ ] In your application settings, locate your API credentials:
  - **API Key** (e.g., `key_live_...` or `key_test_...`)
  - **API Secret** (e.g., `secret_live_...` or `secret_test_...`)
  - **API Version** (Current stable: `1.0`)
- [ ] Copy these credentials securely. **Never commit them to Git or share in public chat.**

### Step 4: Verify Subscription Tier & Credits
- [ ] Check that your application has active test/production credits for:
  - `POST /gst/compliance/public/gstin/search` (Public GSTIN Search)
  - `POST /authenticate` (Access token exchange)
- [ ] If using test mode, note test GSTINs provided by Sandbox for dry-run verification.

---

## 3. Environment Variable Configuration

Configure the following environment variables in your hosting provider (Render / Vercel):

### Backend Environment (Render Dashboard $\rightarrow$ Environment Variables)

| Variable | Description | Example / Default |
| :--- | :--- | :--- |
| `SANDBOX_API_KEY` | Your Sandbox API Key | `key_live_xxxxxxxxxxxxxxxx` |
| `SANDBOX_API_SECRET` | Your Sandbox API Secret | `secret_live_xxxxxxxxxxxxxxxx` |
| `SANDBOX_BASE_URL` | Sandbox API Gateway Base URL | `https://api.sandbox.co.in` |
| `SANDBOX_API_VERSION` | API Version Header | `1.0` |
| `GST_ENCRYPTION_KEY` | Base64 32-byte Fernet key for credential encryption | `(Generate via Fernet.generate_key())` |

---

## 4. Verification in SriLekh

Once environment variables are deployed:

1. **Verify Backend Connection**:
   - Access the Django shell or trigger the connection test endpoint:
     ```bash
     python manage.py shell -c "from apps.gst.services.authentication_service import SandboxAuthenticationService; print(SandboxAuthenticationService.test_connection('<COMPANY_ID>'))"
     ```
   - Successful output: `{'success': True, 'status': 'AUTHENTICATED', ...}`.

2. **Verify Frontend Multi-GSTIN & GSTIN Lookup**:
   - Log in to SriLekh as an Owner or Admin.
   - Navigate to **Settings** $\rightarrow$ **GST Registrations**.
   - Click **Add Registration**, enter a state GSTIN, and click **Verify with GST**.
   - Confirm that the Legal Name, Trade Name, and Address are retrieved from Sandbox.
   - Save the registration and toggle primary status.
   - Navigate to **Parties (Customers / Suppliers)** and test "Verify with GST" on party forms.
