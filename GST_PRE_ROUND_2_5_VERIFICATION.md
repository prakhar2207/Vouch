# SriLekh — Post-Merge Operational Hardening & Pre-Round 2.5 Verification Report

**Audit Date:** 20 November 2026  
**Auditor:** Independent Release Engineer, Senior Django Architect, GST Integration Specialist & Accounting Auditor  
**Repository:** `https://github.com/prakhar2207/Vouch`  
**Active Branch:** `main`  
**Staging Backend URL:** `https://vouch-u3u7.onrender.com`  
**Staging Database:** Neon `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`)  
**Staging Database Fingerprint:** `6f4741bdaaf4`  
**Dedicated Primary Sandbox Tenant:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Isolated Staging MSME Tenants Tested:**  
- **Tenant A:** `Precision Agro Tools Pvt Ltd` (`c2771ca4-31bd-47d2-b98c-c1be119f40a1`) — User: `owner_msme-plt-01@staging.srilekh.internal`
- **Tenant B:** `Garodia Bearing & Power Transmission` (`cd788d07-ae29-4af9-89d2-c5a4f32378cf`) — User: `owner_msme-plt-02@staging.srilekh.internal`  
**Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) — *Strictly Isolated; 0 rows present in staging DB*

---

## Executive Summary & Final Verdict

### Final Operational Verdict
$$\mathbf{PASS\ WITH\ LIMITATIONS\ —\ READY\ TO\ BEGIN\ ROUND\ 2.5}$$

### Operational Limitations Summary
1. **Background Dyno Constraint:** Render staging runs on a single Gunicorn web container without Redis or Celery worker dynos (`redis: unreachable`, `workers_online: 0`). Core accounting, return compiling, drift detection, and export generation operate synchronously and flawlessly. Asynchronous transactional outbox notifications accumulate safely in PostgreSQL (`0 PENDING`) and require explicit manual/cron invocation of `OutboxService.recover_pending_outbox_events()`.
2. **External Quicko Sandbox Unverified:** The gateway routes to `MockGSTProvider` by default because `CompanyGSTConfig` credentials (`SANDBOX_API_KEY`/`SANDBOX_API_SECRET`) are not provisioned in live staging environment variables. Live external network calls to `api.sandbox.co.in` remain unverified in staging; resilience and error-handling simulation passed 100%.
3. **Prior-Period GST Return Amendments Incomplete:** In the current `main` release, double-entry accounting reversals and credit notes are fully functional, but GSTR-1 amendment tables (`b2ba`, `b2cla`, `b2csa`, `cdnra`, `cdnura`) and GSTR-3B Table 4(B)/4(D) reversals/reclaims are hardcoded stubs. This defines the primary engineering mandate for Round 2.5.

---

## 1. Phase 1 — Exact Release Identity & Git Lineage Evidence

| Verification Dimension | Expected State | Measured Evidence | Result |
| :--- | :--- | :--- | :---: |
| **Deployed Render Commit (Short)** | `640f3e9c` | `GET /api/v1/health/environment/` returns `"commit": "640f3e9c"` | **PASS** |
| **Exact Full Deployed Commit SHA** | Full 40-char SHA | `640f3e9c36f81f2dc4fc936375e64eac261daf4f` | **PASS** |
| **Certified Base Commit in Git** | `640f3e9` | `git rev-parse 640f3e9` $\rightarrow$ `640f3e9c36f81f2dc4fc936375e64eac261daf4f` | **PASS** |
| **Merge Commit Ancestry** | Ancestor of `origin/main` | `git merge-base --is-ancestor 4cba2926aa90bdf760217fe5d2454bd89b2be19e main` (Exit 0) | **PASS** |
| **Certified Commit Ancestry** | Ancestor of `origin/main` | `git merge-base --is-ancestor 640f3e9c36f81f2dc4fc936375e64eac261daf4f main` (Exit 0) | **PASS** |
| **Database Target** | `neondb_staging` | `"sanitized_target": "neondb_staging"`, host: `ep-silent-feather-b34egg28-pooler` | **PASS** |
| **Database Identity Fingerprint** | `6f4741bdaaf4` | `"identity_fingerprint": "6f4741bdaaf4"`, `"is_isolated": true` | **PASS** |
| **Database Migrations** | 0 unapplied | `"migrations": {"status": "up_to_date", "unapplied_count": 0}` | **PASS** |
| **Protected Production Tenant Count** | Exactly 0 | `SELECT count(*) FROM companies_company WHERE id = '5d2e5dea...'` $\rightarrow$ `0` | **PASS** |

