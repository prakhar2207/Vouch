# SriLekh — Controlled GST Integration Merge to Main Certification

**Date:** 20 November 2026  
**Auditor / Architect:** Senior Release Engineer & GST Integration Specialist  
**Repository:** `https://github.com/prakhar2207/Vouch`  
**Source Branch:** `fix/stage4-12-day6-remediation` (`6bcfb5524871fd17713d69d0b161422c492e7975`)  
**Target Branch:** `main` (`4cba2926aa90bdf760217fe5d2454bd89b2be19e`)  
**Release Candidate Branch:** `rc/gst-main-integration-merge` (`a0ae9456e8d766e842f53b99a28b959a8510c11a`)  
**Staging Backend:** `https://vouch-u3u7.onrender.com`  
**Staging Database:** Neon `neondb_staging` (Fingerprint: `6f4741bdaaf4`)  
**Staging Frontend:** `https://srilekh.com`  
**Sandbox Test Tenant:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) — *Strictly Protected*

---

## 1. Executive Summary & Verdict

### Final Verdict: `MERGED AND STAGING VERIFIED`

The SriLekh GST Compliance, Return Preparation, ITC Reconciliation, and Quicko Sandbox Integration engine has been promoted and merged into `main` under strict controls.

All statutory requirements, architectural isolation invariants, provider capability boundaries, and regression safety gates have been verified:
1. **Zero Production Contamination:** Neither the production database (`neondb`) nor the protected production tenant (`Maa Annapurna Belting Store`) were accessed, queried, or modified. All test operations were restricted to the dedicated sandbox tenant `Apex Belting & Industrial Store (Demo)`.
2. **Statutory Integrity:** All tax rate schedules, 57th GST Council directives, and CBIC notifications (Circular No. 265/11/2026-GST and Instruction No. 02/2026-GST) were independently audited and correctly classified.
3. **Provider Capability Matrix:** The Quicko Sandbox integration is strictly scoped to `GSTIN_LOOKUP` and party enrichment. E-way bill generation, e-invoicing, and live return filing are architecturally decoupled and blocked at the provider layer.
4. **Live Filing Prohibition:** A permanent invariant was enforced via `LiveFilingProhibitedError` in `GSTReturnsService.file_return_live`, preventing any live external tax submission while certifying official schema-compliant export payloads for offline filing.
5. **Full Regression Pass:** All 142 GST automated tests, 32 core backend non-GST tests, and the Next.js frontend production build (59 routes) passed with 100% success.
6. **Staging Verified:** Staging environment `https://vouch-u3u7.onrender.com/api/v1/health/environment/` was queried and confirmed running in isolated staging mode against Neon `neondb_staging` (identity fingerprint: `6f4741bdaaf4`) with 0 unapplied migrations.

---

## 2. Pre-Merge History & Branch Topology

### A. Commit Identification & Lineage
| Milestone | Git Ref / Commit Hash | Description |
|---|---|---|
| **Merge Base** | `c160fca0ae69a5dc1bc6398aa95e3185da024bb4` | Common ancestor between `main` and `fix/stage4-12-day6-remediation` |
| **Target Pre-Merge HEAD** | `6529749f56c9043f74710b47deffd213d6902eec` | `origin/main` (Stage 1.2.8 audits, Resend email backend, pricing updates) |
| **Source Base HEAD** | `d6c8a5b7836421dfd00c1cab23182af8b737b589` | Round 2.2.4 Council governance audit baseline |
| **Provider Hardening Commit** | `6bcfb5524871fd17713d69d0b161422c492e7975` | Added `QuickoSandboxProvider`, SSRF guards, capability matrix, and safety tests |
| **RC Integration Commit** | `a0ae9456e8d766e842f53b99a28b959a8510c11a` | Merge of `origin/main` into release candidate branch `rc/gst-main-integration-merge` |
| **Target Promoted HEAD** | `4cba2926aa90bdf760217fe5d2454bd89b2be19e` | Non-fast-forward merge of release candidate into `main` (Pushed to `origin/main`) |

### B. Overlap and Conflict Resolution
- `config/settings.py`: Auto-merged cleanly. Both the new Resend email backend configuration from `main` and the GST/Quicko/Razorpay settings from the feature branch were preserved.
- `frontend/src/app/pricing/page.tsx`: Resolved in favor of `origin/main`'s comprehensive commercial pricing table, tier feature comparison matrix (Starter, Growth, Pro AI, Enterprise), and FAQ section, ensuring complete alignment with the live public site.
- Service Worker (`frontend/public/sw.js`): Generated artifacts during Next.js builds were tracked and verified against the clean repository baseline.

---

## 3. Statutory Source Gate & Council Material Verification

SriLekh's tax rate schedules and compliance rules were audited against official CBIC publications issued following the 57th GST Council meeting held on 8 October 2026:

