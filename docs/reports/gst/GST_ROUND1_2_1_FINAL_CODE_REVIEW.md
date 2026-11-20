# SRI LEKH — GST ROUND 1.2.1 FINAL CODE REVIEW & AUDIT REPORT
**Audited Target:** SriLekh GST Sandbox Provider Integration & Multi-GSTIN Management  
**Git Commit Audited:** `8860b99ac3f13db1c554b7d9b0a559a79c5a927e`  
**Git Branch:** `fix/stage4-12-day6-remediation`  
**Auditor Roles:** Principal Software Architect, Senior Django Security Engineer, GST Integration Specialist, Accounting Systems Auditor, QA Lead  
**Audit Type:** Static Code Review & Security Verification (Strictly No Deployment)  
**Date:** 2026-11-16  

---

## 1. Executive Summary

This comprehensive audit independently reviews the implementation of Round 1.2 of SriLekh's **Sandbox GST Integration** at commit `8860b99ac3f13db1c554b7d9b0a559a79c5a927e`.

The scope includes encryption and credential lifecycle (`apps/gst/encryption.py`), provider API client and token management (`apps/gst/services/sandbox_client.py`), Luhn MOD-36 verification and taxpayer caching (`apps/gst/services/gstin_service.py`), multi-GSTIN management (`apps/gst/services/registration_service.py`), HTTP endpoints and permissions (`apps/gst/views.py`, `apps/gst/permissions.py`), double-entry accounting safety (`apps/accounting/`), and the Next.js frontend (`frontend/src/components/settings/GSTRegistrationsView.tsx`).

### Overall Audit Verdict: **NO-GO FOR PRODUCTION DEPLOYMENT**
While the subsystem demonstrates outstanding architectural foundations—particularly in local format validation, credential redaction, non-interference with double-entry ledgers, and standard encryption roundtrips—the audit identified **3 P1 High-Severity Flaws** and **6 P2 Medium-Severity Flaws** that prevent production release certification.

---

## 2. Master Findings Register

| Finding ID | Severity | File & Location | Issue Description | Impact |
|---|---|---|---|---|
| **ENC-01** | **P1** | `apps/gst/encryption.py`: 85–98 | Key rotation does not re-encrypt database records at rest; removing old key causes permanent data loss | High |
| **REG-01** | **P1** | `apps/gst/views.py`: 554, 607, 693 | Missing RBAC on registration mutations (EMPLOYEE/VIEWER can add or deactivate company GSTINs) | High |
| **ACC-01** | **P1** | `apps/gst/views.py`: 776–786 | Missing RBAC on party enrichment endpoint (VIEWER can mutate supplier/customer ledgers) | High |
| **CLI-01** | **P1** | `apps/gst/services/sandbox_client.py`: 111–116 | Token stampede and redundant `/authenticate` calls when `CompanyGSTConfig` is not persisted | High |
| **ENC-02** | **P2** | `apps/gst/encryption.py`: 140–144 | Plaintext pass-through bypass in `decrypt_gst_credential()` violates fail-closed security | Medium |
| **CLI-02** | **P2** | `apps/gst/services/sandbox_client.py`: 135–136 | Incomplete expiry parsing for nested `expires_in` defaults token lease to 24h instead of 1h | Medium |
| **CLI-03** | **P2** | `apps/gst/services/sandbox_client.py`: 256, 304 | Outbound API requests without `company` bypass audit trail persistence | Medium |
| **CCH-01** | **P2** | `apps/gst/services/gstin_service.py`: 220–237 | Stale cache returned as `success: True` on network exception during explicit `force_refresh` | Medium |
| **REG-02** | **P2** | `apps/gst/models.py`: 140–147 | Lack of PostgreSQL partial unique constraint for `is_primary=True` risks duplicate primaries under race | Medium |
| **REG-03** | **P2** | `apps/gst/services/registration_service.py`: 90–98 | PAN stem consistency not enforced across multi-state company registrations | Medium |
| **ACC-02** | **P2** | `apps/gst/views.py`: 787–803 | `PartyEnrichmentApplyAPIView` checks `hasattr(party, 'legal_name')`, silently failing to update `party.name` | Medium |
| **ACC-03** | **P2** | `apps/gst/views.py`: 801–808 | Direct model update in `PartyEnrichmentApplyAPIView` bypasses `GSTAuditService` logging | Medium |
| **FE-01** | **P2** | `frontend/.../GSTRegistrationsView.tsx`: 408–421 | UI unconditionally displays "Portal Verified" badge even on local cache or offline fallback | Medium |
| **FE-02** | **P2** | `frontend/.../GSTRegistrationsView.tsx`: 149–160 | User can save unverified GSTIN without explicit confirmation dialog | Medium |
| **ENC-03** | **P3** | `apps/gst/encryption.py`: line 48 | Fragile test detection via `'test' in sys.argv` | Low |
| **CCH-02** | **P3** | `apps/gst/services/gstin_service.py`: 189–199 | Fragile date parsing ignores ISO-8601 timestamps with millisecond offsets | Low |
| **FE-03** | **P3** | `frontend/.../GSTRegistrationsView.tsx`: 188–201 | Missing confirmation dialog on registration deactivation | Low |
| **FE-04** | **P3** | `frontend/.../GSTRegistrationsView.tsx`: line 348 | Modal container overflows viewport on mobile devices (< 700px height) | Low |

