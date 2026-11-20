# SRI LEKH — STAGE 1.2.6 LEGAL & STATUTORY OWNER INPUT REGISTER

**Assessment Date:** 2026-11-12  
**Target Legal Domains:** Indian Information Technology Act (2000), Digital Personal Data Protection Act (DPDP 2023), Companies Act (2013), Central Goods and Services Tax Act (2017), Consumer Protection (E-Commerce) Rules (2020), and Google Play Developer Policies  
**Certification Verdict:** **OWNER APPROVAL REQUIRED (OA-02)**  

---

## 1. Executive Summary

To comply with Google Play Developer Program policies, Indian statutory e-commerce regulations, and financial bookkeeping laws, SriLekh's public compliance pages (`/contact`, `/privacy-policy`, `/terms`, `/refund-policy`) must display accurate legal entity details rather than placeholder text.

An automated scan of the frontend repository revealed **12 explicit `[Pending Owner Confirmation]` placeholders**.

These 12 placeholders have been consolidated into an actionable **10-Point Legal Questionnaire**. Once the owner provides the answers to these 10 fields, an automated patch can be applied to completely eliminate all placeholder text.

---

## 2. The 10-Point Legal Questionnaire

| # | Field Name | Statutory / Policy Purpose | Code Locations | Example Valid Value | Owner Input |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Q-01** | **Registered Legal Entity Name** | Full legal name of the incorporated company or registered proprietorship. Required by Google Play & IT Rules. | `contact/page.tsx:76`<br>`privacy-policy/page.tsx:225`<br>`terms/page.tsx:168` | *SriLekh Technologies Private Limited* (or *[Proprietor Name] t/a SriLekh*) | `[Pending Owner Input]` |
| **Q-02** | **Registered Office Physical Address** | Complete physical address with city, state, and PIN code. Required for legal notices and Play Console verification. | `contact/page.tsx:97`<br>`privacy-policy/page.tsx:390` | *Plot No. 12, Industrial Area, Kanpur, Uttar Pradesh - 208001, India* | `[Pending Owner Input]` |
| **Q-03** | **Official Business Support Phone** | Direct telephone/mobile contact number for consumer grievance and billing support. | `contact/page.tsx:86` | *+91 98765 43210* | `[Pending Owner Input]` |
| **Q-04** | **Official Business Support Hours** | Operating days and working hours for live customer service and support tickets. | `contact/page.tsx:108` | *Monday – Saturday, 9:30 AM – 6:30 PM IST* | `[Pending Owner Input]` |
| **Q-05** | **Grievance Officer Name** | Statutory Grievance Redressal Officer designated under Rule 5(9) of the IT (Reasonable Security Practices) Rules, 2011. | `privacy-policy/page.tsx:390` | *Mr. Prakhar Srivastava* | `[Pending Owner Input]` |
| **Q-06** | **Grievance Officer Direct Email** | Official email address specifically dedicated to statutory grievances and data deletion escalation. | `privacy-policy/page.tsx:390` | *grievance@srilekh.com* | `[Pending Owner Input]` |
| **Q-07** | **Governing Law Jurisdiction** | City and State where courts have exclusive jurisdiction for disputes arising under the Terms of Service. | `terms/page.tsx:251` | *Kanpur, Uttar Pradesh, India* | `[Pending Owner Input]` |
| **Q-08** | **Statutory Data Retention Window** | Mandated retention period for financial accounting, invoices, and audit logs before purging. | `privacy-policy/page.tsx:347` | *8 years (as mandated by Section 128 of the Companies Act, 2013 and Section 36 of the CGST Act, 2017)* | `[Pending Owner Input]` |
| **Q-09** | **Cross-Border Cloud Processing Confirmation** | Confirmation of third-party cloud data center locations (AWS US-East-2 Ohio, Neon AWS Ohio, Render EU/US). | `privacy-policy/page.tsx:265` | *Amazon Web Services (US East - Ohio) and Render Services Inc. (US/EU) under Standard Contractual Clauses (SCC)* | `[Pending Owner Input]` |
| **Q-10** | **Refund & Cancellation Policy Windows** | Formal policy on paid subscription cancellations and refund eligibility window. | `refund-policy/page.tsx:67, 81, 90` | *Refund window: 7 calendar days from initial subscription. Cancellation notice: 15 days prior to next billing date. Free trial: 14 days.* | `[Pending Owner Input]` |

---

## 3. Statutory & Google Play Rejection Risks If Left Unresolved

1. **Google Play Store Policy (Section 4.8 & Privacy Policy Requirements):**
   - Apps collecting business or personal data must link to an active privacy policy clearly identifying the entity or developer responsible.
   - Using placeholders or generic template text triggers automated and manual review rejection under "Inaccurate or Misleading Privacy Disclosures".
2. **Indian Consumer Protection (E-Commerce) Rules, 2020 (Rule 4):**
   - Every e-commerce entity operating in India must prominent display its legal entity name, principal geographic address, website, and contact details (including phone and email) for consumers.
3. **IT Act 2000 / IT Rules 2011 (Grievance Redressal):**
   - Failure to publish the name and contact details of a Grievance Officer constitutes a statutory infraction under Section 79 / IT Rules, forfeiting intermediary safe-harbor protections.

---

## 4. Automation Patch Ready for Deployment

Once the owner fills in the 10 fields above, the following replacement routine will be executed to replace every placeholder across the codebase:

```bash
# Automated substitution script target:
frontend/src/app/contact/page.tsx
frontend/src/app/privacy-policy/page.tsx
frontend/src/app/terms/page.tsx
frontend/src/app/refund-policy/page.tsx
```

All 4 pages have already been verified to render valid semantic HTML with responsive mobile views.
