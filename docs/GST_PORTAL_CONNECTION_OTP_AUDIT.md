# SriLekh GST Portal Connection & OTP Integration Audit

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Branch:** `audit/round-2.4.6-gst-integration-reliability`  
**Audit Focus:** GST Portal Direct Connection, OTP Authentication, Session Lifecycle, and Root-Cause Investigation  
**Audit Date:** November 25, 2026  
**Auditor:** Principal Django/PostgreSQL Engineer & Application Security Specialist  

---

## 1. Authentication Architecture & Protocol Flow

Direct GST Portal integration allows SriLekh to authenticate taxpayer sessions, query live compliance statuses, synchronize GSTR-2B inward statements, and prepare returns.

### End-to-End Authentication Sequence

```
Taxpayer / UI              SriLekh API               Sandbox / GSP             GSTN Portal
     |                          |                          |                        |
     | 1. Request OTP           |                          |                        |
     |------------------------->|                          |                        |
     | (company_id, gstin)      | 2. Rate & Cooldown Check |                        |
     |                          |    (30s CD, 5/hr Limit)  |                        |
     |                          |                          |                        |
     |                          | 3. Dispatch OTP Request  |                        |
     |                          |------------------------->|                        |
     |                          |                          | 4. Forward OTP Request |
     |                          |                          |----------------------->|
     |                          |                          |    (SMS/Email sent)    |
     |                          | 5. Return Txn/Challenge  |                        |
     | 6. Challenge Bound       |<-------------------------|                        |
     |<-------------------------|                          |                        |
     |    (txn_id, 30s cd)      | (Cache: 10m TTL)         |                        |
     |                          |                          |                        |
     | 7. Submit 6-digit OTP    |                          |                        |
     |------------------------->|                          |                        |
     | (otp, txn_id, gstin)     | 8. Verify Challenge &    |                        |
     |                          |    Atomic Attempt Count  |                        |
     |                          |                          |                        |
     |                          | 9. Submit OTP to Gateway |                        |
     |                          |------------------------->|                        |
     |                          |                          | 10. Validate with GSTN |
     |                          |                          |----------------------->|
     |                          | 11. Return Session Token |<-----------------------|
     |                          |<-------------------------|                        |
     |                          |                          |                        |
     |                          | 12. Validate Token,      |                        |
     |                          |     Expiry, and GSTIN    |                        |
     |                          | 13. Persist encrypted in |                        |
     | 14. Connected (200 OK)   |     GSTRegistration      |                        |
     |<-------------------------|                          |                        |
```

---

## 2. Security Guardrails & Rate Controls

To protect taxpayer accounts and prevent brute-force attacks or provider denial-of-service, the OTP flow enforces strict server-side invariants:

| Security Control | Implementation Mechanism | Enforcement Layer | Failure Action |
|---|---|---|---|
| **Atomic Cooldown** | `gst_otp_cd_{company}_{gstin}` (30-second TTL) | Redis `cache.add()` | Returns 400 `COOLDOWN_ACTIVE` with remaining seconds |
| **Hourly Rate Limit** | `gst_otp_hr_{company}_{gstin}` (1-hour TTL) | Redis `cache.incr()` | Returns 400 `RATE_LIMIT_EXCEEDED` after 5 attempts |
| **Challenge Binding** | `gst_chal_{txn_id}` (10-minute TTL) | Django Redis Cache | Rejects unissued or expired challenges (`CHALLENGE_EXPIRED`) |
| **Tenant & User Scope** | Cryptographically bound company & user ID | Django Redis Cache | Rejects cross-tenant attempts (`CHALLENGE_OWNERSHIP_MISMATCH`) |
| **Brute-Force Shield** | `gst_chal_att_{txn_id}` (Atomic counter) | Redis `cache.incr()` | Locks out and deletes challenge after 5 failed tries (`MAX_ATTEMPTS_EXCEEDED`) |
| **Token Validation** | Checks token length, structure, and future expiry | Python Service Layer | Rejects dummy tokens, correlation IDs (`INVALID_SESSION_TOKEN`) |
| **Encrypted Storage** | AES-256-GCM at rest | PostgreSQL Model | Stored encrypted in `GSTRegistration.auth_token` |