---

## 3. Independent Assessment Across the 10 Dimensions

### Dimension 1: Encryption & Key Management
- **Audit Findings:** MultiFernet provides excellent in-memory fallback. Fallback to `SECRET_KEY` in staging/production is strictly disabled (verified). However, rest-at-rest database re-encryption is not automatic (ENC-01), and plaintext pass-through needs production gating (ENC-02).
- **Dimension Verdict:** **CONDITIONAL PASS** (Requires management command for rotation re-encryption).

### Dimension 2: Provider API Client Architecture
- **Audit Findings:** Base URL resolution, timeout controls (12s auth, 15s API), and idempotent/non-idempotent retry segregation are exemplary. `requests.request` is used cleanly with proper header injection.
- **Dimension Verdict:** **PASS**

### Dimension 3: Authentication & Token Lifecycle
- **Audit Findings:** Two-legged JWT exchange works well for single-company workflows. However, missing cache fallbacks for platform credentials cause token stampedes (CLI-01), and nested `expires_in` parsing is defective (CLI-02).
- **Dimension Verdict:** **FAIL** (Must remediate CLI-01 and CLI-02 before production scale).

### Dimension 4: Rate Limiting, Backoff & Resilience
- **Audit Findings:** Clear segregation: idempotent endpoints (`search_taxpayer`) employ exponential backoff with sleep on HTTP 429; non-idempotent endpoints (`generate_einvoice`, `cancel_einvoice`, `request_portal_otp`) fail closed without blind retries.
- **Dimension Verdict:** **PASS**

### Dimension 5: Audit Logging & Credential Redaction
- **Audit Findings:** `GSTAuditService` recursively sanitizes sensitive keys (`api_key`, `secret`, `password`, `token`, `otp`) replacing them with `"REDACTED"`. Zero credential leakage into PostgreSQL logs. However, the view-level party enrichment endpoint bypasses logging (ACC-03).
- **Dimension Verdict:** **CONDITIONAL PASS** (Remediate ACC-03).

### Dimension 6: GSTIN Verification & Cache Integrity
- **Audit Findings:** Indian GST Luhn MOD-36 checksum calculation is mathematically exact. The 24-hour statutory TTL is strictly respected. Dirty caching is prevented. However, network timeouts during explicit `force_refresh` fall back to stale cache with `success: True` (CCH-01).
- **Dimension Verdict:** **CONDITIONAL PASS** (Remediate CCH-01).

### Dimension 7: Multi-GSTIN Architecture & Invariants
- **Audit Findings:** Multi-state modeling is clean and handles primary switching sequentially. However, intra-company RBAC is completely missing on mutation endpoints (REG-01), and database-level partial unique constraints are absent (REG-02).
- **Dimension Verdict:** **FAIL** (Security and data integrity blockers).

