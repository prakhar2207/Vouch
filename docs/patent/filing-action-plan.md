# PATENT FILING ACTION PLAN & PRE-DISCLOSURE QUARANTINE PROTOCOL

**Jurisdiction:** Indian Patent Office (IPO)  
**Target:** Securing Priority Date for Vouch Distributed Accounting Convergence Protocol  
**Critical Priority:** MUST COMPLETE BEFORE ANY PUBLIC DISCLOSURE  

---

## 1. Golden Rule of Patent Law: Absolute Novelty

Under Section 13 and Section 29–34 of the Indian Patents Act, 1970, India adheres strictly to the doctrine of **Absolute Novelty**:
> Any public demonstration, YouTube video, public GitHub commit, open-source release, blog post, or commercial marketing prior to the official filing timestamp destroys the novelty of the invention and will lead to irrevocable forfeiture of patent rights.

**Action Required:**
1. Keep the GitHub repository `prakhar2207/Vouch` **PRIVATE** (or ensure that the protocol patent documents and core algorithms are not published in public branches).
2. Do not discuss the specific convergence, compensation, or 4-way Merkle commitment mathematics in public forums or social media until the Indian Patent Office issues the official **Cash Book Receipt (CBR)** with the Application Number.
3. Provide demos to prospective clients or investors only under a signed bilateral Non-Disclosure Agreement (NDA).

---

## 2. Step-by-Step Indian Patent e-Filing Guide (IPO Portal)

The Indian Patent Office provides 24x7 online e-filing via [ipindiaonline.gov.in](https://ipindiaonline.gov.in/epatentfiling/goForLogin/doLogin).

### Step 1: Obtain / Verify Class 3 Digital Signature Certificate (DSC)
- The applicant or registered patent agent must hold a valid Class 3 Digital Signature Certificate (DSC) registered on the IPO portal.

### Step 2: Prepare Statutory Forms
The following forms are prepared using the documents in `docs/patent/`:

| Form | Title | Purpose | Source Document |
|---|---|---|---|
| **Form 1** | Application for Grant of Patent | Administrative details (Applicant name, address, nationality, inventors, title). | Standard IPO template |
| **Form 2** | Provisional Specification | Technical disclosure describing the nature of the invention and technical advancement. | `docs/patent/invention-disclosure.md` |
| **Form 3** | Statement & Undertaking under Section 8 | Details of any foreign filings (state: "None" if first filing in India). | Standard IPO template |
| **Form 5** | Declaration as to Inventorship | Signed declaration by the inventors. | Standard IPO template |
| **Form 28** | (Optional) Proof of Startup / Small Entity | Entitles the applicant to an 80% discount on statutory patent fees (DPIIT recognition certificate). | Company registration |

### Step 3: Statutory Fee Structure

| Entity Category | Official IPO Provisional Filing Fee (e-Filing) |
|---|---|
| **Natural Person / Recognized Startup (DPIIT) / Small Entity (MSME)** | **₹ 1,600** |
| **Other Entities (Large Corporations)** | **₹ 8,000** |

### Step 4: Submission & Instant Priority Timestamp
1. Upload `Form 1`, `Form 2`, `Form 3`, and `Form 5` on the IPO portal.
2. Sign using Class 3 DSC and pay the fee online via Net Banking / UPI.
3. The portal immediately generates the **Cash Book Receipt (CBR)** containing:
   - **Application Number:** e.g., `2026110XXXXX`
   - **Filing Date & Timestamp:** e.g., `02/10/2026 14:30:15 IST`
   - **CBR Number:** Legal proof of patent filing.

Once the CBR is generated, the **Official Priority Date is Legally Secured**. Public disclosure, marketing, and client deployment may then proceed safely.

---

## 3. Post-Filing Timeline (12-Month Roadmap)

```
[Month 0: October 2026]
   File Provisional Patent Application (Form 1 & Form 2)
   --> PRIORITY DATE SECURED
   --> Public marketing and commercial deployments can proceed safely

[Months 1 - 9: Nov 2026 - July 2027]
   Production metrics collection, enterprise client case studies,
   refinement of specific claims and edge cases

[Month 12: By October 2, 2027]
   MANDATORY DEADLINE: File Complete Specification (Form 2)
   Optionally file PCT (Patent Cooperation Treaty) Application
   to preserve international filing rights across 157 countries
   (US, Europe, UK, Singapore, UAE, Japan)
```

---

## 4. Key Artifacts Prepared for Patent Counsel

All technical materials required by patent attorneys are compiled and ready in `docs/patent/`:
1. **[Protocol Architecture Freeze Specification](protocol-architecture-freeze.md)**
2. **[Formal Invention Disclosure](invention-disclosure.md)**
3. **[Indian Prior-Art Search & Patentability Opinion](indian-prior-art-search-report.md)**
4. **[Empirical Benchmarks & Proofs](benchmarks-and-experiments.md)**
5. **[CRDT Algorithm & Invariant Proofs](crdt-algorithm.md)**
6. **[Semantic Reciprocal Compensation Calculus](semantic-compensation.md)**
7. **[4-Way Merkle Roots & Chained Commitments](state-roots-and-commitments.md)**
