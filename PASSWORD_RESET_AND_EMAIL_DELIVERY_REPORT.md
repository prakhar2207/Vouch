# SRI LEKH — PASSWORD RESET AND EMAIL DELIVERY REPORT

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Modules Audited:** [`apps/accounts/views.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py), [`apps/notifications/email_service.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/email_service.py), [`apps/notifications/tasks.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/tasks.py), [`config/settings.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/settings.py)

---

## 1. Security & Timeout Resilience Assessment

1. **Bounded SMTP Timeout & Non-Blocking Error Isolation:**
   - [`config/settings.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/settings.py) sets `EMAIL_TIMEOUT = env.int('EMAIL_TIMEOUT', default=10)` so stalled SMTP handshakes fail cleanly within 10 seconds instead of exhausting worker request timeouts.
   - [`EmailService`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/email_service.py) uses SHA-256 hashed RFC 5322 `Message-ID`s (`<{sha256[:32]}@srilekh.com>`), transactional `select_for_update()` claim tokens with lease expiration (`claim_token`, `claim_expires_at`), and marks socket/timeout failures explicitly as `DELIVERY_UNKNOWN` (or `RETRY_PENDING`/`FAILED`) in `EmailDeliveryLog` rather than exposing raw credentials.
2. **Account Enumeration Prevention & Rate Limiting:**
   - [`PasswordResetRequestView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py) enforces both per-IP throttling (`OtpInitiateRateThrottle`: `10/hour`) and per-email hashed cache-key throttling (`PasswordResetEmailRateThrottle`: `5/hour`), minute-bucket idempotency keys (`pwd-reset:<user_id>:<bucket>`), and catches SMTP timeouts so unknown emails, valid emails, and timed-out deliveries all return generic `200 OK` responses without leaking account existence.
3. **Token Revocation Upon Password Reset:**
   - Password reset confirmation invokes Django `default_token_generator` + `revoke_user_tokens(user)`, immediately invalidating prior access and refresh JWTs across web cookies and mobile clients.

---

## 2. Verified Automated Tests vs. External Live Blocker

- **Automated Verification (`PASS`):**
  - `test_password_reset_smtp_timeout_returns_generic_200_without_crash` (`apps.accounts.tests_play_launch_account_deletion`): simulates `TimeoutError('SMTP socket timed out')`, confirms generic `HTTP 200`, and asserts `EmailDeliveryLog.status == 'DELIVERY_UNKNOWN'`.
  - `apps.accounts.tests_auth_otp` & `apps.notifications.tests`: password reset confirmation, duplicate/idempotent email suppression, abandoned claim lease recovery, and dead-letter handling all passed (`74/74` combined Django test suite `OK`).
- **Live Staging SMTP Delivery (`BLOCKED — External Infrastructure`):**
  - End-to-end live inbox delivery on `https://vouch-u3u7.onrender.com` remains **BLOCKED** until valid transactional SMTP/relay credentials (`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, or API relay) are provisioned in Render staging environment variables.
