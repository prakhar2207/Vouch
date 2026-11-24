# SRI LEKH GST — ROUND 2.5.18
## Multi-GSTIN Filing Identity & Concurrency Report

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Production Application:** `https://srilekh.com`  
**Baseline Commit:** `7856cca6e510b5a435a93c83a2eaf285dedbd8b5`  
**Target Branch:** `main`  
**Auditor Roles:** Principal Software Architect, Senior Django/PostgreSQL Engineer, Financial Systems Auditor  
**Date:** 2026-11-23  

---

### 1. Executive Summary

A critical audit finding in earlier implementations was that `upload_gstr1_direct()` and `GSTRFilingsAPIView` performed `GSTFilingRecord.objects.update_or_create()` using only `(company, return_type, return_period)` as the lookup key, passing `gst_registration` in `defaults`. 

In a multi-GSTIN enterprise where a company operates multiple branches (e.g., Uttar Pradesh and Delhi), filing for period `082026` by GSTIN B would overwrite and mutate the historical filing record previously created by GSTIN A!

In Round 2.5.18:
1. **Database Constraint Enforcement:** Added a unique composite constraint across `(company, gst_registration, return_type, return_period)` and a partial constraint for legacy null registrations, backed by a composite btree index.
2. **Scoping in Direct Upload:** `upload_gstr1_direct()` now scopes lookups, submission blocking, and state persistence strictly to `(company, gst_registration, return_type, return_period)`.
3. **Statutory Immutability Protection:** Pre-delete signals and custom model manager `.delete()` raise `ValidationError` when attempting to delete filings in `FILED`, `SUBMITTED`, or `SUBMITTING` status.

---

### 2. Database Schema & Migration Evidence

#### Schema Changes in `apps/gst/models.py`:
```python
class GSTFilingRecord(models.Model):
    # ...
    class Meta:
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['company', 'return_type', 'return_period']),
            models.Index(fields=['company', 'gst_registration', 'return_type', 'return_period']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'gst_registration', 'return_type', 'return_period'],
                name='unique_company_reg_return_identity'
            ),
            models.UniqueConstraint(
                fields=['company', 'return_type', 'return_period'],
                condition=models.Q(gst_registration__isnull=True),
                name='unique_company_null_reg_return_identity'
            ),
        ]
```

#### Migration Execution Log:
- Migration `0020_gstfilingrecord_gst_gstfili_company_badd32_idx_and_more.py` generated via `makemigrations gst`.
- Applied cleanly to PostgreSQL via `python manage.py migrate gst` with zero schema conflicts:
  ```
  Running migrations:
    Applying gst.0020_gstfilingrecord_gst_gstfili_company_badd32_idx_and_more... OK
  ```

---

### 3. Verification & Concurrency Control

#### Duplicate Submission Shield:
When `upload_gstr1_direct()` is called:
1. It queries `GSTFilingRecord.objects.filter(company=company, gst_registration=reg, return_type='GSTR1', return_period=period_val).first()`.
2. If an existing record is found:
   - Status `FILED` with authentic ARN: returns `code="ALREADY_FILED"` immediately.
   - Status `SUBMITTED` or `SUBMITTING`: returns `code="SUBMISSION_PENDING"`, instructing the user to check status rather than re-submitting.
3. If no pending or filed record exists:
   - Atomically records `status="SUBMITTING"` with `provider_reference=corr_id` and `arn=""` before initiating any outbound network call.

#### Deletion Invariants (Statutory Anti-Spoliation):
- Calling `.delete()` on `GSTFilingRecord` instances where `status in ['FILED', 'SUBMITTED', 'SUBMITTING']` raises `ValidationError`:
  `"Statutory Audit Invariant: Cannot delete GST filing record in FILED/SUBMITTED status."`
- Bulk deletion via `ProtectedGSTFilingRecordQuerySet.delete()` is similarly intercepted and blocked.

---

### 4. Empirical Test Evidence

| Test Case | Scenario Description | Expected Outcome | Result |
| :--- | :--- | :--- | :--- |
| `test_separate_filing_records_for_different_gstins_same_period` | GSTIN A and B file for period 082026 | 2 distinct records created under same company | **PASS** |
| `test_database_unique_constraint_enforces_company_reg_period` | Direct insertion of duplicate (company, reg, period) | Raises `django.db.IntegrityError` | **PASS** |
| `test_duplicate_submission_blocked_when_already_filed` | Re-upload when return is already `FILED` with ARN | Blocked: `ALREADY_FILED` | **PASS** |
| `test_duplicate_submission_blocked_when_pending` | Re-upload when previous return is `SUBMITTED` | Blocked: `SUBMISSION_PENDING` | **PASS** |
| `test_filing_record_protected_from_deletion_when_filed` | Delete invocation on `FILED` return | Blocked: `ValidationError` | **PASS** |

---

### 5. Conclusion
Filing records for distinct GST registrations are completely decoupled and protected by PostgreSQL database-level unique constraints. Multi-branch returns cannot overwrite each other, and statutory audit integrity is permanently preserved.
