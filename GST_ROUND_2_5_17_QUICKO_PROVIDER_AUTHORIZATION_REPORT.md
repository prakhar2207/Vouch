# SRI LEKH GST — ROUND 2.5.17
# Deliverable 6: Quicko / Sandbox.co.in Provider Authorization Architecture Report

**Repository**: https://github.com/prakhar2207/Vouch  
**Production Application**: https://srilekh.com  
**Audit Date**: November 23, 2026  
**Auditor**: GST API Integration Specialist & Systems Architect  

---

## 1. Provider Identity & Authorization Model

SriLekh connects to GSTN through **Sandbox.co.in** (powered by **Quicko Infosoft Private Limited**), an authorized Goods and Services Tax Suvidha Provider (GSP).

Official References:
- Provider Console: `https://console.sandbox.co.in/`
- Documentation: `https://sandbox-docs.readme.io/reference/gst-taxpayer-authentication`
- Quicko GSP ASP Onboarding Guide: `https://help.quicko.com/portal/en/kb/articles/onboarding-as-an-asp-with-quicko-gsp`

### GSP & ASP Identity Mapping on Government GST Portal:
- **GSP Legal Name**: `Quicko Infosoft Private Limited`
- **ASP Model**: Multi-tenant Application Service Provider (ASP) operating via Quicko GSP gateway.

---

## 2. Taxpayer Authorization Workflow on Government GST Portal

For a business owner or accountant to connect their GST registration to SriLekh via Quicko:

1. **Sign in to Official GST Portal**:
   - URL: `https://services.gst.gov.in`
2. **Navigate to API Settings**:
   - `My Profile` > `Manage API Access`
3. **Enable API Access**:
   - Toggle **Enable API Request** to **Yes**.
   - Select **Duration**: **30 Days** (or 6 hours / 365 days).
4. **GSP Selection**:
   - If prompted for GSP selection, choose **Quicko Infosoft Private Limited**.

---

## 3. Provider Contract & Required Headers

Every request to `api.sandbox.co.in` strictly injects the documented authentication headers:
- `x-api-key`: Sandbox API Key (loaded from server environment or encrypted config).
- `authorization`: JWT access token generated via `POST /authenticate`.
- `x-api-version`: `2.0` (or configured API version).
- `x-source`: `custom` / configured ASP source identifier.
- `Accept`: `application/json`

Internal API keys and secrets remain **strictly on the backend server** and are never transmitted to client browsers or mobile devices.

---

## 4. Phase 6 Certification

**STATUS: CERTIFIED & COMPLIANT**  
The GSP/ASP authorization mapping and documentation references are established and aligned with production requirements.
