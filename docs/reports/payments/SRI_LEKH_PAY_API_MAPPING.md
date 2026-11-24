# SriLekh Pay — API Endpoints & Request/Response Specification

## Base URL
- Production: `https://vouch-api-752s.onrender.com/api/v1/payments/`
- Staging: `https://vouch-api-staging.onrender.com/api/v1/payments/`

---

## 1. Merchant Account Configuration
### `GET /api/v1/payments/account/`
- **Auth**: Bearer JWT (`IsAuthenticated`)
- **Headers**: `X-Company-ID: <UUID>`
- **Response `200 OK`**:
```json
{
  "id": "c1f76f7b-...",
  "company": "4e62863a-08f9-4e99-b0bd-64873acfdd33",
  "company_name": "Apex Belting & Industrial Store (Demo)",
  "vpa": "apexbelts@icici",
  "is_onboarded": true,
  "onboarding_status": "ACTIVE",
  "default_settlement_ledger": "bb752f89-...",
  "settlement_ledger_name": "Apex Current Account",
  "payment_clearing_ledger": "a823901b-...",
  "clearing_ledger_name": "SriLekh Payment Clearing",
  "gateway_charges_ledger": "e1209bc4-...",
  "gateway_charges_ledger_name": "Payment Gateway Charges",
  "virtual_account_prefix": "APEX",
  "virtual_account_ifsc": "ICIC0000011",
  "auto_post_accounting": true
}
```

### `POST /api/v1/payments/account/`
- **Auth**: Bearer JWT (`IsAuthenticated`)
- **Headers**: `X-Company-ID: <UUID>`
- **Request Body**:
```json
{
  "vpa": "merchant@icici",
  "virtual_account_prefix": "MCH",
  "default_settlement_ledger": "bb752f89-...",
  "payment_clearing_ledger": "a823901b-...",
  "gateway_charges_ledger": "e1209bc4-...",
  "auto_post_accounting": true
}
```

---

## 2. Beneficiary Discovery & Directory
### `POST /api/v1/payments/beneficiaries/discover/`
- **Auth**: Bearer JWT (`IsAuthenticated`)
- **Headers**: `X-Company-ID: <UUID>`
- **Request Body**:
```json
{
  "discovery_mode": "MOBILE",
  "query": "9876543210"
}
```
*(Modes supported: `MOBILE`, `VPA`, `QR`, `IFSC`)*
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "mobile_number": "9876543210",
    "name": "Saksham Industrial Belts",
    "vpa": "saksham@icici",
    "is_srilekh_merchant": true,
    "is_verified": true,
    "source": "SRILEKH_NETWORK",
    "masked_identifier": "••••••3210"
  }
}
```

### `GET /api/v1/payments/beneficiaries/`
- **Auth**: Bearer JWT (`IsAuthenticated`)
- **Headers**: `X-Company-ID: <UUID>`
- **Query Params**: `?search=...&type=...&favorite=true`
- **Response `200 OK`**: List of `Beneficiary` records.

### `POST /api/v1/payments/beneficiaries/`
- **Auth**: Bearer JWT (`IsAuthenticated`)
- **Headers**: `X-Company-ID: <UUID>`
- **Request Body**:
```json
{
  "name": "Saksham Industrial Belts",
  "nickname": "Saksham Belts",
  "beneficiary_type": "VPA",
  "vpa": "saksham@icici",
  "linked_party": "109f6aa9-...",
  "auto_verify": true
}
```

### `POST /api/v1/payments/beneficiaries/<uuid:pk>/favorite/`
- **Auth**: Bearer JWT (`IsAuthenticated`)
- **Headers**: `X-Company-ID: <UUID>`
- **Response `200 OK`**: `{"success": true, "is_favorite": true}`

### `POST /api/v1/payments/beneficiaries/<uuid:pk>/verify/`
- **Auth**: Bearer JWT (`IsAuthenticated`)
- **Headers**: `X-Company-ID: <UUID>`
- **Response `200 OK`**: `{"success": true, "data": {...}, "message": "Beneficiary verified."}`

---

## 3. Payment Request & Execution
### `POST /api/v1/payments/requests/`
- **Auth**: Bearer JWT (`IsAuthenticated`)
- **Headers**: `X-Company-ID: <UUID>`
- **Request Body**:
```json
{
  "amount": 1850.00,
  "payment_method": "UPI",
  "beneficiary_id": "86e4152c-...",
  "payer_party_id": "109f6aa9-...",
  "invoice_id": "6032d847-...",
  "notes": "Invoice #PUR/26-27/004 payment",
  "idempotency_key": "pay_apex_1732431200000"
}
```
- **Response `201 Created`**:
```json
{
  "id": "276c1234-...",
  "srilekh_pay_id": "SLP-202611-7325B5",
  "amount": "1850.00",
  "currency": "INR",
  "payment_method": "UPI",
  "provider": "SETU",
  "provider_reference": "SETU_SLP-202611-7325B5_B577710F",
  "qr_data": "upi://pay?pa=saksham@icici&pn=Saksham%20Industrial%20Belts&am=1850.00&tr=SETU_SLP-202611-7325B5_B577710F",
  "payment_url": "https://setu.co/pay/SLP-202611-7325B5",
  "status": "INITIATED",
  "accounting_status": "PENDING"
}
```

### `GET /api/v1/payments/requests/<uuid:pk>/`
- **Auth**: Bearer JWT (`IsAuthenticated`)
- **Headers**: `X-Company-ID: <UUID>`
- Returns complete payment audit details, linked vouchers, and timeline.

### `POST /api/v1/payments/requests/<uuid:pk>/confirm/`
- **Auth**: Bearer JWT (`IsAuthenticated`)
- **Headers**: `X-Company-ID: <UUID>`
- **Request Body**: `{"utr": "411223344556"}`
- Idempotently verifies and transitions payment to `SUCCESS`, automatically posting double-entry vouchers.

---

## 4. Webhooks
### `POST /api/v1/payments/webhooks/setu/`
- **Auth**: Open (`AllowAny`), protected by `X-Setu-Signature` HMAC-SHA256 header.
- **Headers**: `X-Setu-Signature: <hex_hmac_sha256>`
- **Response `200 OK`**: `{"status": "SUCCESS", "message": "Event processed.", "data": {"srilekh_pay_id": "..."}}`

### `POST /api/v1/payments/webhooks/bank/`
- **Auth**: Open (`AllowAny`), protected by `X-Bank-Signature` HMAC-SHA256 header.
- Handles VAN inbound credit notifications.
