# SRI LEKH — GST ROUND 1.2.1 AUDIT REPORT: MULTI-GSTIN ARCHITECTURE & INVARIANTS
**Audited Target:** `GSTRegistration` in `apps/gst/models.py`, `registration_service.py`, `views.py`, & `permissions.py`  
**Git Commit:** `8860b99ac3f13db1c554b7d9b0a559a79c5a927e`  
**Branch:** `fix/stage4-12-day6-remediation`  
**Auditor:** Principal Software Architect & Application Security Specialist  
**Date:** 2026-11-16  

---

## 1. Executive Summary

This independent forensic audit evaluates the multi-state, multi-GSTIN architecture implemented in SriLekh. Under the Indian GST regime, an enterprise operating across multiple states or distinct union territories must maintain separate GSTIN registrations tied to the same 10-character Permanent Account Number (PAN) stem.

The subsystem manages registration creation, verification status transitions (`NOT_VERIFIED`, `PENDING`, `VERIFIED`, `INVALID`, `INACTIVE`), primary GSTIN exclusivity, and tenant-scoped isolation.

This audit identifies **one P1 security vulnerability regarding missing role-based access control (RBAC) on registration mutations**, **one P2 concurrency vulnerability regarding primary registration exclusivity**, and **one P2 business invariant omission regarding PAN stem consistency**.

---

## 2. Detailed Findings

### FINDING REG-01 (Severity: P1 — High)
**Missing Role-Based Access Control (RBAC) on Registration Mutation Endpoints**

- **File & Function:** `apps/gst/views.py`:
  - `GSTRegistrationListCreateAPIView.post` (line 554)
  - `GSTRegistrationDetailAPIView.put` (line 607)
  - `GSTRegistrationDeactivateAPIView.post` (line 693)
  - `GSTRegistrationReactivateAPIView.post` (line 712)
- **Exact Problem:**
  Unlike `CompanyGSTConfigAPIView` which explicitly requires `CanManageGSTCredentials()` (enforcing that only users with role `OWNER` or `ADMIN` can modify company credentials), the GST registration mutation endpoints rely exclusively on:
  ```python
  permission_classes = [IsAuthenticated, HasGSTPermission]
  ```
  In `apps/gst/permissions.py`, `HasGSTPermission.has_permission()` checks:
  ```python
  is_member = request.user.companies.filter(id=company_id).exists()
  if not is_member:
      return False
  return True
  ```
  `HasGSTPermission` verifies only that the user is an active member of the company tenant. **It does not inspect the user's role.**
  
  Consequently, a low-privilege employee (e.g. `role="EMPLOYEE"`, `role="VIEWER"`, or a warehouse inventory clerk) can:
  1. Add arbitrary GSTIN registrations to the company.
  2. Change the primary GSTIN of the company.
  3. Deactivate or reactivate active GST registrations, disrupting e-invoicing and billing operations.

- **Reproduction Scenario:**
  1. Create a user `viewer@company.com` with `UserCompany(role='VIEWER')`.
  2. Authenticate as `viewer@company.com`.
  3. Send `POST /api/v1/gst/registrations/{company_id}/` with `{"gstin": "27AAACA1234A1Z5", ...}`.
  4. The request succeeds with HTTP 201 Created instead of HTTP 403 Forbidden.

- **Business / Security Impact:**
  High. Violates principle of least privilege and Sarbanes-Oxley / Indian statutory audit controls. Unauthorized personnel can alter tax identifiers.

- **Recommended Correction:**
  Enforce administrative role requirements on all state-altering registration endpoints:
  ```python
  from apps.accounts.permissions import CanManageGSTCredentials
  # Or enforce role check in get_permissions:
  def get_permissions(self):
      if self.request.method in ['POST', 'PUT', 'DELETE']:
          return [IsAuthenticated(), CanManageGSTCredentials()]
      return [IsAuthenticated(), HasGSTPermission()]
  ```

- **Detected by Existing Tests?**
  **NO.** Test `test_tenant_isolation_on_gst_registrations` tests cross-company isolation (Company B vs Company A), but does not test intra-company role segregation between ADMIN and VIEWER for registration creation/deactivation.

---

### FINDING REG-02 (Severity: P2 — Medium)
**Absence of Database-Level Partial Unique Constraint for Primary Registration**

- **File & Function:** `apps/gst/models.py`: `GSTRegistration.Meta` (lines 140–147) & `apps/gst/services/registration_service.py` (lines 143–150).
- **Exact Problem:**
  `GSTRegistrationService.create_registration()` maintains primary registration exclusivity in Python code inside a database transaction:
  ```python
  with transaction.atomic():
      if should_be_primary:
          GSTRegistration.objects.filter(company=company, is_primary=True).update(is_primary=False)
      reg = GSTRegistration.objects.create(..., is_primary=should_be_primary)
  ```
  However, at the database level (`models.py`), there is **no database constraint enforcing that only one record per company has `is_primary=True`**.
  
  Under concurrent HTTP requests (e.g. two administrators configuring registrations simultaneously in different browser tabs) or during bulk data imports, a race condition can result in **two registrations for the same company having `is_primary=True`**.
  
  When downstream billing and e-invoicing queries call `GSTRegistration.objects.get(company=company, is_primary=True)`, Django will raise `MultipleObjectsReturned`, causing runtime exceptions across invoicing flows.

