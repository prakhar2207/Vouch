# SriLekh GST Integration — Round 1.3 Residual Risks & Operational Prerequisites
## Honest Risk Matrix, External Dependencies & Owner Action Items

- **Target System:** SriLekh GST Integration
- **Auditor Role:** Principal System Architect & Quality Assurance Lead
- **Date:** November 16, 2026
- **Status:** ACTIONABLE REGISTER PRIOR TO LIVE ACTIVATION

---

## 1. Executive Summary

While all code-level defects, cryptographic vulnerabilities, database invariants, and RBAC gaps identified in Round 1.2 have been remediated, real-world live provider connectivity requires external owner-dependent actions and operational coordination.

This document clearly distinguishes between **Engineering-Complete Work** (already implemented and tested) and **Owner-Dependent Dependencies** (required before live activation).

---

## 2. Residual Risk & Dependency Matrix

| # | Risk / Blocker Domain | Severity | Current Status | Owner / DevOps Action Required |
|---|---|---|---|---|
| **1** | **Live Sandbox API Credentials** | **HIGH** | `NOT LIVE-VERIFIED` | Client must obtain Sandbox credentials from `https://developer.sandbox.co.in` and set `SANDBOX_API_KEY` and `SANDBOX_API_SECRET` in the Render staging dashboard. |
| **2** | **Dedicated Encryption Key in Staging** | **MEDIUM** | Fallback to SECRET_KEY Active (Warning) | Client must set `GST_ENCRYPTION_KEY` in Render environment variables for `vouch-u3u7.onrender.com` using the provided 44-char Fernet key. |
| **3** | **Sandbox Provider Quota & Rate Limits** | **MEDIUM** | Mock-Tested Only | Quicko Sandbox free tiers enforce request throttles. Operational monitoring must be configured once live traffic begins. |
| **4** | **Database Migration Application on Staging** | **LOW** | Migration Ready | Staging build pipeline runs `python manage.py migrate` automatically on deploy. Ensure Neon `neondb_staging` applies migration `0007`. |
| **5** | **GSTR-1 / 3B / 2B Return Workspaces** | **LOW** | Out of Scope for Round 1 | Filing and reconciliation features are scheduled for subsequent implementation rounds (Round 2 & Round 3). |

---

## 3. Immediate Action Checklist for Staging Activation

To complete live verification on the Render staging service (`https://vouch-u3u7.onrender.com`):

1. **Log in to Render Dashboard:**
   Navigate to service `vouch-u3u7`.
2. **Add Environment Variables:**
   ```env
   GST_ENCRYPTION_KEY=gARI18ulp-PN9OxExXsg44YMDs0Hb4WYDeZmMAD3Hkg=
   SANDBOX_API_KEY=<your-quicko-sandbox-api-key>
   SANDBOX_API_SECRET=<your-quicko-sandbox-api-secret>
   ```
3. **Trigger Manual Deploy (or push latest staging commit):**
   Render will build static assets, run migrations, and launch Gunicorn.
4. **Execute Live GSTIN Verification:**
   From the SriLekh UI or staging API, verify a test GSTIN (e.g. `27AAACA1234A1Z5`) and confirm live provider response.
