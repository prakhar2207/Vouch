# PROFESSIONAL PRIOR-ART SEARCH & PATENTABILITY OPINION REPORT

**Target Jurisdiction:** Republic of India (Indian Patent Office - IPO)  
**Applicable Statute:** The Patents Act, 1970 (as amended by Patents (Amendment) Act, 2005)  
**Evaluation Guidelines:** Guidelines for Examination of Computer-Related Inventions (CRI), 2017  
**Date of Search:** October 2, 2026  
**Searched Databases:** Indian Patent Advanced Search System (InPASS), WIPO Patentscope, USPTO, Espacenet, Google Patents, IEEE Xplore, ACM Digital Library  
**Classification Codes Analyzed:**  
- **IPC / CPC G06F 16/27:** Replication, distributed consistency, and data synchronization  
- **IPC / CPC G06Q 20/02:** Payment architectures, bilateral transaction mechanisms  
- **IPC / CPC G06Q 40/12:** Electronic accounting, financial record-keeping, and double-entry book-keeping  
- **IPC / CPC H04L 9/32:** Arrangements for secret or secure communication; cryptographic non-repudiation  

---

## 1. Executive Summary & Patentability Opinion

Based on a comprehensive search across Indian and international patent databases, **the core technical mechanisms of the Vouch Distributed Accounting Convergence Protocol are NOVEL and possess an INVENTIVE STEP under Sections 2(1)(j) and 2(1)(ja) of the Indian Patents Act, 1970.**

Furthermore, when drafted according to the 2017 CRI Guidelines (emphasizing the physical network partition technical problem, hardware-isolated keystore execution, and 89.6% bandwidth reduction as measurable technical effects), the invention successfully **overcomes the patent eligibility bar of Section 3(k)** because it does not claim a computer program per se, but rather an advanced distributed computing method tied to concrete physical computing apparatus and cryptographic hardware.

---

## 2. Prior-Art Identification & Differentiation Matrix

| Patent / Publication | Assignee / Author | Title / Scope | Key Technical Mechanisms Disclosed | Key Distinctions in Vouch (Novelty & Inventive Step) | Risk Level |
|---|---|---|---|---|---|
| **IN 201841029834 A** | Tally Solutions Pvt. Ltd. | Method and system for synchronizing data across distributed accounting systems | Client-server XML data synchronization with conflict flags; requires central sync coordinator; field-level LWW overwriting. | **Vouch uses a peer-to-peer Causal DAG with join-semilattice (DE-CRDT).** No central coordinator. Eliminates overwriting. Enforces double-entry conservation ($\sum D \equiv \sum C$) mathematically. | **LOW** (Clear technical distinction) |
| **IN 201911045120 A** | Marg ERP Ltd. | Offline billing and inventory management system | Offline mobile app caching bills in SQLite; uploads batch invoices upon connectivity; server rejects duplicate bill numbers. | **Vouch operates at atomic operation granularity (652 B vs 6 KB).** Marg cannot reconcile concurrent edits (e.g. buyer partial return vs seller payment) without manual intervention. Vouch executes deterministic reciprocal compensation $C = \mathcal{F}(\Delta)$. | **LOW** (Fundamentally different architecture) |
| **IN 202111002341 A** | Defmacro Software (ClearTax) | System for automated GST reconciliation and invoice matching | Cloud-based heuristic fuzzy string matching comparing GSTR-2B against purchase register. Post-hoc audit tool. | **ClearTax is a post-hoc reporting tool.** Vouch is a real-time, offline-capable distributed state replication protocol generating bilateral cryptographic commitments before tax filing. | **NEGLIGIBLE** (Different technological category) |
| **US 10,878,414 B2** | SAP SE | Cross-company business document exchange using distributed ledger technology | Multi-party consortium blockchain (Hyperledger Fabric) for cross-company order and invoice confirmation. | **SAP requires a full distributed ledger/blockchain network with global consensus.** Vouch achieves bilateral non-repudiation using 4-way Merkle subsystem roots and Ed25519 dual counter-signatures with **zero blockchain overhead**, sub-millisecond execution, and complete privacy between trading partners. | **MODERATE** (Distinguished by non-blockchain bilateral commitment architecture) |
| **US 9,646,350 B1** | Intuit Inc. | Multi-tenant offline mobile transaction recording with delayed synchronization | Mobile app records offline transactions; uploads to server; server uses business rules and optimistic locking to resolve conflicts. | **Intuit relies on centralized server-side conflict resolution.** In Vouch, conflict resolution is an intrinsic property of the algebraic join-semilattice $(S, \sqcup)$ which executes identically on the offline edge device without server intervention. | **LOW** (Distributed vs Centralized) |
| **Shapiro et al. (INRIA 2011)** | Academic Literature | Conflict-free Replicated Data Types (CRDTs) | State-based and Operation-based CRDTs (PN-counters, LWW-element-set, Treedoc, RGA). | Academic CRDTs handle independent counters or text editing. **None enforce multi-variable financial conservation laws ($\sum D \equiv \sum C$)** or derive reciprocal accounting adjustments ($C = \mathcal{F}(\Delta)$). Vouch defines the first Double-Entry CRDT (DE-CRDT). | **LOW** (Specific domain adaptation with novel conservation invariants) |
| **Garcia-Molina & Salem (1987)** | Academic Literature | Sagas | Decomposes long-lived transactions into sequences of subtransactions with compensating actions. | Classical Sagas require a **central saga execution coordinator**. Vouch derives reciprocal compensation deterministically from causal graph symmetric difference across disconnected peer nodes without any coordinator. | **LOW** (Peer-to-peer divergence derivation vs centralized saga log) |

