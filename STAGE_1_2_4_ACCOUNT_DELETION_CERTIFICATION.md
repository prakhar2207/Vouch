# SRI LEKH — STAGE 1.2.4 ACCOUNT DELETION CERTIFICATION

**Assessment Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Overall Gate Status:** **CONDITIONAL PASS** *(Backend Row-Locking, Audit Chain, Rate Limit & Local Browser E2E Passed 100%; Live Deployment on `srilekh.com` & Staging API Pending)*

---

## 1. Audited Architecture & Invariants Verified

Audited [`AccountDeletionView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py#L1011-L1206), [`AccountDeletionStatusView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py#L1209-L1237), [`AccountDeletionRateThrottle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py#L73-L75), [`revoke_user_tokens`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/cookies.py#L209-L223), and [`/delete-account`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/delete-account/page.tsx):

1. **Authentication, Password Re-Auth & Confirmation Phrase:**
   - Unauthenticated requests rejected (`401 Unauthorized`).
   - Empty or wrong `current_password` rejected inside atomic lock (`403 Forbidden`).
   - Wrong phrase rejected cleanly unless exact `"DELETE MY ACCOUNT"` (`400 Bad Request`).
   - Platform superuser self-deletion blocked (`403 Forbidden`).
2. **Ownership & Multi-Tenant Safety:**
   - Sole `OWNER`/`ADMIN` of a multi-member active workspace blocked with `409 OWNERSHIP_TRANSFER_REQUIRED` until ownership transfer.
   - Sole owner of a single-user workspace requires explicit `sole_company_action == 'ARCHIVE_SOLO_COMPANIES'` (`409 SOLE_COMPANY_CONFIRMATION_REQUIRED` otherwise).
3. **True PostgreSQL Concurrency Safety (`select_for_update()`):**
   - `User.objects.select_for_update().filter(pk=request.user.pk)` + `UserCompany.objects.select_for_update()` + `Company.objects.select_for_update()` serialize parallel delete requests.
   - Executed a live multi-threaded `TransactionTestCase` (`ThreadPoolExecutor(max_workers=2)` behind `threading.Barrier(2)`) against **Neon PostgreSQL 18.6 (`test_neondb_staging`)**: one worker completed (`200 OK`) and the concurrent worker returned **`409 Conflict` (`ACCOUNT_ALREADY_DELETED`)**, leaving `AccountDeletionRequest.objects.filter(user_snapshot_id=owner.id).count() == 1`.
4. **Rate Throttle Enforcement:**
   - Verified `AccountDeletionRateThrottle` (`10/hour`) with `TESTING=False, DISABLE_THROTTLING=False`: requests 1–10 returned `200`, request #11 returned **`429 Too Many Requests`**.
5. **Non-Statutory Cleanup & Cryptographic `AuditLog` Preservation:**
   - Removes `UserCompany`, `PushSubscription`, `Notification`, `EmailVerificationChallenge`, and `PendingRegistration`; revokes active `AuthorizedDevice` rows (`status='REVOKED'`, `registered_by=None`); increments `User.token_version` & blacklists outstanding refresh tokens; clears browser cookies.
   - Anonymizes `User` (`deleted-<uuid>@anonymized.srilekh.invalid`, `is_active=False`, unusable password) while preserving the `User` row FK so SHA-256 hash-chained `AuditLog` entries retain unbroken continuity.
   - Verified via `AuditLogListView.verify_company_chain_telemetry(comp)` pre-deletion + post-deletion: **`status == 'VERIFIED'`**, `invalid_records_count == 0`, while unrelated bystander users/companies remained completely untouched.
6. **Public Zero-PII Receipt Lookup:**
   - Verified `GET /api/v1/auth/account/delete-status/?reference=<uuid>` returns `COMPLETED` metadata without exposing original email or PII.

---

## 2. Verification Summary

| Check | Target | Observed Outcome |
| :--- | :--- | :--- |
| **`apps.accounts.tests_play_launch_account_deletion` (10 tests)** | Neon PostgreSQL 18.6 (`test_neondb_staging --keepdb`) | **10 / 10 PASSED (`OK`, 0 skipped)** inside `15 / 15` combined PG security run |
| **`apps.accounts.tests_play_launch_account_deletion` (10 tests)** | Isolated SQLite | **9 / 9 non-MVCC PASSED (`OK`)**, 1 PG-MVCC concurrency test skipped cleanly with explicit Neon reason |
| **Playwright Chromium Edge E2E (`:3000` + `:8000`)** | Built Next.js + isolated SQLite | **PASS** — interactive cookie login -> `/delete-account` -> `200 COMPLETED` + `Reference ID` -> zero-PII status lookup |
| **Live Public `https://www.srilekh.com/delete-account` & `https://vouch-u3u7.onrender.com/api/v1/auth/account/delete-request/`** | Live deployed domains | **HTTP 404** (blocked on unpushed `feat/google-play-launch-readiness` deployment) |
