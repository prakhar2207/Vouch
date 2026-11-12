# SRI LEKH — ACCOUNT DELETION SECURITY CERTIFICATION

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Modules Certified:**
- Backend: [`AccountDeletionView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py), [`AccountDeletionStatusView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py), [`AccountDeletionRateThrottle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py), [`AccountDeletionRequest`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/models.py), [`0008_accountdeletionrequest.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/migrations/0008_accountdeletionrequest.py)
- Frontend: `/delete-account` (`frontend/src/app/delete-account/page.tsx`) & `Settings -> Account Profile`
- Test Suite: [`tests_play_launch_account_deletion.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/tests_play_launch_account_deletion.py)

---

## 1. Stage 1.2.3 Security Hardening Applied

1. **Row-Locked Concurrency Safety (`select_for_update()` Inside `transaction.atomic()`):**
   - Moved password re-verification, `User` anonymization-state check (`ACCOUNT_ALREADY_DELETED` -> `409 Conflict`), active `UserCompany` row locks, `_analyze_user_company_ownership(locked_user)`, and `Company` row locks **inside** `with transaction.atomic():` using `User.objects.select_for_update()`.
   - Eliminates double-deletion TOCTOU race conditions and concurrent ownership-transfer races on PostgreSQL.
2. **Dedicated Per-User Rate Throttling (`AccountDeletionRateThrottle`):**
   - Added `AccountDeletionRateThrottle` (`rate = '10/hour'`, `scope = 'account_deletion'`) to [`AccountDeletionView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py) to protect password re-authentication against automated brute-force guessing.
3. **Complete Non-Statutory Erasure & Device Revocation:**
   - Inside the atomic deletion transaction, clears/revokes:
     - `UserCompany` memberships
     - `PushSubscription` & `Notification` records for the deleted user
     - Active `AuthorizedDevice` bindings (`status = 'REVOKED'`, `registered_by = None`) for archived solo companies, plus unlinks `registered_by = None` across detached devices
     - `EmailVerificationChallenge` & `PendingRegistration` rows matching the original email
     - All JWT access/refresh sessions via `revoke_user_tokens(locked_user)` (`token_version` increment + refresh blacklisting)
     - Recoverable PII on `User` (`first_name=''`, `last_name=''`, `email='deleted-<uuid>@anonymized.srilekh.invalid'`, `set_unusable_password()`, `is_active=False`, `email_verified=False`)
   - Clears browser auth cookies cleanly on HTTP `200` response.
4. **Statutory Double-Entry Integrity & Zero-PII Receipt:**
   - Posted double-entry `Voucher` rows, tax ledgers, and SHA-256 hash-chained `AuditLog` entries retain FK integrity against the anonymized user record; solo-user workspaces require explicit `sole_company_action='ARCHIVE_SOLO_COMPANIES'` (`409` otherwise), while multi-member workspaces block deletion until ownership transfer (`409 OWNERSHIP_TRANSFER_REQUIRED`).
   - [`AccountDeletionStatusView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py) (`GET /api/v1/auth/account/delete-status/?reference=<uuid>`) returns status/metadata with zero recoverable email/PII (`AccountDeletionRequest` stores SHA-256 email digest & masked label internally).

---

## 2. Observed Verification Evidence

- **SQLite Isolated Suite (`apps.accounts.tests_play_launch_account_deletion`):** **`7 / 7` tests passed (`OK`)**, verifying unauth `401`, bad password `403`, wrong confirmation phrase `400`, sole-owner multi-user block `409`, solo-company archive flag check `409` -> `200`, `AuthorizedDevice` revocation (`REVOKED`, `registered_by=None`), `Notification` deletion, `AuditLog` preservation, stale JWT `401`, refresh replay `401`, zero-PII status check, and locked already-anonymized rejection `409`.
- **Neon PostgreSQL 18.6 (`test_neondb_staging --keepdb`):** Passed inside **`26 / 26` OK** (`apps.accounts.tests_play_launch_account_deletion` + `apps.accounts.tests_stage1_2_auth_cookies` + `apps.accounting.tests_voucher_occ`).
- **Playwright Chromium Edge E2E (`http://127.0.0.1:3000` + `:8000`):** Verified end-to-end cookie-authenticated deletion (`200`), subsequent `/api/v1/auth/me/` rejection (`401`), and non-PII status receipt (`200`).
- **Pending External Deployment:** `/delete-account` and `AccountDeletionView` are not yet pushed/deployed to live Render staging (`f8578a88`) or live `https://srilekh.com` (`main` untouched per release safety rules).