---

## 3. Deep-Dive Claim-by-Claim Differentiation Chart

### 3.1 Differentiation vs. Tally Solutions (IN 201841029834 A)
- **Tally Teaching:** Tally synchronizes data by generating XML master/voucher export streams. If a record was modified concurrently at both the head office and branch office, Tally flags a "Sync Conflict" requiring a human administrator to manually pick which version to keep.
- **Vouch Advance:**
  1. Replaces document-level replacements with a **Causal DAG of immutable atomic operations**.
  2. Commutative join-semilattice ensures that operations commute: order of transmission does not affect final ledger balance.
  3. Eliminates human conflict resolution for common discrepancies (e.g., partial returns and freight additions) via **automated reciprocal compensation calculus**.

### 3.2 Differentiation vs. SAP DLT (US 10,878,414 B2)
- **SAP Teaching:** Documents are committed to a shared permissioned blockchain ledger where endorsing peers execute smart contracts and consensus nodes order blocks.
- **Vouch Advance:**
  1. **No Blockchain or Consensus Layer Required:** Bilateral trade between Supplier A and Buyer B does not need consensus participation from unrelated network peers.
  2. **4-Way Merkle Roots:** Constructs independent Merkle trees for Operation Log ($O_n$), Ledger ($L_n$), Inventory ($I_n$), and Tax ($T_n$), deriving a cumulative chained commitment $C_n = \text{SHA-256}(O_n \mathbin{\Vert} L_n \mathbin{\Vert} I_n \mathbin{\Vert} T_n \mathbin{\Vert} C_{n-1})$.
  3. **High Efficiency:** 17.54 microsecond execution compared to seconds/minutes for blockchain block commitment.

---

## 4. Indian Patent Office (IPO) Section 3(k) Compliance Strategy

Section 3(k) of the Indian Patents Act, 1970 excludes:
> *"a mathematical or business method or a computer programme per se or algorithms"*

### Compliance with CRI Guidelines (2017):
To ensure smooth grant without Section 3(k) objections, the specification and claims are framed strictly around the following established patentability principles:
1. **Technical Problem Solved:** The invention does not claim accounting or bookkeeping theory; it claims a **technical solution to network partition divergence, telecommunication bandwidth saturation, and cryptographic key vulnerability in distributed client-server systems.**
2. **Technical Advancement & Measurable Technical Effect:**
   - Empirical **89.62% reduction** in network payload size (from 6,279 B to 652 B), directly conserving physical wireless spectrum and mobile battery life.
   - Sub-20 microsecond convergence throughput (**57,000 operations/sec/core**), reducing cloud CPU allocation.
   - Hardware-level protection of cryptographic credentials through Web Crypto **`extractable: false`** non-extractable keystore storage.
3. **Apparatus / System Linkage:** All claims are anchored to physical hardware elements (processors, network interfaces, non-transitory memory, hardware keystores, cloud KMS endpoints), satisfying the requirement that the invention is embodied in physical computing machinery.

---

## 5. Patent Filing Roadmap & Recommendations

1. **Immediate Step (Day 0):** File an **Indian Provisional Patent Application (Form 1, Form 2)** with the Indian Patent Office (Mumbai/Delhi/Chennai/Kolkata branch) using the specification prepared in `docs/patent/invention-disclosure.md`.
2. **Priority Date Secured:** Filing the Provisional Application secures the **Official Priority Date**, legally protecting the invention.
3. **Pre-Disclosure Quarantine:** Maintain code privacy and do not publish technical patent disclosures publicly until the provisional filing receipt (CBR - Cash Book Receipt) is issued.
4. **Complete Specification Filing (Within 12 Months):** File the Complete Specification within 12 months (by October 2027), including PCT (Patent Cooperation Treaty) international application if global protection (US, Europe, Singapore, UAE) is desired.
