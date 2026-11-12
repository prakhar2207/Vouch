# SRI LEKH — STAGE 1.1: CONTACT SAFETY & COMMERCIAL / REFUND REVIEW

**Audit Date:** 2026-11-12  
**Files Reviewed:**  
- [`frontend/src/app/contact/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/contact/page.tsx)  
- [`frontend/src/components/public/ContactForm.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/public/ContactForm.tsx)  
- [`frontend/src/components/public/contact-validation.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/public/contact-validation.ts)  
- [`frontend/src/components/public/contact-validation.test.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/public/contact-validation.test.ts)  
- [`frontend/src/app/pricing/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/pricing/page.tsx)  
- [`frontend/src/app/refund-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/refund-policy/page.tsx)  
- [`frontend/src/app/terms/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/terms/page.tsx)

---

## 1. Contact Page & Dispatch Safety Review

### Verified Architecture
- **No Backend Contact API Exists:** Confirmed no `/contact` POST endpoint exists in Django `urls.py`. Rather than inventing a mock endpoint or showing a fake "Message Sent" toast, `ContactForm` explicitly operates in **Direct Email Dispatch Mode** (`mailto:` prefill + one-click Copy Inquiry Text fallback).
- **Stage 1.1 Hardening Applied:**
  1. **Strict Field Length Limits (`FIELD_MAX_LENGTHS`):** `fullName` (120), `businessEmail` (254), `phone` (30), `businessName` (150), `subject` (150), `message` (1500), enforced both via HTML `maxLength` attributes and JS `validateContactForm`.
  2. **Sanitization (`sanitizeSingleLine` / `sanitizeMultiline`):** Strips NUL/ASCII control characters and collapses CR/LF header-injection characters in single-line inputs before generating `mailto:` links.
  3. **Safe `mailto:` URI Length Cap (`MAX_MAILTO_URI_LENGTH = 1900`):** Prevents browser / Windows Explorer / email-client URL truncation failures on long messages; displays an explicit amber notice (`isMailtoTruncated`) directing users to click **Copy Inquiry Text** for the full text.
  4. **Clear Non-Delivery Warning:** Amber status card reads `"Not yet sent — send this prepared draft using your email application"` and explicitly states `"We cannot guarantee delivery until your email client completes sending."`
  5. **Anti-Spam Traps:** Hidden `company_website` honeypot field (`aria-hidden="true"`, `tabIndex={-1}`) and minimum 2-second mount-to-submit human timing guard (`checkContactAntiSpam`).

### Remaining Contact Page Gaps (Owner Action Required)
- `Registered legal entity name`, `Support Phone`, `Registered Business Address`, and `Support Availability` are marked `[Pending Owner Confirmation]`.
- Future enhancement (post Stage 1.1 approval): If direct form capture without an email app is desired for mobile users, implement a rate-limited, server-validated Django endpoint (`/api/v1/public/contact/`) backed by verified SMTP.

---

## 2. Commercial, Subscription, Razorpay & Refund Review

### Verified Repository State
- Inspected `apps/`, `frontend/src/`, and `config/settings.py`: **Zero subscription plans, INR tier pricing, billing intervals, Razorpay SDKs/keys, webhook endpoints, or trial countdown timers exist.**
- All public pages (`/pricing`, `/terms` Section 8, `/refund-policy` Sections 1–10) were cross-checked to ensure consistency:
  - `/pricing`: Shows **"Pricing Coming Soon — Contact Us for Plans & Onboarding"** with no fabricated INR figures or free-trial promises.
  - `/refund-policy`: Banner and Sections 1, 2, 3, 4, 6, 7, 8, 9, 10 consistently state that online payment checkout (such as Razorpay) is **not active today**, no payments can currently be made, refund eligibility/cancellation/bank timelines are pending owner & payment-partner confirmation, and Section 9 explicitly labels refund submission steps as **"Future Procedure (Applicable Once Billing Launches)"**.

### Razorpay Merchant Onboarding Readiness Gaps
Before applying for live Razorpay Merchant KYC & activating checkout on SriLekh:
1. Publish verified **INR subscription tiers & billing cycles** (monthly/annual + GST applicability) on `/pricing`.
2. Replace all contact placeholders (`/contact`, `/privacy-policy`, `/terms`) with **Legal Entity Name, Physical Address matching GST/Udyam/Bank KYC, Official Phone Number, and Grievance Officer**.
3. Define **Cancellation & Refund SLA rules** in `/refund-policy` (e.g., whether refunds apply, prorating vs fixed window, and standard **5–7 business day** Razorpay/bank credit timeline once confirmed with Razorpay agreement).
4. Clarify **Digital Delivery Policy** in `/refund-policy` & `/terms` (e.g., instant workspace provisioning upon successful Razorpay webhook payment confirmation).
5. Build & audit backend Razorpay order/subscription creation, webhook HMAC signature verification, GST tax invoice issuance, and entitlement enforcement in Django before switching `/pricing` from "Contact Us" to "Subscribe".