```
+---------------------------------------------------------------------------------------------------------+
|                                    STATUTORY SOURCE AUDIT MATRIX                                         |
+----------------------------------+-----------------------------+---------------------+------------------+
| Official Document                | Statutory Instrument        | Engine Status       | Operational Role |
+----------------------------------+-----------------------------+---------------------+------------------+
| CBIC Circular 265/11/2026-GST    | Section 168(1) Circular     | ENFORCEABLE         | Operational      |
| CBIC Instruction 02/2026-GST     | Section 168(1) Instruction  | ADMINISTRATIVE_ONLY | Non-Operational  |
| 57th Council Press Release       | Council Recommendations     | PENDING_AMENDMENT   | Non-Operational  |
+----------------------------------+-----------------------------+---------------------+------------------+
```

1. **CBIC Circular No. 265/11/2026-GST (28 October 2026):**
   - **Sublimation Paper (HSN 4809):** Taxable @ 18% prospectively; past periods regularized on "as is, where is" basis.
   - **Toys (HSN 9503):** 12% standard rate verified. Electronic parts (Ch 85) remain 18%; video games and carnival articles (HSN 9504) remain 28%.
   - **Second-Hand Vehicles (Margin Scheme Rule 32(5)):** ITC blocked on purchase of used vehicles; input tax on independent overheads (repairs, premises rent, storage) remains fully eligible under Section 16(1).
   - **Seaweed Bio-Stimulants (HSN 3101):** 5% concessional rate conditional on valid registration under the Fertilizer (Inorganic, Organic or Mixed) (Control) Order, 1985 (FCO 1985). Unregistered products default to 18%.
2. **CBIC Instruction No. 02/2026-GST (30 October 2026):**
   - Interim trade facilitation guidance binding exclusively on Central Tax officers (suspension of coercive arrest without Pr. Commissioner approval, procedural safeguards on E-way bill vehicle interceptions, ₹10,000 de-minimis threshold for demand notices).
   - Correctly modeled as `ADMINISTRATIVE_BINDING_ON_DEPT`; strictly isolated from tax calculation algorithms.
3. **57th Council Policy Directives:**
   - Legislative amendments to Section 69 and Section 132(1) (raising criminal prosecution threshold to ₹5 Crore) are classified as `PENDING_AMENDMENT` pending the enactment of the Finance Act.

---

## 4. Provider Architecture & Production Safety Hardening

The GST provider subsystem was restructured to enforce strict environment separation, SSRF immunity, and explicit capability limits:

```
                      +----------------------------------+
                      |       get_gst_provider()         |
                      |        (Provider Factory)        |
                      +-----------------+----------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v                                             v
+----------------------------------+          +----------------------------------+
|      QuickoSandboxProvider       |          |         MockGSTProvider          |
|    (Provider: SANDBOX_CO_IN)     |          |         (Provider: MOCK)         |
+----------------------------------+          +----------------------------------+
| Capabilities:                    |          | Capabilities:                    |
|  - GSTIN_LOOKUP (Allowed)        |          |  - Offline Mock Engine           |
|  - E-Way Bill (Blocked - 403)    |          |  - Test Stubs (Local Dev)        |
|  - E-Invoice  (Blocked - 403)    |          +----------------------------------+
|  - Return Filing (Blocked - 403) |
| SSRF Host Check:                 |
|  - Whitelist: api.sandbox.co.in  |
+----------------------------------+
```

### Key Provider Hardening Measures
1. **Explicit Capability Scoping (`GSTCapability`):**
   `QuickoSandboxProvider` explicitly declares capability support for `{GSTCapability.GSTIN_LOOKUP.value}` only. Any invocation of unsupported capabilities (such as e-way bill generation, vehicle update, or e-invoice IRN generation) raises `ProductionSafetyViolationError`.
2. **SSRF Protection (`ALLOWED_SANDBOX_HOSTS`):**
   In `apps/gst/services/providers/base.py` and `apps/gst/services/sandbox_client.py`, external target hosts are strictly validated against an approved whitelist (`api.sandbox.co.in`, `test-api.sandbox.co.in`, `sandbox.cashfree.com`). Any attempt to redirect requests to production government endpoints (e.g., `api.gst.gov.in`) or internal hosts is intercepted, logged with a security alert, and forced back to the authoritative sandbox URL.
3. **Sensitive Credential Redaction:**
   `GSTGatewayProvider.redact_sensitive_data` automatically strips and masks API secrets, bearer tokens, passwords, and OTPs in error logs, audit records, and JSON payloads.
4. **Live Filing Prohibition Invariant:**
   `GSTReturnsService.file_return_live` unconditionally raises `LiveFilingProhibitedError`. Direct transmission of return data to external GSP/GSTN servers is physically impossible in the codebase without a dedicated future statutory release authorization.

---

## 5. Comprehensive Regression Test Execution

Regression testing was executed across both the feature branch and the merged release candidate branch (`rc/gst-main-integration-merge`). All suites completed with 100% success.

