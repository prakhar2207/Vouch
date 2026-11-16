# SriLekh — GST Round 1.1 Provider Connectivity Report

## 1. Executive Summary

This report assesses provider connectivity between SriLekh and **Sandbox by Quicko** (`https://sandbox.co.in` / `https://api.sandbox.co.in`).

- **Client Implementation Status**: **PASS** — Fully architected, unit-tested, and deployed.
- **Live Provider Gateway Connectivity**: **BLOCKED (Awaiting Owner Provisioning)** — Live calls are gated on the owner provisioning API credentials on `developer.sandbox.co.in` and adding them to the Render Staging environment.

---

## 2. API Gateway & Endpoints Specification

| Action | HTTP Method | Official Sandbox Endpoint | Request Headers | Request Body |
| :--- | :--- | :--- | :--- | :--- |
| **Token Authentication** | `POST` | `/authenticate` | `x-api-key`<br>`x-api-secret`<br>`x-api-version: 1.0` | None / `{}` |
| **Public GSTIN Search** | `POST` | `/gst/compliance/public/gstin/search` | `authorization: <JWT>`<br>`x-api-key`<br>`x-api-version: 1.0` | `{"gstin": "27AADCB2230M1ZT"}` |

### Client Execution Flow (`SandboxGSTClient`)
1. Resolves `SANDBOX_API_KEY`, `SANDBOX_API_SECRET`, and `SANDBOX_BASE_URL`.
2. Inspects cached JWT token in `CompanyGSTConfig`.
3. If token is absent or within 5 minutes of expiry, executes `POST /authenticate`.
4. Caches valid token for 23 hours.
5. Injects token into `authorization` header with unique `x-transaction-id` for correlation.
6. Dispatches request to Sandbox endpoint with 12s timeout and automatic retry on transient 5xx errors.

---

## 3. Credential Availability Status

Environment inspection of Render Staging and local workspace:

| Credential Variable | Status | Required Action |
| :--- | :---: | :--- |
| `SANDBOX_API_KEY` | `NOT_SET` | Owner must obtain from `developer.sandbox.co.in` |
| `SANDBOX_API_SECRET` | `NOT_SET` | Owner must obtain from `developer.sandbox.co.in` |
| `SANDBOX_BASE_URL` | `DEFAULT` | Set to `https://api.sandbox.co.in` |
| `GST_ENCRYPTION_KEY` | `NOT_SET` | Owner must set base64 32-byte Fernet key |

---

## 4. Failure Handling & Mock Verification

The client error-handling pipeline was tested against simulated gateway conditions in `apps/gst/tests_round1_foundation.py`:

- **Missing Credentials**: Raises `GSTConfigurationMissingError` cleanly; frontend displays "Provider not configured" without crashing.
- **HTTP 401 / 403**: Raises `GSTAuthenticationError`; forces token invalidation and logs redacted alert.
- **HTTP 429 Rate Limit**: Raises `GSTRateLimitExceededError`; triggers exponential backoff.
- **HTTP 500 / 502 / 503 / 504**: Retries up to 3 times before raising `ProviderUnavailableError`.
- **Zero Accounting Mutations**: No error condition causes uncommitted transactions or corrupts ledger states.

---

## 5. Connectivity Verdict

- **Code & Architecture**: **PASS**
- **Live Provider Verification**: **BLOCKED** pending owner credential entry in Render.