- **Reproduction Scenario:**
  1. Simulate two concurrent `create_registration` calls with `is_primary=True`.
  2. If the Python queries interleave, both update queries complete before either insert occurs.
  3. Two rows with `is_primary=True` are inserted into PostgreSQL.
  4. Calling `company.gst_registrations.get(is_primary=True)` throws `MultipleObjectsReturned`.

- **Business / Security Impact:**
  High impact under concurrency. Invoicing workflows halt with 500 Internal Server Errors.

- **Recommended Correction:**
  Add a PostgreSQL partial unique constraint to `GSTRegistration.Meta`:
  ```python
  class Meta:
      ordering = ['-is_primary', 'state_code']
      unique_together = ('company', 'gstin')
      constraints = [
          models.UniqueConstraint(
              fields=['company'],
              condition=models.Q(is_primary=True),
              name='unique_primary_gst_registration_per_company'
          )
      ]
  ```

- **Detected by Existing Tests?**
  **NO.** Existing tests are single-threaded.

---

### FINDING REG-03 (Severity: P2 — Medium)
**PAN Stem Consistency Not Enforced Across Registrations**

- **File & Function:** `apps/gst/services/registration_service.py`: `create_registration()` (lines 90–98).
- **Exact Problem:**
  In India, all GST registrations belonging to a single legal entity must share the **exact same 10-character PAN stem** (characters 3 to 12 of the GSTIN, e.g. `27AAACA1234A1Z5` and `07AAACA1234A1Z7` share PAN `AAACA1234A`).
  
  `create_registration()` validates that characters 3 to 12 form a syntactically valid PAN format (`[A-Z]{5}[0-9]{4}[A-Z]{1}`), but **does not verify that the PAN matches existing registrations of the company or the company's master PAN**.
  
  A user could inadvertently add a GSTIN belonging to a different company (e.g. a sister company or vendor) into the same tenant account.

- **Reproduction Scenario:**
  1. Company has existing primary registration: `27AAACA1234A1Z5` (PAN: `AAACA1234A`).
  2. User calls `create_registration` with GSTIN: `07BBBCB5678B1Z2` (PAN: `BBBCB5678B`).
  3. The service accepts and creates the registration without validation error.

- **Business / Security Impact:**
  Tax compliance integrity failure. Invoices and e-way bills generated under mismatched PANs are legally invalid and expose the business to GST penalties.

- **Recommended Correction:**
  Enforce PAN stem consistency:
  ```python
  existing_primary = GSTRegistration.objects.filter(company=company, is_primary=True).first()
  if existing_primary:
      expected_pan = existing_primary.gstin[2:12]
      new_pan = clean_gstin[2:12]
      if new_pan != expected_pan:
          raise GSTINValidationError(
              f"PAN mismatch: Registration PAN '{new_pan}' does not match company PAN '{expected_pan}'."
          )
  ```

- **Detected by Existing Tests?**
  **NO.**

---

## 3. Structural Invariants Assessment

| Architectural Invariant | Code Mechanism | Audit Finding |
|---|---|---|
| **Multi-State Support** | `GSTRegistration` has `state_code` indexed, supports 1..N registrations per company. | **VERIFIED.** |
| **Tenant Isolation** | Foreign key `company_id` on all registrations; queried via `company=company`. | **VERIFIED.** Cross-tenant access returns 403 Forbidden. |
| **Duplicate Prevention** | `unique_together = ('company', 'gstin')` + Python duplicate check. | **VERIFIED.** Cannot register the same GSTIN twice for a company. |
| **Primary Auto-Promotion** | If first registration, `is_primary` automatically forced to `True`. | **VERIFIED.** Guarantees every company has at least one primary registration. |
| **Primary Exclusivity** | Atomically unsets previous primary when new primary is chosen. | **PARTIALLY VERIFIED.** Works sequentially; missing DB partial unique constraint for concurrency (Finding REG-02). |
| **Company Model Sync** | Syncs primary GSTIN and state to `Company` model fields. | **VERIFIED.** Preserves legacy invoice templates. |

---

## 4. Verdict & Release Readiness

**Dimension Verdict:** **FAIL (REMEDIATION REQUIRED BEFORE GA)**  
The core multi-GSTIN domain model is well-structured and handles tenant boundaries properly. However, **Finding REG-01 (Missing RBAC on registration mutations)** and **Finding REG-02 (Missing DB partial unique constraint for primary)** represent real security and reliability risks that must be fixed prior to production deployment.