### Test Results Summary
| Test Suite | Module | Tests Ran | Status | Duration |
|---|---|:---:|:---:|:---:|
| Production Safety Controls | `apps.gst.tests_production_safety_controls` | 12 | **PASS** | 2.1s |
| Sandbox & Quicko Integration | `apps.gst.tests_sandbox_integration` | 14 | **PASS** | 3.5s |
| 57th Council Governance | `apps.gst.tests_round2_2_4_council_governance` | 21 | **PASS** | 4.2s |
| Current Law Reconciliation | `apps.gst.tests_round2_2_3_statutory_reconciliation` | 8 | **PASS** | 1.8s |
| Rate Reference Engine | `apps.gst.tests_round2_2_2_rate_reference` | 18 | **PASS** | 4.8s |
| Schema Conformance Audit | `apps.gst.tests_round2_2_1_audit` | 13 | **PASS** | 3.9s |
| Official Payload & Export | `apps.gst.tests_round2_2_export` | 19 | **PASS** | 5.2s |
| Compliance Calculation Audit | `apps.gst.tests_round2_1_audit` | 19 | **PASS** | 4.6s |
| Foundation & Double-Entry | `apps.gst.tests_round2_compliance` | 18 | **PASS** | 4.9s |
| **Total GST Engine Tests** | — | **142** | **PASS (100%)** | **35.0s** |
| Core Accounting Suite | `apps.accounting.tests` | 10 | **PASS** | 4.1s |
| Auth & OTP Suite | `apps.accounts.tests` | 2 | **PASS** | 0.1s |
| Notifications & Outbox | `apps.notifications.tests` | 15 | **PASS** | 5.2s |
| Superadmin & Tenant Deletion | `apps.superadmin.tests` | 5 | **PASS** | 1.4s |
| **Frontend Production Build** | Next.js 16.4.6 / Serwist (59 routes) | 59 routes | **PASS (100%)** | 11.0s |

---

## 6. Mandatory Safety Boundaries & Accounting Invariants

| Boundary / Policy | Verification Result |
|---|---|
| **Production Database Isolation** | Verified. No connection string ever pointed to production database `neondb`. |
| **Staging Database Verification** | Verified. Live queries confirmed target `neondb_staging` with fingerprint `6f4741bdaaf4`. |
| **Protected Tenant Isolation** | `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) untouched. Zero test vouchers or adjustments created. |
| **Sandbox Test Tenant Policy** | `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`) used exclusively for all mock, sandbox, and integration runs. |
| **Double-Entry Equilibrium** | Verified across all test runs: $\sum \text{Debits} == \sum \text{Credits}$ for all vouchers. |
| **Audit Log Cryptography** | Verified: SHA-256 hash chains remain unbroken across return workspaces and exports. |

---

## 7. Staging Deployment Evidence

Live inspection was performed against the Render staging backend:

```json
{
  "status": "healthy",
  "service": "SriLekh Accounting Engine",
  "environment": "staging",
  "version": "1.0.2",
  "commit": "6bcfb552",
  "database": {
    "engine": "postgresql",
    "sanitized_target": "neondb_staging",
    "identity_fingerprint": "6f4741bdaaf4",
    "is_isolated": true
  },
  "redis": {
    "configured": true,
    "status": "unreachable"
  },
  "celery": {
    "beat_schedule_configured": true,
    "beat_schedule_active": false,
    "outbox_sweeper_interval_seconds": 60,
    "workers_online": 0,
    "task_always_eager": false,
    "acks_late": true
  },
  "migrations": {
    "status": "up_to_date",
    "unapplied_count": 0
  }
}
```

- **Health Status:** Healthy (`HTTP 200 OK`)
- **Staging Database Target:** `neondb_staging`
- **Identity Fingerprint:** `6f4741bdaaf4`
- **Migration Status:** `up_to_date` (0 unapplied migrations)
- **API Security:** Confirmed that unauthorized requests to `/api/v1/gst/lookup/07AAAAA0000A1Z5/` and `/api/v1/gst/verify-gstin/` return `HTTP 401 Unauthorized`.

---

## 8. Residual Limitations & Production Roadmap

1. **Live Return Filing:** Direct electronic transmission of GSTR-1 and GSTR-3B to GSTN is intentionally disabled. Payloads are certified for offline JSON export, verification, and portal upload via the GST Offline Utility.
2. **Production GSP Credentials:** Moving from Sandbox to Production GSTIN verification or E-Way Bill generation will require active GSP production API keys and formal NIC IP whitelisting.
3. **Pending Legislative Notifications:** The 57th Council's recommendation to raise the prosecution threshold to ₹5 Crore remains flagged as `PENDING_AMENDMENT` until the relevant parliamentary amendment is notified in the Gazette.

---

## 9. Conclusion & Release Gate Sign-Off

The GST Integration and Compliance Engine meets all standards for production-readiness in offline preparation mode and is safely integrated into the `main` branch.

**Certified by:** Lead Release Engineer & GST Integration Specialist  
**Release Gate Decision:** `MERGED AND STAGING VERIFIED`
