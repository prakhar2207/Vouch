# SRI LEKH — ACCOUNT DELETION IMPLEMENTATION REPORT

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Target Public Web URL:** `https://srilekh.com/delete-account` *(ready in code; pending approved deployment to `srilekh.com`)*  
**In-App Path:** `Settings → Account Profile → Permanent Account Deletion → Delete My Account`

---

## 1. Architecture & Components Implemented

### A. Backend API & Database Model
- **Model:** [`AccountDeletionRequest`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/models.py) + migration [`apps/accounts/migrations/0008_accountdeletionrequest.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/migrations/0008_accountdeletionrequest.py) (`makemigrations --check --dry-run` clean).
  - Stores `id` (UUID reference receipt), nullable `user` FK (`SET_NULL`), `user_snapshot_id`, `email_sha256` digest, `masked_email` (`ow***@domain`), `status`, `sole_owned_company_ids`, `company_resolution`, `reason`, `retention_summary`, `ip_address`, `verified_at`, `completed_at`.
  - Avoids retaining recoverable plaintext personal email in audit tables after deletion.
- **Authenticated Preview & Execution View:** [`AccountDeletionView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py) mounted at `GET/POST /api/v1/auth/account/delete-request/`:
  - **Authentication & CSRF:** `IsAuthenticated` via [`CookieJWTAuthentication`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/authentication.py); unsafe `POST` enforces Django CSRF validation for browser cookies and Bearer auth for Capacitor native clients. Superuser accounts are explicitly blocked (`403`).
  - **Impact Inspection (`GET`):** Categorizes active companies into `sole_owned_requires_transfer` (other active members present), `sole_owned_single_user` (sole user only), and `detachable_memberships`.
  - **Identity & Intent Confirmation (`POST`):**
    1. Password re-authentication (`user.check_password(current_password)` -> fails closed `403` if invalid/missing).
    2. Exact typed confirmation phrase (`confirmation_text == "DELETE MY ACCOUNT"` -> `400` if mismatched).
  - **Multi-Tenant & Ownership Protections:**
    - If `sole_owned_requires_transfer` is non-empty, aborts with **`409 Conflict` (`OWNERSHIP_TRANSFER_REQUIRED`)** and directs the user to transfer Ownership in `Settings → Team Access` — preventing multi-user tenants from becoming orphaned/locked.
    - If `sole_owned_single_user` is non-empty and `sole_company_action != "ARCHIVE_SOLO_COMPANIES"`, aborts with **`409 Conflict` (`SOLE_COMPANY_CONFIRMATION_REQUIRED`)**.
    - Never permits deleting another user's account or archiving any shared company where another active user or `OWNER`/`ADMIN` exists.
  - **Atomic Erasure & Legal Accounting Preservation (`transaction.atomic()`):**
    - Records tamper-evident SHA-256 hash-chained `AuditLog` entries for workspace detachment / solo-company archival (`is_active=False`, `deleted_at=now`).
    - Deletes `UserCompany` memberships, `PushSubscription` endpoints, `EmailVerificationChallenge`, and `PendingRegistration` rows.
    - Revokes all active JWT access and refresh sessions immediately via `revoke_user_tokens(user)` (`token_version` increment + `OutstandingToken` blacklist) and clears auth cookies.
    - Permanently anonymizes personal `User` identity (`first_name=""`, `last_name=""`, `email="deleted-<uuid>@anonymized.srilekh.invalid"`, `set_unusable_password()`, `is_active=False`, `email_verified=False`) while keeping `Voucher.created_by` & ledger/audit FK integrity intact.
- **Non-PII Public Status Receipt Endpoint:** [`AccountDeletionStatusView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py) mounted at `GET /api/v1/auth/account/delete-status/?reference=<uuid>` (`AllowAny`, throttled `20/hour`). Returns strictly `reference_id`, `status`, `company_resolution`, timestamps, and retention notice — zero email or tenant names.

### B. Frontend Web & In-App UI
- **Public + Authenticated Web Portal:** [`frontend/src/app/delete-account/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/delete-account/page.tsx)
  - Publicly accessible without login (`PublicHeader` + `PublicFooter`, allowed in [`robots.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/robots.ts) & [`sitemap.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/sitemap.ts)).
  - Guides logged-out users through `/login?next=/delete-account` (support for safe relative `?next=` added to [`login/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/login/page.tsx)) or support email fallback.
  - Executes `removeTokens({ wipeLocalDeviceData: true, broadcastReason: "logout" })` upon completion so `VouchOfflineDB`, `VouchSecurityVault`, `vouch_*` keys, and Service Worker caches are erased locally too.
- **In-App Entry Point:** [`frontend/src/app/settings/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/settings/page.tsx) (`account-profile` tab) displays the **Permanent Account Deletion** card with direct link to `/delete-account`.

---

## 2. Verification Evidence

| Check | Scope / Assertion | Result | Status |
| :--- | :--- | :--- | :--- |
| Django Unit/API Tests ([`tests_play_launch_account_deletion.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/tests_play_launch_account_deletion.py)) | Unauth `401`, bad password `403`, bad phrase `400`, sole-owner multi-member `409 OWNERSHIP_TRANSFER_REQUIRED`, solo archive confirmation `409 -> 200`, `User` PII anonymized (`@anonymized.srilekh.invalid`, `is_active=False`), `token_version` bumped & pre-existing Bearer token `401`, non-PII status check `200`. | Passed inside SQLite (`11/11`) and Neon PostgreSQL `test_neondb_staging` | **Verified PASS** |
| Live Browser E2E (Playwright `msedge` + `next start` + isolated Django) | Logged-out `/delete-account` -> `/login?next=/delete-account` -> solo company impact loaded -> checkbox + password + `DELETE MY ACCOUNT` -> `COMPLETED` receipt + zero `eyJ` JWTs in DOM + simulated Capacitor footer still shows `Delete Account`. | Passed (`exit 0`, zero console errors) | **Verified PASS** |
| Live Production `https://srilekh.com/delete-account` URL | Not yet deployed to `main` / production Vercel per safety rules (`Never merge into main without approval`). | Pending deployment approval | **BLOCKED / OWNER ACTION REQUIRED** |
| Statutory Retention Period Confirmation (years) | Explicitly marked `[Pending Owner & Legal Counsel Confirmation]` in `/delete-account` & `/privacy-policy` — never invented. | Pending Owner & Legal Counsel | **OWNER ACTION REQUIRED** |