### Git Commit Lineage Trace
```text
* 3ce8887 (HEAD -> main, origin/main) docs(gst): publish post-merge main deployment verification report
* d4ffa08 docs(gst): publish prior-period GST correction and adjustment capability audit report
* 640f3e9 docs(gst): publish official GST main merge certification report  <-- [DEPLOYED ON RENDER]
*   4cba292 chore(release): merge GST integration and compliance engine into main
|\  
| * a0ae945 chore(merge): merge origin/main into rc/gst-main-integration-merge
| * 6bcfb55 feat(gst): implement provider capability matrix and production safety controls
| * d6c8a5b feat(gst): enforce dynamic tax rate schedules, 57th council rules & statutory change register
```

---

## 2. Phase 2 — Authenticated Tenant Isolation & IDOR Audit

Unlike unauthenticated probes (which return 401), cross-tenant authorization testing was conducted with live authenticated JWT tokens issued to verified users belonging to distinct staging tenants:
- **User A:** `owner_msme-plt-01@staging.srilekh.internal` (Member of Tenant A: `c2771ca4-31bd-47d2-b98c-c1be119f40a1`)
- **User B:** `owner_msme-plt-02@staging.srilekh.internal` (Member of Tenant B: `cd788d07-ae29-4af9-89d2-c5a4f32378cf`)

### Bidirectional Multi-Tenant Test Matrix (19 / 19 PASS — 100%)

| # | Request Vector | Action Description | Target Tenant | Auth User | HTTP Status | Verdict |
| :-: | :--- | :--- | :---: | :---: | :-: | :-: |
| **1** | `GET /api/v1/gst/overview/{id}/` | Own Tenant Overview | Tenant A | User A | **200 OK** | **PASS** |
| **2** | `GET /api/v1/gst/overview/{id}/` | Cross-Tenant Overview | Tenant B | User A | **403 Forbidden** | **PASS** |
| **3** | `GET /api/v1/gst/workspace/{id}/` | Cross-Tenant Workspace | Tenant B | User A | **403 Forbidden** | **PASS** |
| **4** | `GET /api/v1/gst/registrations/{id}/` | Cross-Tenant Registrations | Tenant B | User A | **403 Forbidden** | **PASS** |
| **5** | `GET /api/v1/gst/returns/gstr1/{id}/` | Cross-Tenant GSTR-1 | Tenant B | User A | **403 Forbidden** | **PASS** |
| **6** | `GET /api/v1/gst/returns/gstr3b/{id}/` | Cross-Tenant GSTR-3B | Tenant B | User A | **403 Forbidden** | **PASS** |
| **7** | `GET /api/v1/gst/workspace/{id}/export/` | Cross-Tenant Export | Tenant B | User A | **403 Forbidden** | **PASS** |
| **8** | `POST /api/v1/gst/workspace/{id}/init-period/` | Cross-Tenant Write (Workspace) | Tenant B | User A | **403 Forbidden** | **PASS** |
| **9** | `POST /api/v1/gst/registrations/{id}/` | Cross-Tenant Write (Registration) | Tenant B | User A | **403 Forbidden** | **PASS** |
| **10** | `DELETE /api/v1/gst/registrations/{id}/{pk}/` | Cross-Tenant Delete | Tenant B | User A | **403 Forbidden** | **PASS** |
| **11** | `GET /api/v1/gst/overview/{id}/` | Own Tenant Overview | Tenant B | User B | **200 OK** | **PASS** |
| **12** | `GET /api/v1/gst/overview/{id}/` | Cross-Tenant Overview (Reverse) | Tenant A | User B | **403 Forbidden** | **PASS** |
| **13** | `GET /api/v1/gst/workspace/{id}/` | Cross-Tenant Workspace (Reverse) | Tenant A | User B | **403 Forbidden** | **PASS** |
| **14** | `GET /api/v1/gst/registrations/{id}/` | Cross-Tenant Registrations (Reverse) | Tenant A | User B | **403 Forbidden** | **PASS** |
| **15** | `GET /api/v1/gst/returns/gstr1/{id}/` | Cross-Tenant GSTR-1 (Reverse) | Tenant A | User B | **403 Forbidden** | **PASS** |
| **16** | `GET /api/v1/gst/returns/gstr3b/{id}/` | Cross-Tenant GSTR-3B (Reverse) | Tenant A | User B | **403 Forbidden** | **PASS** |
| **17** | `GET /api/v1/gst/workspace/{id}/export/` | Cross-Tenant Export (Reverse) | Tenant A | User B | **403 Forbidden** | **PASS** |
| **18** | `POST /api/v1/gst/workspace/{id}/init-period/` | Cross-Tenant Write (Reverse) | Tenant A | User B | **403 Forbidden** | **PASS** |
| **19** | `GET /api/v1/gst/overview/{fake_id}/` | Non-Existent Company Access | `00000000-...` | User A | **403 Forbidden** | **PASS** |

