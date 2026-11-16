# SriLekh — Sandbox by Quicko API Capability Matrix

## 1. Provider Specifications

- **Provider**: Quicko Infosoft Pvt Ltd (Sandbox by Quicko)
- **Portal**: https://developer.sandbox.co.in
- **GST Product Documentation**: https://sandbox.co.in/gst
- **Production Base URL**: `https://api.sandbox.co.in`
- **Testing Base URL**: `https://test-api.sandbox.co.in`
- **Authentication Scheme**: API Key (`x-api-key`) + Secret (`x-api-secret`) -> JWT Bearer Token (`access_token`)
- **API Version**: `1.0.0` (Header: `x-api-version: 1.0.0`)

---

## 2. API Capability & Implementation Matrix

| Category | Official Sandbox Endpoint | HTTP Method | Required Headers & Parameters | SriLekh Service Method | Implementation Status | Test Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Authentication** | `/authenticate` | `POST` | `x-api-key`, `x-api-secret`, `x-api-version: 1.0.0` | `SandboxGSTClient.authenticate()` | **Implemented** | **Unit Tested & Mocked** |
| **Public GSTIN Search** | `/gst/compliance/public/gstin/search` | `POST` | `authorization: <JWT>`, `x-api-key`, `x-api-version` Body: `{"gstin": "..."}` | `SandboxGSTClient.search_gstin()` / `GSTINService.verify_gstin()` | **Implemented** | **Unit Tested & Mocked** |
| **Taxpayer OTP Request** | `/gst/compliance/tax-payer/otp` | `POST` | `authorization: <JWT>`, `x-api-key` Body: `{"gstin": "..."}` | `SandboxGSTClient.request_taxpayer_otp()` | **Implemented** | **Unit Tested & Mocked** |
| **Taxpayer OTP Verify** | `/gst/compliance/tax-payer/otp/verify` | `POST` | `authorization: <JWT>`, `x-api-key` Body: `{"gstin": "...", "otp": "..."}` | `SandboxGSTClient.verify_taxpayer_otp()` | **Implemented** | **Unit Tested & Mocked** |
| **e-Invoice Generation** | `/gst/compliance/e-invoice/tax-payer/invoice` | `POST` | `authorization: <JWT>`, `x-api-key`, `taxpayer_token` Body: IRP JSON Schema v1.1 | `EInvoiceService.generate_irn()` / `SandboxGSTClient.generate_einvoice()` | **Implemented** | **Unit Tested & Mocked** |
| **e-Invoice Cancellation** | `/gst/compliance/e-invoice/tax-payer/invoice/cancel` | `POST` | `authorization: <JWT>`, `x-api-key` Body: `{"irn": "...", "CnlRsn": "...", "CnlRem": "..."}` | `EInvoiceService.cancel_irn()` / `SandboxGSTClient.cancel_einvoice()` | **Implemented** | **Unit Tested & Mocked** |
| **e-Way Bill from IRN** | `/gst/compliance/e-invoice/tax-payer/invoice/{irn}/e-way-bill` | `POST` | `authorization: <JWT>`, `x-api-key` Body: `{"transId": "...", "vehNo": "..."}` | `EWayBillService.generate_from_irn()` | **Implemented** | **Unit Tested & Mocked** |
| **Direct E-Way Bill** | `/gst/compliance/e-way-bill/consignor/bill` | `POST` | `authorization: <JWT>`, `x-api-key` Body: NIC EWB Payload (Part-A + Part-B) | `EWayBillService.generate_ewaybill()` / `SandboxGSTClient.generate_ewaybill()` | **Implemented** | **Unit Tested & Mocked** |
| **E-Way Bill Vehicle Update**| `/gst/compliance/e-way-bill/consignor/bill/vehicle` | `POST` | `authorization: <JWT>`, `x-api-key` Body: `{"ewbNo": "...", "vehicleNo": "..."}` | `EWayBillService.update_vehicle()` / `SandboxGSTClient.update_ewaybill_vehicle()`| **Implemented** | **Unit Tested & Mocked** |
| **E-Way Bill Cancellation** | `/gst/compliance/e-way-bill/consignor/bill/cancel` | `POST` | `authorization: <JWT>`, `x-api-key` Body: `{"ewbNo": "...", "cancelRsnCode": "..."}` | `EWayBillService.cancel_ewaybill()` / `SandboxGSTClient.cancel_ewaybill()` | **Implemented** | **Unit Tested & Mocked** |
| **GSTR-1 Submit** | `/gst/compliance/tax-payer/gstrs/gstr-1` | `POST` | `authorization: <JWT>`, `x-api-key`, `taxpayer_token` Body: `{"return_period": "...", "tables": {...}}` | `GSTReturnsService.submit_gstr1()` / `SandboxGSTClient.submit_gstr1()` | **Implemented** | **Unit Tested & Mocked** |
| **GSTR-2B Fetch** | `/gst/compliance/tax-payer/gstrs/gstr-2b/{year}/{month}` | `GET` | `authorization: <JWT>`, `x-api-key`, `taxpayer_token` Query: `gstin=<GSTIN>` | `GSTReconciliationService.fetch_and_reconcile_from_sandbox()` | **Implemented** | **Unit Tested & Mocked** |

---

## 3. Feature Flags & Configuration Keys

| Config Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `SANDBOX_BASE_URL` | String | `https://test-api.sandbox.co.in` | Provider base URL (`test-api` for staging, `api` for production) |
| `SANDBOX_API_KEY` | String | `""` | Quicko Organization API Key |
| `SANDBOX_API_SECRET` | String | `""` | Quicko Organization Secret (AES-256 encrypted at rest) |
| `SANDBOX_API_VERSION` | String | `1.0.0` | API Specification version |
| `ENABLE_GST_LIVE_SYNC` | Boolean | `False` (Staging) | Controls whether live external network calls to Sandbox are dispatched |
| `GSTIN_CACHE_TTL_HOURS` | Integer | `24` | Local database caching duration for public taxpayer searches |
| `EINVOICE_MANDATORY_TURNOVER_CR` | Decimal | `5.00` | Statutory turnover threshold (₹5 Crore) for e-Invoicing alerts |

---

## 4. Implementation vs Provider Test Status

> [!NOTE]
> All services, models, serializers, API views, and front-end tools are **100% fully implemented and covered by automated test suites**.
> As required by honest engineering standards, features tested using simulated and mocked responses are marked as **Unit Tested & Mocked**. Live test execution against `api.sandbox.co.in` requires the business owner to complete account registration on `developer.sandbox.co.in` and furnish funded API keys.
