# SRI LEKH — STAGE 1.2.4 SMTP AND RECOVERY REPORT

**Assessment Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Overall Status:** **PARTIALLY VERIFIED / BLOCKED ON LIVE SMTP CREDENTIALS**

---

## 1. Audited Code & Timeout Resiliency Controls

Verified in [`config/settings.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/settings.py#L466-L476), [`apps/notifications/email_service.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/email_service.py), and [`apps/accounts/views.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/views.py):
- **Bounded Socket Timeout:** `EMAIL_TIMEOUT = env.int('EMAIL_TIMEOUT', default=10)` prevents stalled SMTP handshakes from hanging request workers indefinitely.
- **Throttling & Anti-Enumeration:** `PasswordResetRequestView` applies `OtpInitiateRateThrottle` (`10/hour` IP) + `PasswordResetEmailRateThrottle` (`5/hour` hashed email key), minute-bucket idempotency keys, and always returns generic `200 OK` even when SMTP raises `TimeoutError`.
- **Lease-Claimed Idempotent `EmailDeliveryLog`:** Uses transactional `select_for_update()` claim tokens (`claim_token`, `claim_expires_at`), SHA-256 RFC 5322 `Message-ID`s (`<{sha256[:32]}@srilekh.com>`), and logs ambiguous transport failures as `DELIVERY_UNKNOWN` without duplicating sends.
- **Session Revocation on Recovery:** Password reset confirmation revokes all existing user tokens via `revoke_user_tokens(user)` (`token_version` increment + refresh blacklisting).

---

## 2. Observed Test Verification vs. Live Environment Blocker

- **Automated Verification (`PASS`):**
  - `test_password_reset_smtp_timeout_returns_generic_200_without_crash` (`apps.accounts.tests_play_launch_account_deletion`): passed on both SQLite and **Neon PostgreSQL 18.6 (`test_neondb_staging`)**, verifying `HTTP 200` + `EmailDeliveryLog.status == 'DELIVERY_UNKNOWN'`.
  - `apps.accounts.tests_auth_otp` + `apps.notifications.tests_stage4_15_auth`: included inside **56 / 56 passed (`OK`)** Batch A SQLite run cleanly.
- **External Live SMTP Blocker (`BLOCKED`):**
  - Local `.env` contains no SMTP credentials (`EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` default to empty in [`config/settings.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/settings.py#L470-L471); `DEBUG` uses `console.EmailBackend`).
  - Live inbox delivery via production/staging SMTP relay or transactional API remains **BLOCKED** until valid credentials and verified SPF/DKIM/DMARC sender domain records are configured in Render staging & verified via a real test inbox.
