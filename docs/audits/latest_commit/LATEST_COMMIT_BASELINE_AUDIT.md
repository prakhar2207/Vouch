# LATEST COMMIT BASELINE AUDIT

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Audited Target Commit (Merge Integration):** `08cd3b8bc3ab2cf15293400c3e703c4a318ebbe8`  
**Latest Main Branch HEAD:** `4ca76a0f44e138be708e17812f8fc73bb463d1a3`  
**Dedicated Remediation Branch:** `audit/latest-main-remediation`  
**Previous Production Baseline:** `d39d481ac2eb545d0436fafa9dd2c593ceb7e946` (October 10, 2026)  
**Date of Audit:** November 13, 2026  
**Auditor Roles:** Principal Software Architect, Senior Django Backend Engineer, Senior Next.js Engineer, Database Reliability Engineer, Security Auditor, DevOps Engineer, QA Lead  

---

## 1. Executive Summary & Integration Baseline

On November 13, 2026, SriLekh underwent a comprehensive consolidation merge ([commit `08cd3b8`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B)) that integrated 55 commits from 22 active engineering branches into `main`. Prior to this merge, production environments on Render (`vouch-api-752s`) and Vercel (`vouch-pi-one`) were anchored to legacy commit `d39d481`, causing newly built statutory compliance routes, offline-first sync features, banking reconciliation rules, and enhanced multi-tenant security layers to return `404 Not Found` or remain unexercised in production.

This audit establishes the empirical baseline of the integrated codebase, isolates production data, executes full-stack regression verification, remediates critical CI/CD and email transport defects, and delivers definitive release candidate certification.

---

## 2. Environment & Database Safety Invariant Verification

In accordance with mandatory Phase 0 directives, strict tenant isolation and environment safety invariants were confirmed prior to executing any write operation or test harness:

| Target Resource | Target Identity / Fingerprint | Safety Policy Enforced | Status |
| :--- | :--- | :--- | :--- |
| **Protected Production Tenant** | `Maa Annapurna Belting Store`<br>`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c` | Zero test writes, zero schema migrations, zero mock seed, zero test logins. | **STRICTLY PROTECTED & UNTOUCHED** |
| **Dedicated Test Sandbox** | `Apex Belting & Industrial Store (Demo)`<br>`4e62863a-08f9-4e99-b0bd-64873acfdd33` | Explicit UUID assertion required in all integration harnesses. | **VERIFIED FOR BENCHMARKS** |
| **Production Neon Database** | `neondb` on AWS Neon cluster `ep-lingering-boat-b3994i6f` | No write operations without user authorization; zero test fixtures. | **ISOLATED & VERIFIED** |
| **Staging Neon Database** | `neondb_staging` on Neon cluster `ep-silent-feather-b34egg28`<br>Fingerprint: `6f4741bdaaf4` | Disposable/isolated scratch testing target. Protected tenant absent. | **VERIFIED ABSENT OF PROD TENANT** |

---

## 3. Commit Integration Topology & Divergence Analysis

The audited commit `08cd3b8bc3ab2cf15293400c3e703c4a318ebbe8` consolidated 22 distinct topic branches:
1. `feat/google-play-launch-readiness`: Public legal compliance routes (`/privacy-policy`, `/terms`, `/refund-policy`, `/delete-account`, `/pricing`, `/contact`), Android app bundle packaging, Capacitor native bridge configuration.
2. `feat/stage4-accounting-core`: Double-entry accounting vouchers, transaction lifecycle (Draft -> Posted -> Reversed -> Cancelled), ledger balancing invariants.
3. `feat/stage4-fifo-stock-valuation`: FIFO lot allocation for inventory inward/outward and return voucher acquisition cost basis restoration.
4. `feat/stage4-banking-engine`: Bank statement parsers (CSV, Excel), 4-pass reconciliation, idempotency deduplication hashing, statement transaction exclusion.
5. `feat/stage4-offline-sync`: AES-GCM-256 IndexedDB client outbox, deterministic `X-Idempotency-Key` headers, tenant-switch memory purges.
6. `fix/resend-https-transport`: Render free-tier SMTP port firewall bypass using HTTPS Port 443 transactional email backend.
7. `fix/ci-cd-triggers`: GitHub Actions workflow trigger coverage for `main`, `audit/**`, and `pull_request`.

### Baseline Comparison: `d39d481` vs `08cd3b8`

| Dimension | Legacy Baseline (`d39d481`) | Integrated Audit Baseline (`08cd3b8`) | Delta / Architectural Impact |
| :--- | :--- | :--- | :--- |
| **Public Statutory Routes** | 0/6 accessible (404 on Vercel) | 6/6 accessible (200 OK across desktop & mobile) | Full Google Play statutory compliance restored. |
| **Email Delivery Transport** | Raw SMTP (Port 587/465) blocked by Render free dyno firewall (`[Errno 101] Network is unreachable`) | Built-in HTTPS Port 443 Resend API transport with zero external dependencies | Real-time OTP delivery unblocked on Render container runtimes. |
| **CI/CD Workflow Triggers** | `feat/**`, `fix/**` only (No `main`, no PR validation) | `main`, `feat/**`, `fix/**`, `audit/**`, `pull_request` to `main` with `npm ci` | Continuous integration and post-merge automated verification enabled. |
| **Offline IndexedDB Security** | Plaintext client storage | AES-GCM-256 non-extractable Web Crypto keys with cross-table AAD authentication | Client-side tenant privacy and hardware-isolated crypto keys. |
| **Sales Return Valuation** | Unverified return unit costing | Strict original purchase lot acquisition cost recovery | Strict compliance with Indian Accounting Standard (Ind AS 2). |

---

## 4. Git Working Tree Status on Remediation Branch

- **Active Remediation Branch:** `audit/latest-main-remediation`
- **Tracked Modifications:**
  - `.github/workflows/stage-verification-ci.yml`: Added `main` and `pull_request` triggers; replaced `npm install` with lockfile-enforced `npm ci`.
  - `frontend/src/app/register/page.tsx`: Updated error handlers to catch DRF throttling `detail` payloads and prevent generic masking.
  - `apps/notifications/backends/resend_backend.py`: Implemented resilient HTTPS Resend transactional email backend.
  - `apps/notifications/tests_resend.py`: Comprehensive test harness for HTTPS email delivery.
- **Untracked Verification Artifacts & Scripts:** Preserved safely in `scripts/` directory for repeatable verification across audit cycles.
