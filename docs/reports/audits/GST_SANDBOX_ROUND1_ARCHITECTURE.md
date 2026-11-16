# SriLekh — GST Sandbox Round 1 Architecture Specification

## 1. Scope & Objective

Round 1 establishes the **production foundation** of the Sandbox by Quicko integration in SriLekh, focusing strictly on:
1. Reusable, robust Provider Client (`SandboxGSTClient`) with secure token caching and auto-refresh.
2. Multi-state / Multi-GSTIN Registration Management for companies (`GSTRegistrationService`).
3. Real-time GSTIN verification using local ISO 7064 MOD 37-2 (Luhn MOD-36) validation and Sandbox Public Search.
4. Non-intrusive Party Master enrichment for customers and suppliers.
5. Strict tenant isolation, cryptographic credential protection, and tamper-evident audit logging.

Features outside Round 1 (GSTR filing, GSTR-2B reconciliation, e-Invoice, and E-Way Bill) are excluded from this stage.

---

## 2. Component Architecture

```
+───────────────────────────────────────────────────────────────────────────+
|                        SRILEKH USER INTERFACE (Next.js)                   |
|   1. Settings → GST Registrations (Add, Verify, Review, Edit, Deactivate)  |
|   2. Customer & Supplier Forms (Verify with GST, Side-by-Side Diff Dialog)|
+───────────────────────────────────────────────────────────────────────────+
                                      │ REST API / JWT
                                      ▼
+───────────────────────────────────────────────────────────────────────────+
|                       SRILEKH BACKEND API (Django REST)                   |
|   apps/gst/                                                               |
|   ├── permissions.py          (HasGSTPermission: Tenant check, RBAC)      |
|   ├── views.py                (Registration & Verification REST Endpoints)|
|   ├── serializers.py          (GSTRegistrationSerializer, Payloads)       |
|   └── services/                                                           |
|       ├── sandbox_client.py   (Quicko /authenticate, /public/gstin/search)|
|       ├── gstin_service.py    (Luhn Checksum, Public Search, 24-hr Cache) |
|       ├── registration_service.py (Multi-GSTIN CRUD, State & Duplicate Chk)|
|       └── audit_service.py    (Tamper-evident log with secret redaction)  |
+───────────────────────────────────────────────────────────────────────────+
                                      │ HTTPS (TLS 1.3)
                                      ▼
+───────────────────────────────────────────────────────────────────────────+
|                       SANDBOX BY QUICKO API GATEWAY                       |
|   Staging: https://test-api.sandbox.co.in                                  |
|   - POST /authenticate                                                    |
|   - POST /gst/compliance/public/gstin/search                              |
+───────────────────────────────────────────────────────────────────────────+
```

---

## 3. Data Model Design for Multi-GSTIN Management

A company operating across Indian states requires distinct GST registrations:
- `GSTRegistration` entity:
  - `id`: UUID primary key.
  - `company`: ForeignKey to `Company` (Tenant).
  - `gstin`: 15-character statutory GSTIN (Indexed).
  - `legal_name`: Legal registered entity name.
  - `trade_name`: Trade / DBA name.
  - `state_code`: 2-digit state code (`01`–`38`, `97`).
  - `state_name`: Full state / UT name.
  - `address`: Principal place of business address.
  - `pincode`: 6-digit postal code.
  - `taxpayer_type`: Regular, Composition, ISD, SEZ Unit/Developer, etc.
  - `status`: Active, Suspended, Cancelled, Inactive.
  - `verification_status`: `NOT_VERIFIED`, `PENDING`, `VERIFIED`, `INVALID`, `INACTIVE`, `FAILED`, `PROVIDER_UNAVAILABLE`, `EXPIRED`.
  - `last_verified_at`: Timestamp of successful verification.
  - `provider_reference_id`: Unique transaction/correlation ID from Sandbox.
  - `is_primary`: Flag marking default registration for invoicing.
  - `created_at` & `updated_at`: Auto-timestamped audit fields.

---

## 4. GSTIN Verification Lifecycle & Flow

```
[User enters GSTIN in Settings or Party Form]
                     │
                     ▼
[1. Local Format Check] ─────────── Failed ───────> [Return Local Validation Error]
- Length == 15 chars
- Valid State Code (01-38)
- Valid PAN format (chars 2:12)
- Luhn MOD-36 Checksum
                     │ Passed
                     ▼
[2. Cache Check (24-hr TTL)] ────── Hit ──────────> [Return Cached Profile]
                     │ Miss / Force
                     ▼
[3. Sandbox /authenticate] ──────── 401/403 ──────> [Raise Auth Exception / Re-auth]
- Exchange x-api-key & x-api-secret for JWT
                     │ Success
                     ▼
[4. POST /public/gstin/search] ──── 404/Error ────> [Return "Not Found on Portal"]
                     │ 200 OK
                     ▼
[5. Ingest to GSTTaxpayerCache]
- Save normalized legal name, trade name, state, address, status
                     │
                     ▼
[6. Side-by-Side Review Dialog]
- User reviews verified profile vs current books
- User confirms which fields to adopt
                     │ Confirmed
                     ▼
[7. Save Registration / Enrich Party]
- Updates GSTRegistration or Ledger fields with audit trail
```

---

## 5. Security & Isolation Guarantees

1. **Tenant Isolation**: Every database read and write filters by `company=request.company`. Supplying an external company ID is rejected with HTTP 403.
2. **Credential Protection**: Sandbox API secret and access tokens are encrypted using symmetric Fernet (AES-128 in CBC mode + HMAC-SHA256 authenticated encryption).
3. **Log Redaction**: All request/response payloads logged in `GSTAuditLog` or server logs pass through `GSTAuditService.redact_sensitive_payload()`, masking passwords, API keys, tokens, and secrets.
4. **Accounting Non-Interference**: Round 1 performs zero writes to `accounting_voucher`, `accounting_voucheritem`, `accounting_ledgerentry`, or `inventory_stockitem`. Double-entry books remain untouched.
