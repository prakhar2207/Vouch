# SRI LEKH GST — ROUND 2.5.17
# Deliverable 5: Rate Limiting, OTP Challenge Binding & Session Semantics Report

**Repository**: https://github.com/prakhar2207/Vouch  
**Production Application**: https://srilekh.com  
**Audit Date**: November 23, 2026  
**Auditor**: Application Security Engineer & Systems Architect  
**Dedicated Test Tenant**: `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  

---

## 1. Rate Limiting & Brute-Force Defense

To prevent OTP spamming and protect taxpayer accounts against brute-force attacks:
1. **Server-Enforced Cooldown**:
   - 30-second cooldown per `(company_id, gstin)`.
   - Repeated requests within the cooldown window return `COOLDOWN_ACTIVE` with remaining seconds.
2. **Hourly Rate Limit**:
   - Maximum 5 OTP requests per hour per `(company_id, gstin)`.
   - Exceeding the threshold returns `RATE_LIMIT_EXCEEDED` with a retry delay advisory.
3. **Cryptographically Bound Challenge IDs**:
   - Every OTP generation request creates a random `CHAL-<uuid>` challenge token.
   - Binds `(company_id, gstin, username)` in cache for 10 minutes.
   - Verification requests must prove challenge ownership; cross-company verification is rejected with `INVALID_CHALLENGE`.
   - Maximum 5 incorrect OTP attempts allowed per challenge before permanent invalidation (`MAX_ATTEMPTS_EXCEEDED`).

---

## 2. Session Lifecycle: Disconnect & Refresh Semantics

1. **Remote Logout & Local Revocation**:
   - `disconnect_portal_session` immediately clears the encrypted token and expiry locally.
   - Dispatches a remote invalidation request to the gateway provider (`POST /logout`).
   - Differentiates confirmed remote logout (`remote_status: "CONFIRMED"`) from local-only invalidation (`remote_status: "NOT_CONFIRMED"`).
2. **Session Extension (Refresh)**:
   - `refresh_portal_session` contacts the provider refresh endpoint.
   - Validates refreshed token schema, minimum length, and future expiry.
   - If the provider rejects the session (e.g. taxpayer revoked permissions on GSTN), SriLekh invalidates the local session immediately to prevent stale states.

---

## 3. Verification Test Evidence (Phase F & G)

| Test Case | Description | Result |
| :--- | :--- | :--- |
| `test_otp_rate_limiting_enforces_cooldown` | Second request within 30s triggers `COOLDOWN_ACTIVE`. | **PASSED** |
| `test_challenge_binding_and_rejection` | Challenge ownership mismatch triggers `INVALID_CHALLENGE`. | **PASSED** |
| `test_challenge_expired` | Non-existent or expired challenge returns `CHALLENGE_EXPIRED`. | **PASSED** |
| `test_disconnect_local_and_remote` | Revokes local token, executes remote logout, returns `remote_status`. | **PASSED** |
| `test_refresh_session_extends_active_session` | Refreshes session and updates token and expiry in database. | **PASSED** |

---

## 4. Phase F & G Certification

**STATUS: CERTIFIED & COMPLIANT**  
Rate limiting, challenge binding, and session lifecycle management provide robust security and operational resilience.
