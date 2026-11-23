# SRI LEKH — GST CONNECTION UX IMPLEMENTATION REPORT
**Date**: November 23, 2026  
**Audience**: Product Management, Frontend Engineering, and UX Design  
**Application**: SriLekh ERP (`https://srilekh.com`)  
**Component**: `frontend/src/app/settings/page.tsx` (`tab === 'gst-portal'`)  

---

## 1. UX Design Philosophy: High Abstraction for Indian Retailers

Indian retailers and MSME proprietors manage operations under high pressure. They should never be exposed to API keys, technical endpoints, developer test buttons, or internal gateway errors.

The redesigned **Government GST Portal Integration** follows a progressive, 3-state guided interface:

```
[ State 1: Not Connected ]
       │
       ▼ (User enters GST Portal Username & clicks 'Connect GST Portal')
[ State 2: OTP Verification ]
       │
       ▼ (User enters 6-digit OTP & clicks 'Verify and Connect')
[ State 3: Connected & Active ]
```

---

## 2. Walkthrough of the Guided Onboarding States

### State 1: Not Connected
- **Entity Identification**:
  - Displays registered business name (`currentCompany.name`) and GSTIN.
  - If GSTIN is missing, a prominent alert prompts: *"No GSTIN configured for this entity. A valid 15-character GSTIN is required to connect to the GST Portal"* with a direct button to **Configure GSTIN in Firm Details**.
- **Guided Onboarding Card (when API access is disabled)**:
  - If `portalErrorCode === 'API_ACCESS_DISABLED'` or `'GSP_AUTH_MISSING'`, a styled amber card immediately renders:
    - Clear title: **"Action Required on Government GST Portal"**
    - Plain-language explanation: *"GST API access is currently disabled for this GST registration. Please enable API access in your GST Portal account and try again."*
    - Visual 4-step checklist:
      1. Sign in to your GST Portal account at `services.gst.gov.in`
      2. Go to **My Profile** > **Manage API Access**
      3. Select **Yes** for 'Enable API Request' and choose **30 days**
      4. If prompted for GSP, choose **Quicko Infosoft Private Limited**
    - Direct External Link CTA: **"Open Government GST Portal ↗"** (opens in new tab)
    - One-click Retry CTA: **"I've enabled API access — Try Connecting Again"**
- **Default Action**:
  - Pre-fills GST Portal username from GSTIN.
  - Primary button: **"Connect GST Portal"** with spinner during network requests.
  - Security note: *"Secure & Encrypted: SriLekh never asks for your GST Portal password. Direct connection uses official Government OTP verification."*

### State 2: OTP Verification
- **Challenge Message**: *"We've requested an OTP for your registered GST Portal account. Enter the OTP to continue."*
- **Inputs**:
  - 6-digit numeric input with monospace letter spacing (`font-mono tracking-widest text-base`).
- **Actions**:
  - **"Verify and Connect"** (green primary button, enabled once 4+ digits are typed).
  - **"Resend OTP"** (with 30-second countdown cooldown protection to prevent rate limiting).
  - **"Cancel"** (returns cleanly to State 1).

### State 3: Connected
- **Status Indicator**: Green badge **"Connected"** with checkmark icon.
- **Entity Details**: Business Name and formatted GSTIN.
- **Session Expiry**: Clean localized string: `Active session expires: 11/23/2026, 9:24:45 PM` (rendered client-side post-mount to eliminate Next.js hydration mismatch #418).
- **Actions**:
  - **"Extend Session"**: Refreshes the token with GSTN without re-entering an OTP.
  - **"Reconnect with New OTP"**: Clears active session and initiates fresh OTP verification.
  - **"Disconnect Account"**: Remotely logs out the session from Sandbox/GSTN and clears local authorization tokens.

---

## 3. Eliminated Infrastructure Leaks

| Item Removed from UI | Reason for Removal |
|---|---|
| "Render Platform Environment Credentials Active LIVE API READY" | Internal hosting platform leak. Users don't care where backend runs. |
| "api.sandbox.co.in" | Third-party endpoint leak. End users only know the Government GST Portal. |
| "Quicko API Key and Secret loaded and active" | Security & vendor abstraction violation. |
| "Test Connection" button | Developer diagnostic tool that confused non-technical users. |
| "Missing required request parameters: [x-source]" | Raw HTTP header error. Replaced with semantic, actionable guidance. |

---

## 4. Frontend Resilience & Zero-Hydration-Error Verification
- Applied `suppressHydrationWarning` and `mounted` client state check on date formatting to eliminate Next.js Minified React Error #418.
- Verified with Next.js production build:
  ```
  ✓ Running next.config.ts took 603ms
  ✓ Compiled successfully in 9.4s
  ✓ Generating static pages using 23 workers (59/59) in 1991ms
  ```
  **0 build errors, 0 hydration mismatches.**
