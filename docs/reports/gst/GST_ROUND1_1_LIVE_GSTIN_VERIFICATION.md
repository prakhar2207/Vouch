# SriLekh — GST Round 1.1 Live GSTIN Verification Report

## 1. Executive Summary

This report documents the verification status of the GSTIN lookup and Party Master enrichment workflows in SriLekh.

- **Local Validation & MOD-36 Checksum**: **PASS**
- **Taxpayer Profile Normalization**: **PASS**
- **Non-Intrusive Party Master Enrichment**: **PASS**
- **24-Hour Cache Lifecycle**: **PASS**
- **Live Provider-Backed Verification**: **BLOCKED** pending active staging credentials from the business owner.

---

## 2. Verification Pipeline Stages & Audit Results

### Stage 1: Local Format & Checksum Verification
- **Input**: 15-character GSTIN.
- **Algorithm**: ISO 7064 MOD 37-2 (Luhn MOD-36).
- **Execution**: Sub-millisecond local Python execution.
- **Evidence**:
  - Test GSTIN `07AAAAA0000A1Z4` $\rightarrow$ Valid checksum `'4'`. Result: **PASS**.
  - Test GSTIN `07AAAAA0000A1Z5` $\rightarrow$ Invalid checksum (expected `'4'`, found `'5'`). Result: **PASS (Rejected locally)**.
  - Test GSTIN `27AADCB2230M` $\rightarrow$ Invalid length (12 chars). Result: **PASS (Rejected locally)**.

### Stage 2: Cache Lookup (`GSTTaxpayerCache`)
- **TTL**: Strictly 24 hours (`cache_age < timedelta(hours=24)`).
- **Hit Behavior**: Returns stored taxpayer profile without dispatching external network requests, preserving quota.
- **Miss Behavior**: Dispatches request to Sandbox API if credentials exist.

### Stage 3: Live Provider Gateway Request
- **Endpoint**: `POST https://api.sandbox.co.in/gst/compliance/public/gstin/search`
- **Current Status**: **BLOCKED** — Staging API key is not yet configured in Render environment variables.
- **Safety**: Unconfigured gateway gracefully falls back to local validation with an explicit warning, without blocking manual party creation.

### Stage 4: Non-Intrusive Party Master Enrichment
- **Workflow**:
  1. User enters GSTIN in Customer/Supplier modal and clicks "Verify with GST".
  2. Dialog presents side-by-side comparison:
     - Legal Name: Local Books vs. GST Portal
     - Trade Name: Local Books vs. GST Portal
     - Address & PIN: Local Books vs. GST Portal
     - Status: ACTIVE / SUSPENDED / CANCELLED
  3. User selectively checks which fields to adopt.
  4. Only selected fields are updated on the `Party` record.
  5. Zero modifications are made to vouchers or accounting ledgers.

---

## 3. Live Provider Execution Protocol (Upon Credential Provisioning)

Once the owner configures `SANDBOX_API_KEY` and `SANDBOX_API_SECRET` on Render:
1. Log in to `https://vouch-pi-one.vercel.app` (Staging UI) or execute API test:
   ```bash
   curl -X POST https://vouch-u3u7.onrender.com/api/v1/gst/verify-gstin/ \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <TOKEN>" \
     -d '{"gstin": "27AADCB2230M1ZT"}'
   ```
2. Verify response contains:
   ```json
   {
     "success": true,
     "gstin": "27AADCB2230M1ZT",
     "legal_name": "...",
     "status": "Active",
     "source": "sandbox_api"
   }
   ```
3. Audit log will record `action: 'GSTIN_VERIFY'` with correlation ID.

---

## 4. Verification Verdict

**VERDICT: PASS (MOCKED) / BLOCKED (LIVE)** — Architecture is complete and validated in staging; live execution awaits owner credentials.
