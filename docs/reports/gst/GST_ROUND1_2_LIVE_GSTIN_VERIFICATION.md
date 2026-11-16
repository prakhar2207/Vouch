# SriLekh — GST Round 1.2 Live GSTIN Verification Report

## 1. Executive Summary

This report assesses the live GSTIN verification pipeline against **Sandbox by Quicko** (`https://api.sandbox.co.in/gst/compliance/public/gstin/search`).

- **Local Validation & Sub-Millisecond Checksum**: **PASS** (100% verified).
- **Party Master Selective Enrichment**: **PASS** (100% verified).
- **24-Hour Taxpayer Cache**: **PASS** (100% verified).
- **Live Provider-Backed Search**: **BLOCKED (Awaiting Owner Provisioning)** pending staging credentials from the business owner.

---

## 2. Official Provider Endpoint Specification

### Request Format
- **URL**: `POST https://api.sandbox.co.in/gst/compliance/public/gstin/search`
- **Headers**:
  ```http
  authorization: <ACCESS_TOKEN>
  x-api-key: <SANDBOX_API_KEY>
  x-api-version: 1.0
  x-transaction-id: GST-<CORRELATION_ID>
  Content-Type: application/json
  ```
- **Body**:
  ```json
  {
    "gstin": "27AADCB2230M1ZT"
  }
  ```

### Provider Response Schema & Normalization Mapping
```
Provider Field (Sandbox)       Normalized Field (SriLekh)
────────────────────────       ──────────────────────────
data.gstin                 --> gstin
data.lgnm                  --> legal_name
data.tradeNam              --> trade_name
data.sts                   --> status (Active / Cancelled / Suspended)
data.ctb                   --> taxpayer_type (Regular / Composition)
data.rgdt                  --> registration_date
data.pradr.addr            --> address & pincode
```

---

## 3. Local Invariant Verification Evidence

Executed in `apps.gst.tests_round1_foundation`:

1. **Mathematical Luhn MOD-36 Checksum**:
   - `07AAAAA0000A1Z4`: Valid checksum `'4'`. Result: **PASS**.
   - `07AAAAA0000A1Z5`: Expected `'4'`, received `'5'`. Result: **REJECTED LOCALLY** with 0 API calls.
2. **State Code Validation**:
   - `27` (Maharashtra): Recognized. Result: **PASS**.
   - `99` (Centre Jurisdiction): Recognized. Result: **PASS**.
   - `00` / Invalid numbers: Rejected locally. Result: **PASS**.
3. **Selective Party Master Enrichment**:
   - Users view side-by-side diff preview between local books and verified profile.
   - Users manually check fields to update.
   - Vouchers and accounting ledger balances remain untouched.

---

## 4. Operational Execution Protocol for Live Testing

Once the owner enters `SANDBOX_API_KEY` and `SANDBOX_API_SECRET` in Render Staging:
1. Dispatch verification request:
   ```bash
   curl -X POST https://vouch-u3u7.onrender.com/api/v1/gst/verify-gstin/ \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <STAGING_JWT_TOKEN>" \
     -d '{"gstin": "27AADCB2230M1ZT"}'
   ```
2. Verify that `source` reports `"sandbox_api"` and the taxpayer profile is ingested into `GSTTaxpayerCache`.

---

## 5. Verification Verdict

**VERDICT: BLOCKED (LIVE GATEWAY) / PASS (PIPELINE ARCHITECTURE)** — Live verification is ready to execute immediately upon credential injection.
