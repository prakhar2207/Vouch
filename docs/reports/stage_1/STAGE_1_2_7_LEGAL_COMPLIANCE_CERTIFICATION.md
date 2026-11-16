# SRI LEKH — STAGE 1.2.7 LEGAL & STATUTORY COMPLIANCE CERTIFICATION

**Assessment Date:** 2026-11-12  
**Target Statutory Frameworks:**  
- Indian Information Technology Act (2000) & IT (Intermediary Guidelines and Digital Media Ethics Code) Rules (2021)  
- Consumer Protection (E-Commerce) Rules (2020)  
- Digital Personal Data Protection Act (DPDP Act, 2023)  
- Section 128 of the Companies Act (2013) & Section 36 of the CGST Act (2017) (8-Year Bookkeeping Retention)  
- Google Play Developer Program Policies (Privacy Policy & Account Deletion Requirements)  
**Certification Verdict:** **OWNER APPROVAL REQUIRED (OA-02)**  

---

## 1. Executive Summary

Public compliance pages must accurately represent the legal entity operating the SriLekh platform. Under both Indian law and Google Play Store policies, publishing placeholder text or generic template strings triggers immediate store rejection and regulatory penalties.

A scan of the frontend repository identified **12 explicit `[Pending Owner Confirmation]` placeholders** across 4 statutory pages.

To ensure seamless resolution without multiple back-and-forth exchanges, these 12 placeholders are structured into a concise **10-Point Legal Questionnaire**. An automated code patch is ready to replace all placeholders across the codebase as soon as the owner provides verified values.

---

## 2. The 10-Point Legal Questionnaire

| # | Field Name | Statutory Purpose & Rule | Code Locations | Example Valid Value | Owner Input |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Q-01** | **Registered Legal Entity Name** | Full legal name of company/proprietorship. Required by Google Play & IT Rules. | `contact/page.tsx:76`<br>`privacy-policy/page.tsx:225`<br>`terms/page.tsx:168` | *SriLekh Technologies Private Limited* (or *[Proprietor Name] t/a SriLekh*) | `[Pending Owner Input]` |
| **Q-02** | **Registered Office Physical Address** | Complete physical office address with PIN code. Required under Consumer Protection Rules, 2020. | `contact/page.tsx:97`<br>`privacy-policy/page.tsx:390` | *Plot No. 12, Industrial Area, Kanpur, Uttar Pradesh - 208001, India* | `[Pending Owner Input]` |
| **Q-03** | **Official Business Support Phone** | Direct telephone/mobile contact number for consumer grievance and billing support. | `contact/page.tsx:86` | *+91 98765 43210* | `[Pending Owner Input]` |
| **Q-04** | **Official Business Support Hours** | Operating days and working hours for live customer service and support tickets. | `contact/page.tsx:108` | *Monday – Saturday, 9:30 AM – 6:30 PM IST* | `[Pending Owner Input]` |
| **Q-05** | **Grievance Officer Name** | Statutory Grievance Redressal Officer designated under Rule 5(9) of the IT Rules, 2011. | `privacy-policy/page.tsx:390` | *Mr. Prakhar Srivastava* | `[Pending Owner Input]` |
| **Q-06** | **Grievance Officer Direct Email** | Official email address specifically dedicated to statutory grievances and data deletion escalation. | `privacy-policy/page.tsx:390` | *grievance@srilekh.com* | `[Pending Owner Input]` |
| **Q-07** | **Governing Law Jurisdiction** | City and State where courts have exclusive jurisdiction for disputes arising under the Terms of Service. | `terms/page.tsx:251` | *Kanpur, Uttar Pradesh, India* | `[Pending Owner Input]` |
| **Q-08** | **Statutory Data Retention Window** | Mandated retention period for financial accounting, invoices, and audit logs before purging. | `privacy-policy/page.tsx:347` | *8 years (as mandated by Section 128 of the Companies Act, 2013 and Section 36 of the CGST Act, 2017)* | `[Pending Owner Input]` |
| **Q-09** | **Cross-Border Cloud Processing Confirmation** | Confirmation of third-party cloud data center locations (AWS US-East-2 Ohio, Neon AWS Ohio, Render EU/US). | `privacy-policy/page.tsx:265` | *Amazon Web Services (US East - Ohio) and Render Services Inc. (US/EU) under Standard Contractual Clauses (SCC)* | `[Pending Owner Input]` |
| **Q-10** | **Refund & Cancellation Policy Windows** | Formal policy on paid subscription cancellations and refund eligibility window. | `refund-policy/page.tsx:67, 81, 90` | *Refund window: 7 calendar days from initial subscription. Cancellation notice: 15 days prior to next billing date. Free trial: 14 days.* | `[Pending Owner Input]` |

---

## 3. Statutory Risks of Unresolved Placeholders

1. **Google Play Rejection (Inaccurate Privacy Policy):**
   Google Play automated review bots crawl the declared Privacy Policy URL. If placeholder strings (e.g. `[Pending Owner Confirmation]`) are detected in place of entity or contact information, the submission is rejected under Section 4.8.
2. **Loss of IT Act Intermediary Safe Harbor:**
   Section 79 of the Indian IT Act requires publishing the Grievance Officer's name and contact details. Failure to publish forfeits intermediary liability protections.
3. **Consumer Protection E-Commerce Infraction:**
   Rule 4 of the Consumer Protection (E-Commerce) Rules, 2020 mandates conspicuous publication of legal name, physical geographic address, website, and phone contact on digital portals.

---

## 4. Automated Patch Execution Plan

Upon receiving the owner's answers to `Q-01` through `Q-10`:
1. Automated string replacement will update:
   - [`frontend/src/app/contact/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/contact/page.tsx)
   - [`frontend/src/app/privacy-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/privacy-policy/page.tsx)
   - [`frontend/src/app/terms/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/terms/page.tsx)
   - [`frontend/src/app/refund-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/refund-policy/page.tsx)
2. `npm run build` will rebuild the production pages.
3. Zero placeholder strings will remain in the codebase.