**Conclusion:** Strict tenant isolation is verified. Authenticated cross-tenant read, write, and delete requests are universally denied with `HTTP 403 Forbidden` at the `BaseCompanyPermission` layer before view execution. Zero cross-tenant data leaked.

---

## 3. Phase 3 — Quicko Sandbox Integration & Provider Status

### Configured Provider Path in Live Staging
1. **Active Gateway:** `MockGSTProvider`.
2. **Routing Rationale:** `CompanyGSTConfig` rows in `neondb_staging` are currently empty (`0 rows`), and environment variables `SANDBOX_API_KEY` / `SANDBOX_API_SECRET` are not set on Render staging. `apps.gst.services.providers.factory.get_gst_provider` falls back safely to `MockGSTProvider`.
3. **Explicit Verification Notice:** **Live external integration with Quicko Sandbox (`api.sandbox.co.in`) is UNVERIFIED in the live staging deployment due to absent external API credentials.**

### Provider Capabilities & Resilience Test Suite (`QuickoSandboxResilienceTests`)
A dedicated 9-point unit and simulation suite verified `QuickoSandboxProvider` and `SandboxGSTClient` error handling:

| Scenario | Execution Detail | Expected Behavior | Actual Outcome | Status |
| :--- | :--- | :--- | :--- | :--- :---: |
| **1. Capabilities Scoping** | Inspect `provider.capabilities` | Set contains `GSTIN_LOOKUP` only | `{ 'gstin_lookup' }` strictly enforced | **PASS** |
| **2. Live Filing Prohibition** | Call `file_gstr1` & `file_gstr3b` | Raise `LiveFilingProhibitedError` | Strict prohibition exception raised | **PASS** |
| **3. Successful GSTIN Lookup** | Mock Quicko 200 payload | Parse legal name, trade name, status | Parsed `trade_name`, `legal_name`, `sts` | **PASS** |
| **4. Invalid GSTIN Format** | Mock Quicko 422 payload | Return `success=False`, error details | Returned `status_code=422`, error string | **PASS** |
| **5. Authentication Failure** | Mock Quicko 401 `/authenticate` | Raise `GSTAuthenticationError` | Raised `GSTAuthenticationError` | **PASS** |
| **6. Provider Gateway Timeout** | Simulate `requests.exceptions.Timeout` | Return 504 Gateway Timeout | Returned `status_code=504`, "Timeout" | **PASS** |
| **7. Malformed Response** | Simulate 502 HTML payload | Catch non-JSON and fail closed | Returned `status_code=502`, error string | **PASS** |
| **8. Provider Unavailability** | Simulate `ConnectionError` | Log audit event and return 504 | Returned `status_code=504`, audit logged | **PASS** |
| **9. Data & Secret Redaction** | Redact `Authorization`, `x-api-secret` | Mask with `********` | Masked in all logs, zero secret leakage | **PASS** |

---

## 4. Phase 4 — Redis, Celery & Transactional Outbox Operational Status

