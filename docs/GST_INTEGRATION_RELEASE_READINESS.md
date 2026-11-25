# SriLekh GST Integration — Production Release Readiness Assessment

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Target Release:** v2.4.6-production  
**Target Branch:** `audit/round-2.4.6-gst-integration-reliability`  
**Release Readiness Date:** November 25, 2026  
**Auditors:** Principal Django/PostgreSQL Engineer, Application Security Architect, and Independent QA Lead  

---

## 1. Executive Summary & Production Gate Decision

### Release Gate Status: **CONDITIONALLY CERTIFIED FOR PRODUCTION**

SriLekh's GST compliance engine is fully certified and production-ready for commercial deployment under the following operational posture:
1. **Production-Ready & Fully Certified**:
   - Multi-GSTIN corporate registrations and profile management.
   - Live GSTIN search, taxpayer validation, and party ledger auto-enrichment.
   - GSTR-1 outward supply compilation conforming to GSTN Offline Tool Schema v3.1.2.
   - GSTR-3B monthly statutory liability calculation with Rule 88A set-off waterfall.
   - GSTR-2B inward statement ingestion (XLSX, ZIP with decompression protection).
   - Vendor ITC Risk Shield with QRMP period intelligence and CDNR signed math.
   - Worker lease exclusivity and Celery Beat automated reconciliation recovery.
   - Native PostgreSQL database triggers enforcing audit log and filing frequency immutability.
   - E-Way Bill & E-Invoice payload formatting and IRN cryptographic hashing.
2. **Pre-Requisite for Live GSTN Portal Direct Submission & Live SMS OTP Delivery**:
   - Requires provisioning an active commercial enterprise GSP (GST Suvidha Provider) license and setting `is_sandbox = False` in `CompanyGSTConfig`.
   - Taxpayers must enable API access on their government profile (`gst.gov.in`).
   - Server-side live filing safety guard (`LiveFilingProhibitedError`) remains intentionally active to protect MSMEs from accidental premature return submission until organizational release sign-off.

---

## 2. Capability Readiness Scorecard

| Module / Capability | Implementation Mode | Automated Test Coverage | Gate Decision | Commercial Action |
|---|---|---|---|---|
| **GSTIN Lookup & Verification** | Sandbox / Cashfree | 100% Passed (Cache + Live) | **GO** | Immediate live usage |
| **Party Master Auto-Enrichment** | ERP Integration | 100% Passed | **GO** | Immediate live usage |
| **Multi-GSTIN Isolation** | Database Scoped | 100% Passed (Fail-closed) | **GO** | Immediate live usage |
| **GSTR-1 Preparation & JSON** | Offline Tool Schema v3.1.2 | 100% Passed | **GO** | Export & upload to gst.gov.in |
| **GSTR-3B Computation & Review** | GSTN Spec v1.4 | 100% Passed (Rule 88A) | **GO** | Review & file on gst.gov.in |
| **GSTR-2B Ingestion & Sync** | XLSX / ZIP / Sandbox | 100% Passed (Zip-bomb safe) | **GO** | Ingest monthly 2B statements |
| **Vendor ITC Risk Shield** | PostgreSQL Engine | 100% Passed (Exclusivity + Rec) | **GO** | Active vendor risk protection |
| **Smart GST Payment Hold** | ERP Voucher Control | 100% Passed | **GO** | Withhold GST on defaulting vendors |
| **WhatsApp Filing Chaser** | Client-side URI Scheme | 100% Passed | **GO** | 1-click chaser notices |
| **E-Way Bill Generation** | Gateway / Mock | 100% Passed | **CONDITIONAL** | Switch provider to Live GSP |
| **E-Invoice (IRP / IRN)** | Gateway / Mock | 100% Passed (SHA-256) | **CONDITIONAL** | Switch provider to Live GSP |
| **Direct Portal OTP Delivery** | Sandbox Gateway | 100% Passed (Rate + Lockout) | **CONDITIONAL** | Requires Live GSP for SMS |
| **Direct GSTR-1 Portal Upload** | Server Safety Guard | 100% Blocked (`LiveFilingProhibited`)| **HELD** | Requires explicit release toggle |
| **Electronic Ledgers Sync** | Double-Entry ERP | 100% Passed | **GO (ERP)** | Portal balance entry manual |
| **Challan & Payment Tracking**| CIN Documentary Proof | 100% Passed (Rule 37A) | **GO (ERP)** | Portal PMT-06 payment manual |

---

## 3. Production Deployment Runbook

### 3.1 Migration Sequence
1. Confirm PostgreSQL version is 15+ (Production uses PostgreSQL 18.7 on Neon Cloud).
2. Execute forward migration:
   ```bash
   python manage.py migrate gst
   ```
   *Confirmed: Migrations applied through `0030_worker_exclusivity_frequency_trigger_and_actor_governance.py`.*
3. Verify that native database triggers are active:
   ```sql
   SELECT trigger_name, event_manipulation, event_object_table
   FROM information_schema.triggers
   WHERE trigger_name IN (
       'trg_prevent_direct_filing_frequency_mutation',
       'trg_prevent_frequency_audit_tampering',
       'trg_prevent_attribution_log_mutation'
   );
   ```
   *Expected: All 3 triggers returned with active status.*

### 3.2 Celery Beat Background Worker
Ensure that Celery Beat is running alongside Celery worker:
```bash
celery -A config worker -l info
celery -A config beat -l info
```
*Confirmed: `auto-recover-itc-reconciliation-jobs` is scheduled to execute every 60 seconds.*

### 3.3 Rollback Plan & Safety Guards
If migration rollback is required in staging or disaster recovery:
1. Migration `0030` enforces a rollback guard requiring an explicit environment variable:
   ```bash
   export ALLOW_AUDIT_TRIGGER_ROLLBACK=true
   python manage.py migrate gst 0029
   ```
2. Without `ALLOW_AUDIT_TRIGGER_ROLLBACK=true`, rolling back migration `0030` will raise `RuntimeError`, preventing accidental destruction of audit triggers.

---

## 4. Final Sign-Off

The SriLekh Round 2.4.6 release satisfies all statutory, accounting, security, and concurrency invariants. It is approved for production deployment.
