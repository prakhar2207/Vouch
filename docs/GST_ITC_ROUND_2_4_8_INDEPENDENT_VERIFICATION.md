# SriLekh GST ITC Shield — Round 2.4.8
## Independent Verification & Evidence Reconciliation Report

**Auditor:** Independent QA / Systems Architecture Auditor  
**Inspection Date:** 2026-11-25  
**Target Branch:** `remediation/round-2.4.7-multi-period-gstr2b-sync`  
**Target Commit SHA:** `1ddb70f77639ef80eed576f4f62a8e64528048bb`  
**Parent Baseline Commit:** `6df7dd3` (`audit/round-2.4.6-gst-integration-reliability`)  
**Deployment State:** Unmerged into `main` (`a2e0720`); staging and production environments run `main`.  

---

### 1. Source and Deployment State Evidence Matrix

| Item | Expected Evidence | Verified Result | Notes |
| :--- | :--- | :--- | :--- |
| **Branch and Commit** | `git branch -vv`, `git log -1` | `remediation/round-2.4.7-multi-period-gstr2b-sync` @ `1ddb70f77639ef80eed576f4f62a8e64528048bb` | Exactly matches target commit; remote branch tracking is up-to-date. |
| **Working Tree** | `git status` | Clean (`nothing to commit, working tree clean`) | No untracked or unstaged files. |
| **Migration Committed** | File inspection & git diff | `apps/gst/migrations/0031_alter_gstr2bsyncattempt_return_period.py` | Present in commit `1ddb70f`. Expands `GSTR2BSyncAttempt.return_period` to 32. |
| **Frontend Committed** | Git diff | `MonthPickerInput.tsx` + `page.tsx` integration + `month-picker-input.test.ts` | 606 lines added across 3 frontend files in commit `1ddb70f`. |
| **Backend Committed** | Git diff | `models.py` + `reconciliation_service.py` + `views.py` | Model column expanded to 32; range structured keys exposed; default active registration fallback added. |
| **Test Suites Committed** | Git history & file inspection | `apps/gst/tests_round2_4_7_gstr2b_sync.py` (582 lines) | 14 comprehensive tests committed. |
| **Documentation Committed** | Git history | 4 Round 2.4.7 docs in `docs/` | Root cause, UX spec, regression report, and release readiness docs present. |
| **Deployment Metadata** | `render.yaml` & Git branch log | Staging runs branch `main` (`a2e07205a331247f18f37029c0abf4df5a2179d7`) | Branch `remediation/round-2.4.7-multi-period-gstr2b-sync` is **NOT YET DEPLOYED** to staging or production. |
| **Database Identity** | `settings.DATABASES` & Neon host | PostgreSQL 18.7 on AWS Neon: `ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`, DB: `neondb_staging` | Test DB used: `test_neondb_staging`. |

---

### 2. Reconciliation of Prior Round 2.4.7 Test Claims

An independent audit of the execution transcripts and logs revealed why earlier test commands exited with code 1 prior to the final passing runs:

| Test Claimed | Earlier Execution Issues | Verified Final Execution | Exit Code | Environment | Verification Assessment |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **14/14 Targeted Backend Tests** | 1. `NotNullViolation` on `accounting_voucheritem.product_id`<br>2. Neon DNS transient lookup failure `[Errno 11001]` | `python manage.py test apps.gst.tests_round2_4_7_gstr2b_sync --keepdb -v 2` | **0** | PostgreSQL 18.7 (`test_neondb_staging`) | **CONFIRMED 14/14 PASS**. All 14 tests re-executed independently in Round 2.4.8 (Task-30057) in 38.24s. |
| **31/31 Portal Abstraction & Sandbox** | None. Completed synchronously in Task-29912. | `python manage.py test apps.gst.tests_portal_abstraction apps.gst.tests_sandbox_integration --keepdb` | **0** | SQLite (Standard Django test runner) | **CONFIRMED 31/31 PASS**. Zero regressions across portal auth, OTP, and sandbox endpoints. |
| **63/63 Frontend Tests** | None. Completed in Task-29952. | `node --import ./test-loader.mjs --test "src/**/*.test.ts"` | **0** | Node.js Test Runner | **CONFIRMED 63/63 PASS**. Includes 6 new unit tests for `MonthPickerInput`. |
| **TypeScript Typecheck** | None. | `npx tsc --noEmit` | **0** | TypeScript 5.x | **CONFIRMED 0 ERRORS**. |

---

### 3. PostgreSQL Migration 0031 Inspection

A direct query on `information_schema.columns` and `django_migrations` against Neon PostgreSQL (`neondb_staging`) produced the following authoritative evidence:

```sql
SELECT table_name, column_name, data_type, character_maximum_length 
FROM information_schema.columns 
WHERE table_name IN ('gst_gstr2bsyncattempt', 'gst_gstr2bingestionlock') 
  AND column_name = 'return_period';
```

**Actual Schema Result:**
- `gst_gstr2bsyncattempt.return_period`: **`character varying(32)`** (Expanded from 10)
- `gst_gstr2bingestionlock.return_period`: **`character varying(10)`** (Strictly preserved)

**Migration History (`django_migrations`):**
- `gst` - `0030_worker_exclusivity_frequency_trigger_and_actor_governance` (Applied: `2026-11-25 15:31:23 UTC`)
- `gst` - `0031_alter_gstr2bsyncattempt_return_period` (Applied: `2026-11-25 17:34:38 UTC`)

#### Reversibility & Data Integrity Analysis
1. Currently, `gst_gstr2bsyncattempt` in `neondb_staging` contains `0` records. A rollback on staging would proceed with zero data loss.
2. In production, if records with `length(return_period) > 10` exist, rolling back migration `0031` to `0030` will fail with `StringDataRightTruncation` on PostgreSQL, preventing silent truncation or corrupt data.
3. Therefore, reversing the migration **fails safely**. Forward deployment is non-destructive (pure `ALTER TABLE ... ALTER COLUMN TYPE varchar(32)` metadata update).
