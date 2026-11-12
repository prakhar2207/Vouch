# SRI LEKH — STAGE 1.1: INDIA DPDP ACT 2023 & LEGAL READINESS ASSESSMENT

**Audit Date:** 2026-11-12  
**Primary Pages Reviewed:** `/privacy-policy`, `/terms`, `/refund-policy`, `/contact`  
**Regulatory Context Verified:** Digital Personal Data Protection Act, 2023 (India) and MeitY **DPDP Rules, 2025** (notified in November 2025 under a phased commencement schedule: Rules 1, 2, 17–21 for Data Protection Board setup effective immediately in Nov 2025; Rule 4 for Consent Managers at 1 year / Nov 2026; core Data Fiduciary notice, itemized consent, rights, security safeguards, breach intimation, and cross-border obligations at 18 months / May 13, 2027).  
**Disclaimer:** This is an engineering and compliance readiness gap analysis, not formal Indian legal advice or compliance certification.

---

## 1. Classification Legend

- **Statutory (DPDP Act / Rules):** Core statutory/rule obligation (phasing in through May 13, 2027).
- **Best Practice (Pre-Launch / Enterprise Readiness):** Expected standard before general public availability.
- **Owner Input Required:** Missing business/identity/commercial decision.
- **Legal Counsel Review Required:** Clause requiring qualified Indian counsel drafting/sign-off.
- **Technical Gap:** Backend or frontend engineering capability missing or requiring hardening.

---

## 2. DPDP & Indian SaaS Legal Readiness Matrix

| Area | Current Public Page State | Category | Audit Verdict & Specific Gap |
| :--- | :--- | :--- | :--- |
| **1. Data Fiduciary Identity & Contact** | States `SriLekh Platform` & `support@srilekh.com`; legal entity name & physical registered address explicitly marked `[Pending Owner Confirmation]`. | **Statutory (DPDP) / Owner Input Required** | **BLOCKING:** Published policy must state verified legal name (Proprietorship/LLP/Pvt Ltd) and physical registered office address matching KYC. |
| **2. Grievance Officer / Contact Point** | Marked `[Pending Owner & Legal Counsel Confirmation]` in `/privacy-policy` Section 16. | **Statutory (DPDP) / Owner Input Required** | **BLOCKING:** Must designate an individual/Grievance Officer name (or statutory DPO/Grievance email & India contact details) with escalation SLA before commercial launch. |
| **3. Purpose Limitation & Notice Clarity** | Sections 3–6 accurately itemize account, company/bank master, accounting, OCR/bank documents, device/IP data, and functional use without marketing trackers. | **Statutory (DPDP)** | **READY FOR COUNSEL REVIEW:** Itemized notice structure aligns with DPDP itemized-notice approach; counsel must finalize exact consent flow & retention tie-in prior to May 2027 Rule 3 deadline. |
| **4. Third-Party Processor & Cross-Border Disclosures** | Section 8 now explicitly names Vercel, Render, Neon (AWS `ap-southeast-1`), Redis, **Google Gemini API (`google.genai`)**, SMTP/Gmail, optional S3 (`ap-south-1`), and Cashfree/mock GST, plus cross-border notice. | **Statutory (DPDP) / Owner + Counsel + Best Practice** | **CONDITIONAL / COUNSEL REVIEW:** Technical facts are accurate. Owner & counsel must verify signed DPAs and confirm no restricted-country transfers under Section 16 of DPDP Act notifications. |
| **5. Data Principal Rights (Access / Correction / Erasure / Grievance)** | Section 12 directs requests to `support@srilekh.com`; Section 13 states company archival (`is_active=false`) exists while self-serve permanent user deletion is **not** available in UI. | **Statutory (DPDP) / Technical Gap + Owner SLA** | **GAP:** Support manual email handling works pre-launch, but production readiness requires: (a) defined SLA timelines, (b) verified admin erasure procedure across DB & encrypted backup rotation (`BACKUP_RETENTION_DAYS=7`), and (c) roadmap self-serve user deletion/export workflow. |
| **6. Tenant Controller vs Platform Fiduciary Role Clarity** | Sections 4–5 of `/privacy-policy` and Sections 5–7 of `/terms` note that customer/supplier/employee data is entered into isolated tenant workspaces by business users who must hold authority to upload it. | **Legal Counsel Review Required** | **COUNSEL REVIEW NEEDED:** In B2B SaaS, SriLekh acts as a processor (Data Processor on behalf of MSME Data Fiduciary) for party/invoice data, and as Data Fiduciary for SriLekh account/billing data. Counsel should tighten Controller/Processor split wording in `/terms` & `/privacy-policy`. |
| **7. Security Safeguards vs Accuracy** | Section 7 discloses salted password/OTP hashes, JWT rotation, company-scoped permissions, SHA-256 audit hash chaining, and AES/Fernet support on `CompanyGSTConfig` & backups — plus honest caveat on non-`HttpOnly` JS JWT cookies/localStorage. | **Statutory (DPDP) / Technical Gap** | **CONDITIONAL (Honest Today; Hardening Needed):** Disclosure is accurate and free of false ISO/SOC certifications. Moving auth tokens to `HttpOnly` cookies remains an important technical hardening target for DPDP "reasonable security safeguards." |
| **8. Breach Notification Workflow** | No fabricated breach SLA published. | **Statutory (DPDP) / Owner + Counsel** | **GAP FOR FULL LAUNCH:** DPDP Rules require timely intimation to affected Data Principals and the Data Protection Board once effective; owner/counsel must establish incident response & notification SOPs before commercial scale. |
| **9. Children's Data** | Section 14 states platform is strictly B2B (18+) and does not knowingly collect data from children. | **Statutory (DPDP) / Best Practice** | **ACCEPTABLE FOR B2B** *(assuming UI registration terms reinforce 18+ commercial use)*. |
| **10. Terms of Service Commercial & Liability Clauses** | `/terms` Sections 8, 15, 16, 17 clearly mark pricing/billing rules, aggregate monetary liability cap, indemnification review, and exclusive Indian court jurisdiction city as pending owner/counsel review. | **Legal Counsel + Owner Input Required** | **BLOCKING:** Must fill registered jurisdiction city/state, liability cap formula (e.g., fees paid in prior months), indemnity wording, and GST invoicing terms with counsel before accepting paid customers. |
| **11. Account Aggregator (Setu AA) Consent Readiness** | Setu AA is NOT implemented in codebase; `/privacy-policy` Section 8 & `/pricing` make zero false live-feed claims and state Setu AA would only activate future consent-driven integration. | **Best Practice / Pre-Requisite** | **NO PREMATURE CLAIMS (SAFE TODAY):** Dedicated RBI Account Aggregator consent-artifact, revocation, and data-purging clauses must be added before activating Setu AA. |
| **12. No False Certifications** | Zero false claims of ISO 27001, SOC 2, CERT-In audit, or India-only residency anywhere in public pages. | **Best Practice** | **PASS.** |
