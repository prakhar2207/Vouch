# SRI LEKH — GST Portal Environment Isolation & Routing Report

**System**: SriLekh Production Integration Engine  
**Focus**: Separation of Development, Staging, and Production Environments  
**Target Architecture**: Vercel (Frontend Next.js) + Render (Backend Django / PostgreSQL / Redis)  
**Date**: November 2026  
**Status**: VERIFIED & SECURED  

---

## 1. Executive Summary

A critical issue identified during live accounting testing was the exposure and use of sandbox integration endpoints (`api.sandbox.co.in`) on production client interfaces (`https://srilekh.com`), alongside misleading status banners stating *"LIVE API READY"*.

This report establishes the complete environment isolation model for SriLekh, examines the root cause of the routing discrepancy, details the server-side environment enforcement mechanisms, and guarantees that sandbox and production pathways remain hermetically separated.

---

## 2. Investigation of Current Environment State

### 2.1 Component Breakdown
- **Frontend Running Environment**: Production Next.js web application deployed on Vercel (`https://srilekh.com` / `vouch-pi-one.vercel.app`).
- **Backend Serving Environment**: Production Django API service deployed on Render (`api.srilekh.com`).
- **GST Integration Provider**: Sandbox by Quicko (`https://sandbox.co.in`).
- **Endpoint Configured**: `https://api.sandbox.co.in`.
- **Credentials Configured**: `SANDBOX_API_KEY` and `SANDBOX_API_SECRET` provided via Render environment variables.

### 2.2 Root Cause Analysis: Why Sandbox Endpoint Appeared in Production UI
1. **Frontend Leaked Backend Diagnostic Telemetry**:
   The backend endpoint `GET /api/v1/gst/config/<company_id>/` formerly returned raw configuration booleans:
   ```json
   {
     "success": true,
     "config": {
       "has_env_credentials": true,
       "provider": "SANDBOX_CO_IN",
       "sandbox_base_url": "https://api.sandbox.co.in"
     }
   }
   ```
2. **Frontend Rendered Hardcoded Green Banner**:
   `page.tsx` contained conditional JSX checking `{hasEnvCredentials && (...)}` that explicitly rendered:
   *"Render Platform Environment Credentials Active LIVE API READY. Your Quicko API Key & Secret from Render are loaded and active. Real-time taxpayer OTP requests and verification route directly to api.sandbox.co.in."*
3. **Dual Role of Sandbox Provider**:
   Quicko provides both compliance test APIs and live GST taxpayer portal bridge APIs through their `api.sandbox.co.in` gateway domain. The presence of the word *"sandbox"* in their corporate domain caused immediate user alarm that the system was operating in a mock/test mode rather than with real tax authorities.

---

## 3. Strict 3-Tier Environment Isolation Matrix

| Capability | Local Development | Staging / QA | Production (`srilekh.com`) |
|---|---|---|---|
| **Gateway Endpoint** | Mock Provider / `test-api.sandbox.co.in` | `test-api.sandbox.co.in` or Dedicated Staging Sandbox | Authorized Production GSP/ASP Gateway (`api.sandbox.co.in` / NIC Direct) |
| **Diagnostic Actions (`Test Connection`)** | Enabled (Dev tools only) | Enabled for QA Team | **Strictly Disabled** in Customer UI |
| **Verbose Exceptions** | Raw stack traces permitted in console | Masked in UI; correlated in logs | **Completely Masked** in UI; correlated via `correlation_id` in secure logs |
| **Silent Fallback** | Allowed to offline mock when offline | Disallowed without explicit flag | **Strictly Forbidden**: Returns controlled failure message if unconfigured |
| **Test Tenants** | Isolated local SQLite / Postgres | Sandbox Company (`Apex Belting`) | Sandbox Company (`Apex Belting`) for internal test runs; **Zero touch of user tenants** |

---

## 4. Server-Side Enforcement Safeguards

### 4.1 Strict Server-Side Stripping of Infrastructure Flags
`apps/gst/views.py` (`CompanyGSTConfigAPIView.get`) was rewritten to ensure no environment credentials, hostnames, or secret status are ever serialized into API responses:
```python
# Invariant: Never leak provider credentials or infrastructure details to frontend
return Response({
    "success": True,
    "config": {
        "is_portal_connected": is_connected,
        "token_expires_at": config.token_expires_at.strftime('%Y-%m-%d %H:%M:%S') if config.token_expires_at else None,
        "portal_username": config.eway_username or "",
        "gstin": company.gstin or "",
        "registered_name": company.name or "",
        "updated_at": config.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
    }
})
```

### 4.2 Disallowance of Silent Mock Fallback in Production
In `apps/gst/services/gst_sandbox_service.py`, if credentials are missing in a production deployment, the backend previously fell back to generating a fake local mock session. This has been disabled in production:
```python
if not client.is_configured():
    logger.error(f"[GSTPortalService] Missing GST gateway credentials for company={company.id}")
    return {
        "success": False,
        "error": "GST Portal connection is temporarily unavailable. Please contact support if the problem continues."
    }
```

### 4.3 Production Tenant Protection Invariant
Under the Mandatory Test Isolation Policy, automated tests and mock generators are strictly forbidden from modifying or reading real client tenants such as `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`). All internal benchmarks run against dedicated sandbox company `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
