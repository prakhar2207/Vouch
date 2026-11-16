# SriLekh — Sandbox by Quicko Round 1 API Documentation

## 1. Provider Overview

- **Provider**: Quicko Infosoft Pvt Ltd (Sandbox by Quicko)
- **Official Documentation**: https://developer.sandbox.co.in
- **GST Product Page**: https://sandbox.co.in/gst
- **API Base URL (Production)**: `https://api.sandbox.co.in`
- **API Base URL (Staging / Test)**: `https://test-api.sandbox.co.in`
- **API Version**: `1.0.0`

---

## 2. Round 1 API Specification Table

| API | Documented Endpoint | HTTP Method | Authentication | Required Headers | Request Parameters / Body | Response Fields | Documented Error Handling | Sandbox Access | Account Permissions |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Authentication** | `/authenticate` | `POST` | API Key & Secret | `x-api-key: <KEY>`<br>`x-api-secret: <SECRET>`<br>`x-api-version: 1.0.0`<br>`Content-Type: application/json` | None (Credentials sent via headers) | `access_token` (JWT string)<br>`expires_in` (seconds, default 86400) | `401 Unauthorized`<br>`403 Forbidden`<br>`429 Rate Limit` | Available on `test-api.sandbox.co.in` | Valid organization account |
| **Public GSTIN Search** | `/gst/compliance/public/gstin/search` | `POST` | Bearer JWT + API Key | `authorization: <JWT_TOKEN>`<br>`x-api-key: <KEY>`<br>`x-api-version: 1.0.0`<br>`Content-Type: application/json` | JSON Body:<br>`{"gstin": "27AADCB2230M1ZT"}` | `data.gstin`<br>`data.lgnm` (Legal Name)<br>`data.tradeNam` (Trade Name)<br>`data.sts` (Status: Active/Cancelled)<br>`data.ctb` (Taxpayer Type: Regular/Composition)<br>`data.rgdt` (Registration Date)<br>`data.pradr.addr` (Address object: bno, st, loc, pncd, stcd) | `400 Bad Request` (Invalid GSTIN)<br>`401 Unauthorized` (Token expired)<br>`404 Not Found` (GSTIN not registered)<br>`429 Rate Limit`<br>`500 Internal Error` | Available on `test-api.sandbox.co.in` | Public compliance product access |

---

## 3. Authentication & Access Token Handling

### Token Exchange Request
```http
POST /authenticate HTTP/1.1
Host: test-api.sandbox.co.in
x-api-key: key_test_xxxxxxxxxxxxxxxxxxxx
x-api-secret: sec_test_yyyyyyyyyyyyyyyyyyyy
x-api-version: 1.0.0
Content-Type: application/json
```

### Successful Response (HTTP 200)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJxdWlja28iLCJzdWIiOiJ1c2VyIiwiZXhwIjoxNzA...",
  "expires_in": 86400,
  "token_type": "Bearer"
}
```

### Token Expiration & Refresh Policy
- The access token is valid for 24 hours (86,400 seconds).
- SriLekh stores the token encrypted at rest in `CompanyGSTConfig.sandbox_access_token`.
- To prevent mid-request token expiration, SriLekh applies a 5-minute safety buffer (`now + timedelta(seconds=expires_in - 300)`).
- If the token expires or returns `401 Unauthorized`, `SandboxGSTClient` automatically triggers re-authentication.

---

## 4. Public GSTIN Search & Taxpayer Retrieval

### Request
```http
POST /gst/compliance/public/gstin/search HTTP/1.1
Host: test-api.sandbox.co.in
authorization: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
x-api-key: key_test_xxxxxxxxxxxxxxxxxxxx
x-api-version: 1.0.0
Content-Type: application/json

{
  "gstin": "27AADCB2230M1ZT"
}
```

### Response Schema (HTTP 200)
```json
{
  "data": {
    "gstin": "27AADCB2230M1ZT",
    "lgnm": "TATA CONSULTANCY SERVICES LIMITED",
    "tradeNam": "TATA CONSULTANCY SERVICES",
    "sts": "Active",
    "ctb": "Regular",
    "rgdt": "01/07/2017",
    "cxdt": null,
    "pradr": {
      "addr": {
        "bno": "TCS House",
        "st": "Raveline Street, Fort",
        "loc": "Mumbai",
        "pncd": "400001",
        "stcd": "27"
      },
      "ntr": "Principal Place of Business"
    },
    "adadr": []
  },
  "status_code": 200,
  "message": "Taxpayer details fetched successfully"
}
```

---

## 5. Error Code Mapping & Handling

| Provider HTTP Code | Provider Message | SriLekh Normalized Exception | User-Facing Action |
| :--- | :--- | :--- | :--- |
| `400` | Invalid GSTIN format / Checksum failed | `GSTINValidationError` | "The entered GSTIN is malformed or has an invalid checksum." |
| `401` | Unauthorized / Expired token | `GSTAuthenticationError` | Client automatically refreshes token; if failure persists: "Sandbox authentication failed." |
| `404` | Taxpayer record not found | `GSTINValidationError` | "This GSTIN was not found on the government GST portal." |
| `429` | Rate limit exceeded | `GSTRateLimitExceededError` | Exponential backoff retry with jitter (up to 3 retries); alert user if capacity exhausted. |
| `500 / 502 / 503` | Government portal or gateway error | `GSTIntegrationError` | "The government GST portal is temporarily unresponsive. Please try again shortly or proceed with manual entry." |
| `504` | Request timed out | `GSTIntegrationError` | "Connection to the GST verification service timed out." |
