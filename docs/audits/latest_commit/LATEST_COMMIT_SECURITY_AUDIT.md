# LATEST COMMIT SECURITY & MULTI-TENANT AUTHORIZATION AUDIT

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Target Commit:** `08cd3b8bc3ab2cf15293400c3e703c4a318ebbe8`  
**Audit Date:** November 13, 2026  
**Auditor Roles:** Principal Security Architect & Lead Security Auditor  

---

## 1. Executive Security Evaluation

This security audit conducted an in-depth review of commit `08cd3b8bc3ab2cf15293400c3e703c4a318ebbe8` across multi-tenant data boundaries, session management, credential protection, token storage modes, access control matrices, and tamper-evident audit logging.

**Verdict:** **PASSED WITH ZERO CRITICAL VULNERABILITIES**. Multi-tenant isolation is strictly enforced via database-level foreign keys, ORM-enforced tenant filtering, and cryptographically signed session tokens.

---

## 2. Multi-Tenant Isolation & IDOR Defense

SriLekh operates as a shared-schema, multi-tenant B2B accounting system where tenant data is segregated using `company_id` foreign keys.

### 2.1 Cross-Tenant Leakage Prevention
* Every query within `apps/accounting`, `apps/inventory`, and `apps/banking` scopes queries through `request.company` or `get_active_company(request)`.
* IDOR (Insecure Direct Object Reference) testing verified that attempting to retrieve, edit, reverse, or cancel a voucher, ledger account, or bank transaction belonging to Tenant A while authenticated as Tenant B results in an immediate `HTTP 404 Not Found` or `HTTP 403 Forbidden`.
* Database foreign keys enforce `ON DELETE CASCADE` or `PROTECT` with company scoping. Orphaned records are strictly disallowed.

### 2.2 Production Tenant Invariant Enforcement
* Production tenant **`Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`)** was verified completely isolated from staging, automated CI runs, and developer scratch benchmarks.
* The test suite mandates an explicit assertion:
  ```python
  assert str(company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"
  ```

---

## 3. Authentication & Credential Storage Architecture

### 3.1 Browser Token Storage Mode (Zero LocalStorage Token Exposure)
* In standard web browser sessions (`https://srilekh.com`), JWT authentication tokens (`access_token` and `refresh_token`) are transmitted and stored **exclusively in `HttpOnly`, `SameSite=Lax`, `Secure` cookies**.
* `localStorage` and `sessionStorage` contain **ZERO** plaintext JWT tokens, eliminating XSS token theft vectors.
* Frontend security tests (`src/lib/sync/offline-sync.test.ts`) assert that `window.localStorage.getItem('token')` and `document.cookie` return null/unreadable values for authentication tokens.

### 3.2 Native Capacitor Token Storage Mode
* In native Android packaging (`isCapacitorNative() === true`), cookies are not maintained across background service boundaries.
* The application utilizes `@capacitor/preferences` hardware-backed private storage for token persistence.
* Explicit user logout completely purges these tokens from native storage.

### 3.3 CSRF Protection
* All state-mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`) require Django's double-submit CSRF token.
* The frontend reads the `csrftoken` cookie and attaches it via the `X-CSRFToken` request header.
* Registration and login initiation endpoints utilize `CsrfExemptMixin` where unauthenticated onboarding requires public access, protected instead by rate throttles and advisory locks.

---

## 4. Role-Based Access Control (RBAC) Matrix

SriLekh enforces a granular 5-tier role hierarchy per tenant:

| Permission / Action | OWNER | ADMIN | CA (Chartered Accountant) | EMPLOYEE | VIEWER |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Manage Company Settings / Subscription** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Manage Users & Role Assignments** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Create & Post Sales Invoices** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Create & Post Purchase Invoices** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Create Manual Journals & Contra Vouchers**| ✅ | ✅ | ✅ | ❌ | ❌ |
| **Bank Statement Ingestion & Reconciliation**| ✅ | ✅ | ✅ | ❌ | ❌ |
| **Delete Draft Vouchers** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Financial Statement Reports (P&L, Bal Sheet)**| ✅ | ✅ | ✅ | ✅ (Limited) | ✅ (Read) |
| **Export Audit Logs & Ledgers** | ✅ | ✅ | ✅ | ❌ | ❌ |

---

## 5. Rate Limiting & Denial of Service Protection

SriLekh enforces strict throttling tiers to prevent denial-of-service, credential stuffing, and OTP exhaustion:

1. **`OtpInitiateRateThrottle`**: `10/hour` per client IP. Protects `/api/v1/auth/register/initiate/` and `/api/v1/auth/register/resend-otp/`.
2. **`PasswordResetEmailRateThrottle`**: `5/hour` per normalized email hash. Protects password reset endpoints against email flooding.
3. **`LoginRateThrottle`**: `15/minute` per client IP. Prevents automated brute-force attacks on user passwords.
4. **`AccountDeletionRateThrottle`**: `10/hour` per authenticated user. Prevents rapid tenant deletion abuse.
5. **PostgreSQL Advisory Locks**: `pg_advisory_xact_lock` prevents concurrent registration hijacking on identical email addresses.

---

## 6. Audit Trail & Cryptographic Tamper-Evidence

* Every posted accounting voucher, bank match, and tenant configuration change writes an immutable record to `apps.audit.AuditLog`.
* Audit records include:
  - `tenant_id`, `actor_user_id`, `client_ip`, `action_type`, `resource_type`, `resource_id`.
  - Structured `before_state` and `after_state` JSON diffs.
  - Cryptographic **SHA-256 hash chaining**: each entry's hash is computed as `SHA-256(previous_hash + timestamp + actor + action + state_payload)`.
* Any out-of-band database update or row deletion invalidates the chain and is flagged during audit trail verification.