---

## 3. Investigation & Root Cause of Reported OTP Delivery Failure

### 3.1 The Issue
During end-user testing, users reported: *"I clicked 'Connect to GST Portal' and requested an OTP, but no SMS or email arrived on my mobile number registered with GSTN."*

### 3.2 Root Cause Analysis

Our comprehensive source-code and network tracing identified two distinct contributing factors:

#### Root Cause 1: Sandbox vs. Live GSP Gateway Routing
1. In `apps/gst/services/gst_sandbox_service.py` and `apps/gst/services/sandbox_client.py`, the default integration target is **Sandbox by Quicko** (`https://api.sandbox.co.in`).
2. Sandbox endpoints (`/gst/compliance/tax-payer/otp`) are mock and staging gateways designed for software certification. **Sandbox environments do NOT dispatch real-world SMS or emails to live Indian taxpayers.**
3. Instead, Sandbox by Quicko either:
   - Returns a deterministic simulation response.
   - Dispatches OTPs only to registered developer test credentials or mock test phone numbers.
4. **Live Government GSTN Delivery** requires:
   - An active enterprise GSP production license (e.g. Masters India, Clear, Karza, Cashfree Production).
   - Live production credentials configured in `CompanyGSTConfig` (`is_sandbox = False`).
   - The taxpayer enabling "API Access" on the government portal (`gst.gov.in -> Manage API Access -> Enable API Access -> Set Duration 6 Hours`).

#### Root Cause 2: Hardcoded Frontend UI Defaults
In `frontend/src/app/gst/returns/page.tsx` (lines 80-87), initial state values for the direct upload modal contained placeholder strings:
```typescript
const [taxpayerUsername, setTaxpayerUsername] = useState("srilekh_taxpayer");
const [portalGstin, setPortalGstin] = useState(activeCompany?.gstin || "09CIFPS1329P2ZL");
const [maskedMobile, setMaskedMobile] = useState("******9821");
```
When users clicked the modal, if the active company lacked an explicitly configured GSTIN or taxpayer portal username, the form defaulted to `"srilekh_taxpayer"` and GSTIN `"09CIFPS1329P2ZL"` rather than the user's actual registered credentials. This resulted in gateway rejections or dispatching requests for unowned accounts.

---

## 4. Hardening & Remediations Applied

1. **Elimination of Fake/Dummy Session Fallbacks**:
   - Completely removed all hardcoded OTP fallbacks (e.g. `"575757"`).
   - Removed all mock session tokens (e.g. `"GSTN-SANDBOX-..."`, `"SIMULATED-..."`).
   - `CompanyGSTConfigAPIView.get()` automatically purges any legacy simulated tokens on load.
2. **Correlation ID & Transaction ID Decoupling**:
   - `GSTPortalService.request_portal_otp()` now preserves both the provider's `correlation_id` and SriLekh's internal `txn_id` in the challenge cache.
   - OTP verification accepts challenges matching either identifier, preventing verification drop-outs.
3. **Session Revocation & Disconnect Parity**:
   - `GSTPortalService.disconnect_portal_session()` now cleanly clears tokens from both `GSTRegistration` and `CompanyGSTConfig`, and calls the provider's remote logout endpoint (`/gst/compliance/tax-payer/session/logout`).
4. **User Guidance & Error Normalization**:
   - `apps/gst/services/gst_error_normalizer.py` translates technical gateway responses into clear user actions:
     - `API_ACCESS_DISABLED` -> *"Please enable API access on the GST Portal under Profile -> Manage API Access."*
     - `INVALID_USER_CREDENTIALS` -> *"GST Portal username does not match the registered taxpayer."*
     - `OTP_EXPIRED` -> *"The OTP has expired. Please request a new OTP."*

---

## 5. Audit Conclusion

The OTP generation and authentication subsystem in SriLekh is architecturally sound, cryptographically protected, and hardened against brute-force attacks and token leakage. 

For commercial release with live taxpayer SMS delivery, the deployment environment must configure production GSP credentials (`is_sandbox = False`), and taxpayers must enable API access on `gst.gov.in`.
