# SRI LEKH — GST Portal UX Abstraction & Technical Exposure Audit

**Product Principle**: *Accounting flexibility like Tally, with the simplicity of modern business software.*  
**Domain**: Direct GST Portal Integration (`/settings?tab=gst-portal`)  
**Target User**: Retailers, Wholesalers, Accountants, MSME Owners  
**Date**: November 2026  
**Status**: RESOLVED & HARDENED  

---

## 1. Executive Summary

An audit of the GST Portal Direct Connect user interface revealed severe abstraction leaks where low-level infrastructure telemetry, external vendor branding, developer diagnostics, and raw API parameters were directly rendered on customer-facing screens. Ordinary business operators were exposed to hosting infrastructure labels, internal endpoint URLs, raw HTTP parameter validation exceptions, and diagnostic actions that belong exclusively in engineering consoles.

This document inventories every identified abstraction leak, details why it violates core product and business principles, and establishes the formal SriLekh Abstraction Standard for all current and future integrations.

---

## 2. Inventory of Identified Abstraction Leaks

| Defect ID | User-Visible Artifact in UI | Layer of Leak | Impact on Business User | Remediation Status |
|---|---|---|---|---|
| **LK-01** | `Render Platform Environment Credentials Active` | Hosting Provider | Severe confusion; user fears deployment details affect tax filing | **REMOVED** from frontend & sanitized on backend |
| **LK-02** | `LIVE API READY` | Backend Diagnostics | Developer readiness flag shown as product status | **REMOVED** |
| **LK-03** | `Your Quicko API Key & Secret from Render are loaded and active.` | External Vendor / Secrets | Unprofessional; reveals third-party intermediary and secret storage mechanisms | **REMOVED** |
| **LK-04** | `Real-time taxpayer OTP requests and verification route directly to api.sandbox.co.in.` | Network Routing / Hostname | Exposes sandbox endpoints to live accounting users | **REMOVED** |
| **LK-05** | `Test Connection` button & `Successfully authenticated with Sandbox by Quicko` | Developer Diagnostic Action | Diagnostic button in production UI; invites unneeded clicks and creates false alarm states | **REMOVED** |
| **LK-06** | `Missing required request parameters: [x-source]` | Raw API Contract Exception | Cryptic HTTP header validation exception dumped directly into UI red alert box | **REPLACED** with normalized business error message |
| **LK-07** | Minified React Error #418 (Hydration Mismatch) | SSR Engine | React console error from client/server date parsing discrepancy | **RESOLVED** via `mounted` guard and `suppressHydrationWarning` |
| **LK-08** | Multi-GSTIN Tab: `Verified via Sandbox by Quicko` & `Verify now with Sandbox` | Settings Copy | Exposes vendor name and test sandbox terminology on registration cards | **REPLACED** with "Verified via official GST records" |

---

## 3. Product & Architectural Analysis: Why Technical Exposure Violates SriLekh Principles

### 3.1 Cognitive Overload for Business Operators
A textile merchant or hardware distributor using SriLekh thinks in terms of:
- *"Is my GSTR-1 ready to file?"*
- *"Can I verify if my supplier filed GSTR-2B so I can claim ITC?"*
- *"Did the OTP come to my phone?"*

When presented with `api.sandbox.co.in` or `x-source`, the merchant is forced to ask:
- *"Is this real or a demo?"*
- *"What is Quicko? Is my data safe with them?"*
- *"What is Render? Did our server crash?"*
- *"What is x-source? Did I type my GST password wrong?"*

This destroys user trust, creates unnecessary support tickets, and makes the software appear unfinished.

### 3.2 Security Risk of Infrastructure Disclosure
Revealing internal hostnames (`api.sandbox.co.in`), hosting providers (`Render`), and API gateways (`Quicko`) gives potential adversaries information on the exact architecture, vendor supply chain, and integration contracts employed by the SaaS platform.

### 3.3 Diagnostic Controls in Production Workflows
A `Test Connection` button implies to the user that the system is unstable and requires manual user verification before performing routine business tasks. Diagnostic probes belong in health endpoints and administrative dashboards, not in the primary workflow of accounting clerks.

---

## 4. Remediation Architecture

```
[Business User]
       │  (Enters GSTIN / Username & Clicks "Connect GST Portal")
       ▼
[SriLekh Clean 3-State UI]
   • Not Connected: Clean input + "Connect GST Portal"
   • OTP Verification: 6-digit OTP + "Verify and Connect" + 30s Cooldown
   • Connected: GSTIN + Business Name + Active Session Expiry
       │
       │  (Standard REST Request: /api/v1/gst/portal/request-otp/)
       ▼
[Backend Abstraction Layer: apps/gst/views.py]
   • Strips all internal flags: has_env_credentials, sandbox_base_url, api_keys
   • Enforces RBAC & tenant boundary
       │
       ▼
[GSTPortalService: apps/gst/services/gst_sandbox_service.py]
   • Enforces 30s cooldown per company in Redis/Cache
   • Enforces max 5 OTP requests/hour rate limit
   • Brute-force protection: Lockout after 5 failed OTP attempts
       │
       ▼
[GST Error Normalizer: apps/gst/services/gst_error_normalizer.py]
   • Intercepts raw exceptions, HTTP 429, timeouts, missing parameters
   • Masks [x-source], tokens, keys, vendor names
   • Returns safe, actionable, localized business copy
       │
       ▼
[SandboxGSTClient: apps/gst/services/sandbox_client.py]
   • Injects required headers: x-source: primary, x-api-version: 1.0.0
   • Dispatches request to authorized gateway
```

---

## 5. Ongoing Enforcement Standard

1. **Rule of Zero Vendor Disclosure**: No third-party API provider (Quicko, Sandbox.co.in, Cashfree, ClearTax) or hosting vendor (Render, AWS, Vercel) may ever be visible in the user interface.
2. **Rule of Exception Normalization**: All errors presented to the UI must pass through `normalize_gst_error()`. Raw exception strings, HTTP status codes, or header names are strictly forbidden.
3. **Rule of Diagnostic Isolation**: Diagnostic buttons (`Test Connection`, `Ping Gateway`) must never exist on standard production settings tabs.
