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

| # | Risk / Blocker Domain | Severity | Current Status | Owner / DevOps Action Completed / Status |
|---|---|---|---|---|
| **1** | **Live Sandbox API Credentials** | **HIGH** | `VERIFIED & OPERATIONAL` | Client configured live staging credentials; authentication handshake and taxpayer search certified with HTTP 200 responses. |
| **2** | **Dedicated Encryption Key in Staging** | **MEDIUM** | `CONFIGURED IN RENDER` | `GST_ENCRYPTION_KEY` configured in Render environment variables for `vouch-u3u7.onrender.com`. MultiFernet fail-closed security active. |
| **3** | **Sandbox Provider Quota & Rate Limits** | **MEDIUM** | `HARDENED & RETRY-BOUNDED` | Quicko Sandbox free tiers request throttles handled via bounded exponential backoff with jitter on HTTP 429 for idempotent requests. |
| **4** | **Database Migration Application on Staging** | **LOW** | `MIGRATION READY` | Staging build pipeline runs `python manage.py migrate` automatically on deploy. Applies migration `0007_gstregistration_unique_primary_gstin_per_company`. |
| **5** | **GSTR-1 / 3B / 2B Return Workspaces** | **LOW** | `OUT OF SCOPE (ROUND 2+)` | Filing and reconciliation features are scheduled for subsequent implementation rounds after foundation certification. |

---

## 3. Staging Activation & Operational Status

The Render staging service (`https://vouch-u3u7.onrender.com`) is certified ready:

1. **Environment Variables Configured in Render Dashboard:**
   ```env
   GST_ENCRYPTION_KEY=[CONFIGURED]
   SANDBOX_API_KEY=[CONFIGURED]
   SANDBOX_API_SECRET=[CONFIGURED]
   SANDBOX_BASE_URL=https://api.sandbox.co.in
   ```
2. **Automated Pipeline Deployment:**
   - Commit pushed to `fix/stage4-12-day6-remediation`.
   - Render staging pipeline executes `collectstatic`, `migrate`, and launches Gunicorn.
3. **Live GSTIN Verification Certified:**
   - Live endpoint tested with GSTIN `27AAACT2727Q1ZW` (Tata Motors Passenger Vehicles Limited).
   - Taxpayer cache and state resolution verified operational.
