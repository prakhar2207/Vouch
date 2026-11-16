# SriLekh — Sandbox by Quicko Environment & Configuration Setup

## 1. Environment Variables Specification

The following environment variables configure the Quicko Sandbox GST integration across development, staging, and production environments:

```bash
# ==============================================================================
# QUICKO SANDBOX GST CONFIGURATION
# ==============================================================================

# Sandbox API Base URL
# Staging/Sandbox: https://test-api.sandbox.co.in
# Production:      https://api.sandbox.co.in
SANDBOX_BASE_URL="https://test-api.sandbox.co.in"

# Sandbox Organization API Credentials (from developer.sandbox.co.in)
SANDBOX_API_KEY="key_test_xxxxxxxxxxxxxxxxxxxx"
SANDBOX_API_SECRET="sec_test_yyyyyyyyyyyyyyyyyyyy"

# Sandbox API Protocol Version
SANDBOX_API_VERSION="1.0.0"

# Master Encryption Key for Stored GST Tokens & Passwords (Fernet/AES-256)
# Must be 32 URL-safe base64-encoded bytes (e.g. from cryptography.fernet.Fernet.generate_key())
GST_CREDENTIAL_ENCRYPTION_KEY="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx="

# Live Integration Switch (Set to True only when live Sandbox calls are permitted)
ENABLE_GST_LIVE_SYNC="False"
```

---

## 2. Encryption of Stored Credentials at Rest

In compliance with Indian IT Act rules and standard SaaS security policies, all sensitive third-party credentials stored in the database are encrypted using symmetric Fernet encryption (AES-128 in CBC mode with HMAC-SHA256 authenticated encryption):

1. **Company Level (`CompanyGSTConfig`)**:
   - `sandbox_api_secret`: Encrypted at rest.
   - `sandbox_access_token`: Encrypted at rest.
2. **Registration Level (`GSTRegistration`)**:
   - `auth_token`: Encrypted at rest.
   - `einvoice_password`: Encrypted at rest.
   - `eway_password`: Encrypted at rest.

### Key Management
The `GST_CREDENTIAL_ENCRYPTION_KEY` is loaded strictly from the system environment and is never hard-coded or logged. If this key is rotated, an administrative management command re-encrypts all database credentials under the new key.

---

## 3. Multi-GSTIN Configuration per Tenant

SriLekh allows tenants to configure multiple GST registrations under a single company account.

### Database Setup
Tenants can create distinct registrations via the API or UI:
- **Endpoint**: `POST /api/v1/gst/registrations/`
- **Fields**:
  - `gstin`: 15-character valid Indian GSTIN.
  - `state_code`: 2-digit numerical state code (e.g., `27` for Maharashtra).
  - `legal_name`: Entity legal name as registered on GST Portal.
  - `trade_name`: Trade name / DBA.
  - `address`: Principal place of business address.
  - `pincode`: 6-digit postal code.
  - `is_primary`: Flag marking the default registration for the tenant.
  - `einvoice_username`: NIC portal API username.
  - `eway_username`: EWB portal API username.

---

## 4. Token Lifecycle & Automated Refresh

```
+───────────────────────────────────────────────────────────────+
|                 Sandbox JWT Token Lifecycle                   |
+───────────────────────────────────────────────────────────────+
  1. Token Acquisition:
     - SandboxGSTClient calls POST /authenticate with API Key + Secret.
     - Receives access_token (valid for 86,400 seconds / 24 hours).

  2. Token Caching:
     - Token is encrypted and persisted in CompanyGSTConfig.
     - sandbox_token_expires_at is set to current_time + expires_in - 300s (5-min buffer).

  3. Automated Pre-Expiry Refresh:
     - On any outbound API call, SandboxGSTClient checks is_token_valid().
     - If current_time >= sandbox_token_expires_at, authenticate() is triggered automatically.

  4. Re-auth on 401 Unauthorized:
     - If Sandbox returns HTTP 401, the client clears the cached token and attempts one re-authentication.
```

---

## 5. Health Check & Connectivity Verification

Administrators can verify live Sandbox connectivity using the dedicated health endpoint:

- **Endpoint**: `GET /api/v1/gst/health/`
- **Response**:
```json
{
  "status": "HEALTHY",
  "provider": "SANDBOX_CO_IN",
  "base_url": "https://test-api.sandbox.co.in",
  "auth_valid": true,
  "last_ping_latency_ms": 142
}
```