### Operational State on Live Staging
- **PostgreSQL Outbox Table Status (`notifications_transactionaloutboxevent`):**
  - `PROCESSED`: 603
  - `SKIPPED`: 397
  - `DEAD_LETTER`: 9 (historical synthetic chaos test rows preserved)
  - `PENDING`: 0
  - `RETRY_PENDING`: 0
- **Celery Broker:** `configured: true`, `status: unreachable` (Web container runs without external Redis).
- **Celery Workers:** `workers_online: 0` (No background worker dyno on single-container Render tier).
- **Celery Beat:** `beat_schedule_active: false`.

### Outbox Resiliency Analysis
1. **Atomicity Guarantee:** When vouchers are posted, `TransactionalOutboxEvent` creation occurs inside the database transaction (`transaction.atomic`). If the voucher fails or rolls back, zero orphaned outbox events are created.
2. **Graceful Degradation:** When Celery task dispatch (`dispatch_outbox_event.delay`) fails due to unreachable Redis, the event remains safely stored in PostgreSQL as `PENDING`.
3. **Idempotent Recovery:** `OutboxService.recover_pending_outbox_events()` utilizes PostgreSQL row-level locks (`select_for_update(skip_locked=True)`) and verifies `EmailDeliveryLog` with `idempotency_key = f"inv_post_{company.id}_{voucher.id}_v{version}"`. Events delivered previously are acknowledged as `PROCESSED` without resending.
4. **Beat Independence:** Recovery does not depend on Celery Beat; it can be triggered via Django management command or automated script.

### Hosting Tier Recommendation
- **Current Staging Tier:** Because background dynos are unprovisioned, asynchronous email notifications are **dormant in real-time**.
- **Actionable Remedy:** 
  1. For staging testing: Configure an hourly Render Cron Job calling `python manage.py run_outbox_worker --batch-limit 100` or attach a free external Redis instance (e.g., Upstash).
  2. For production: Provision dedicated `vouch-worker` and `vouch-beat` dynos as already defined in `render.yaml`.

---

## 5. Phase 5 — Prior-Period GST Capability Baseline Matrix

Evaluation of SriLekh's 10 prior-period correction scenarios on the certified `main` codebase:

