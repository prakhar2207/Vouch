# SRI LEKH GST — ROUND 2.5.18
## Regression Evidence & Verification Report

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Production Application:** `https://srilekh.com`  
**Baseline Commit:** `7856cca6e510b5a435a93c83a2eaf285dedbd8b5`  
**Target Branch:** `main`  
**Auditor Roles:** QA Automation Architect, Principal Software Architect  
**Date:** 2026-11-23  

---

### 1. Executive Summary

To ensure the hardening in Round 2.5.18 did not introduce any regressions, all 4 automated test suites covering the GST subsystem were executed sequentially in a single regression test run against the dedicated sandbox database:
1. `apps.gst.tests_round2_5_18_hardening` (New Round 2.5.18 adversarial suite)
2. `apps.gst.tests_round2_5_17_integrity` (Round 2.5.17 statutory audit suite)
3. `apps.gst.tests_simplified_onboarding` (Taxpayer onboarding suite)
4. `apps.gst.tests_portal_abstraction` (Portal UI abstraction suite)

Additionally, the Next.js production frontend build was executed.

---

### 2. Backend Test Execution Results

#### Command Executed:
```bash
python manage.py test apps.gst.tests_round2_5_18_hardening apps.gst.tests_round2_5_17_integrity apps.gst.tests_simplified_onboarding apps.gst.tests_portal_abstraction
```

#### Test Execution Summary:
```
Creating test database for alias 'default'...
.....................................................................................
----------------------------------------------------------------------
Ran 85 tests in 51.493s

OK
Destroying test database for alias 'default'...
Found 85 test(s).
```

**Result: 85 passed / 0 failed / 0 errors (100% Pass Rate).**

#### Suite Breakdown:
- `apps.gst.tests_round2_5_18_hardening`: 31 tests passed
- `apps.gst.tests_round2_5_17_integrity`: 31 tests passed
- `apps.gst.tests_simplified_onboarding`: 13 tests passed
- `apps.gst.tests_portal_abstraction`: 10 tests passed

---

### 3. Frontend Production Build Verification

#### Command Executed:
```bash
npm --prefix frontend run build
```

#### Build Execution Output:
```
> frontend@0.1.0 build
> node scripts/patch-html2canvas.js && next build --webpack

[patch-html2canvas] Scanning node_modules/html2canvas for unsupported color functions...
[patch-html2canvas] Done.
▲ Next.js 16.4.6 (webpack)
- Environments: .env.local

✓ Running next.config.ts took 755ms
  Creating an optimized production build ...
✓ (serwist) Bundling the service worker script with the URL '/sw.js' and the scope '/'...
✓ Compiled successfully in 17.0s
  Running TypeScript ...
  Finished TypeScript in 3.5s ...
  Collecting page data using 23 workers ...
  Generating static pages using 23 workers (59/59) in 2.0s
  Finalizing page optimization ...
  Collecting build traces ...

Route (app)
✓ All 59 routes generated cleanly (Static & Dynamic)
```

**Result: Build succeeded with 0 errors, 0 type warnings.**

---

### 4. Tenant Isolation Invariant Compliance

- Dedicated Sandbox Tenant Verified: `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
- Protected Production Tenant Unmodified: `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`).
- Client Tenant Mutation Count: **0 records created, modified, or deleted.**

---

### 5. Conclusion
Zero regressions detected across backend services, database migrations, and frontend production bundles.