### Dimension 8: Accounting Invariant Preservation
- **Audit Findings:** Double-entry accounting invariants (`Debits == Credits`, natural balance directions) are 100% preserved. GST operations cause zero mutations to vouchers or financial balances. However, `PartyEnrichmentApplyAPIView` lacks RBAC (ACC-01) and fails to update party `name` (ACC-02).
- **Dimension Verdict:** **FAIL** (Party master enrichment bugs).

### Dimension 9: Frontend UX & Portal Distinction
- **Audit Findings:** Clean Next.js implementation with clear loading states and toasts. However, it displays a false "Portal Verified" badge when results are served from cache or offline fallback (FE-01).
- **Dimension Verdict:** **CONDITIONAL PASS** (Remediate FE-01).

### Dimension 10: Test Coverage & Gap Analysis
- **Audit Findings:** 15/15 foundation tests pass, but 8 major blind spots exist covering concurrency, RBAC boundaries, database key rotation, and HTTP views.
- **Dimension Verdict:** **FAIL** (Test harness expansion required).

---

## 4. Overall Release Certification

```text
================================================================================
FINAL CERTIFICATION DECISION: NO-GO FOR PRODUCTION RELEASE
Target Commit: 8860b99ac3f13db1c554b7d9b0a559a79c5a927e
Branch: fix/stage4-12-day6-remediation
================================================================================
Critical Blockers:
1. [P1] Missing RBAC on registration mutations and party enrichment endpoints (REG-01, ACC-01)
2. [P1] Key rotation does not re-encrypt database records at rest (ENC-01)
3. [P1] Token stampede on missing CompanyGSTConfig (CLI-01)
4. [P2] Party enrichment HTTP endpoint silently ignores legal_name (ACC-02)
5. [P2] Missing database-level partial unique constraint for primary GSTIN (REG-02)
6. [P2] False "Portal Verified" badge on cached/offline fallbacks (FE-01)
================================================================================
```

---

## 5. Prioritized Remediation Roadmap for Round 1.3

### Phase 1: Security & RBAC Enforcement (Immediate)
1. In `apps/gst/views.py`: Apply `CanManageGSTCredentials` or `user_has_company_roles(..., ['ADMIN', 'OWNER'])` to `GSTRegistrationListCreateAPIView.post`, `GSTRegistrationDetailAPIView.put`, `GSTRegistrationDeactivateAPIView.post`, and `PartyEnrichmentApplyAPIView.post`.
2. Refactor `PartyEnrichmentApplyAPIView` to invoke `GSTINService.apply_party_enrichment()`, ensuring `party.name` is updated and `GSTAuditLog` is persisted.

### Phase 2: Cryptographic & Token Resiliency (Immediate)
3. In `apps/gst/services/sandbox_client.py`: Implement Django cache fallback (`cache.get/cache.set`) for JWT tokens with distributed locking to eliminate token stampedes.
4. Correct `expires_in` parsing to inspect nested `data.get('data', {}).get('expires_in')`.
5. Implement management command `rotate_gst_credentials` to re-encrypt records at rest.

### Phase 3: Integrity & Concurrency Hardening
6. Add `UniqueConstraint(fields=['company'], condition=Q(is_primary=True))` to `GSTRegistration.Meta`.
7. Enforce PAN stem consistency check across registrations in `create_registration()`.
8. Guard cache exception fallback so that `force_refresh=True` returns an error rather than stale cache.

### Phase 4: Frontend & UX Alignment
9. Update `GSTRegistrationsView.tsx` to distinguish "Portal Verified (Live)" from "Verified via Cache" and "Format Validated (Gateway Offline)".
10. Add confirmation dialogs for unverified saves and registration deactivations.

### Phase 5: Test Suite Expansion
11. Implement the 8 targeted test cases documented in `GST_ROUND1_2_1_TEST_COVERAGE_GAPS.md` and verify 100% pass rate.