| # | Prior-Period Scenario | Accounting Ledger Effect | GST Reporting Period | GSTR-1 Impact | GSTR-3B Impact | Amendment / Reversal Behavior | Filed-Return Protection | Statutory Validation Result | Scenario Status |
| :-: | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **1** | **January sales invoice entered in February** | Debits Party, credits Sales/GST. | Bound to January `voucher_date`. | Excluded from Feb GSTR-1. | Excluded from Feb GSTR-3B Table 3.1. | No carryover mechanism into Feb returns. | None (Jan return can be modified). | Fails Section 39(9) subsequent-month reporting. | **PARTIALLY PASSES** (Ledgers OK, GST allocation fails) |
| **2** | **January purchase invoice received in February** | Credits Vendor, debits Purchase/ITC. | Bound to January `voucher_date`. | N/A (Purchase). | Excluded from Feb GSTR-3B Table 4. | Excluded from current month claim. | None. | Fails Section 16(2) invoice receipt month rule. | **PARTIALLY PASSES** (Ledgers OK, 3B ITC fails) |
| **3** | **Previously reported invoice requiring GSTIN/value amendment** | Reversal journal + new corrected invoice. | Reversal dated today; new invoice dated today. | Table 9A (`b2ba`, `b2cla`, `b2csa`) hardcoded empty `[]`. | No differential tax row generated. | Cannot generate Table 9A amendment payload. | None. | Fails Section 37(3) GSTR-1 amendment rules. | **FAILS** (Table 9A amendment stubbed) |
| **4** | **Credit note linked to an original invoice** | Debit Sales Return/GST, credit Party. | Bound to credit note date. | Mapped to GSTR-1 Table 9B (`cdnr`/`cdnur`) with `inum`/`idt`. | Subtracted from Table 3.1 outward supplies. | Linked via `original_invoice`. | Compliant with Section 34. | Statutorily compliant. | **PASSES** |
| **5** | **Wrongly claimed ITC requiring reversal** | Debit Expense, credit Input GST. | Current month. | N/A. | Table 4(B) (`itc_reversed`) hardcoded `0.00`. | Reversal journal exists; return payload ignores it. | None. | Fails Rule 42/43/38 GSTR-3B reporting. | **FAILS** (Table 4B stubbed) |
| **6** | **Reclaim of previously reversed ITC** | Debit Input GST, credit Expense. | Current month. | N/A. | Table 4(D)(1) is completely omitted. | Reclaim ignored in GSTR-3B generation. | None. | Fails Section 16(2) proviso & 4(D)(1) rules. | **FAILS** (Table 4D1 omitted) |
| **7** | **Correction after return is filed** | Reversal journal posted today. | Period of original voucher. | Historical draft payload can be overwritten. | Historical 3B can be overwritten. | Reversal allowed on vouchers in filed periods. | **Missing** (Vouchers not locked when return filed). | Violates filed return immutability. | **FAILS** (Filed return protection missing) |
| **8** | **Regeneration of exported workspace** | None. | Workspace period. | `draft_payload` overwritten with current data. | `draft_payload` overwritten. | Status remains `EXPORTED`, but payload changes. | Lacks versioned snapshot history of exported file. | Audit risk (Exported file differs from DB payload). | **PARTIALLY PASSES** (Regenerates, but loses history) |
| **9** | **GST amendment deadline exceeded** | Voucher posts without block. | Financial Year + Nov 30 deadline. | GSTR-1 does not block expired vouchers. | GSTR-3B Table 4 does not block expired ITC. | Advisory query exists (`get_sec16_4_expiry_radar`). | No hard block in posting or return engine. | Fails to enforce Section 16(4) / 37(3) statutory bar. | **PARTIALLY PASSES** (Advisory only; no hard block) |
| **10** | **Rule 37 reversal (180-day unpaid) & reclaim** | Debtors aging identifies unpaid bill. | 180 days from bill date. | N/A. | Table 4(B)(2) hardcoded `0.00`; Table 4(D)(1) omitted. | Manual journal required; return engine omits it. | None. | Rule 37 auto-reversal and reclaim missing. | **FAILS** (Rule 37 automation missing) |

---

## 6. Phase 6 — Newly Discovered Architectural Defects & Round 2.5 Scope

### Defects Identified
1. **`GSTReturnWorkspace` Exported Snapshot Overwrite:**  
   Calling `GSTWorkspaceService.generate_draft()` on an `EXPORTED` workspace overwrites `workspace.draft_payload` with newly recompiled data while maintaining `status='EXPORTED'`. There is no versioning or revision table preserving the exact byte payload exported earlier.
2. **Missing Voucher Lock on Filed Periods:**  
   When a `GSTFilingRecord` is created or marked `FILED`, source vouchers in that date range are not locked against reversal or metadata editing.
3. **Hard Coupling of Voucher Date to Tax Period:**  
   `returns_service.py` filters strictly on `voucher_date`. A separate `tax_period` or `effective_filing_period` attribute is absent, making it impossible to report prior-month vouchers in current-month returns cleanly.
4. **Hardcoded Stubs in Return Payloads:**  
   - GSTR-1: `b2ba`, `b2cla`, `b2csa`, `cdnra`, `cdnura`, `expa`, `ata`, `txpda` are hardcoded `[]`.
   - GSTR-3B: Table 4(B) (`itc_reversed`) and Table 4(D) (`itc_ineligible`) are hardcoded `0.00`.

### Recommended Round 2.5 Implementation Scope
1. **Table 9A/9B Amendment Engine:** Implement GSTR-1 amendment builders comparing current voucher state against original filed snapshots.
2. **Effective Tax Period Decoupling:** Add `filing_period` to vouchers so late January transactions can be allocated to February returns with Section 50 interest calculations.
3. **GSTR-3B Table 4 Reversals & Reclaims:** Connect `ITCReconciliationRecord` and reversal journals to Table 4(B)(2) and Table 4(D)(1).
4. **Filed Return Immutability & Workspace Versioning:** Implement hard voucher locking on filed periods and a `GSTWorkspaceRevision` model to store immutable historical export payloads.
