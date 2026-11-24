# SriLekh Pay — Database Schema Documentation

## Database Engine
- Engine: PostgreSQL (Neon Cloud)
- Migrations Applied:
  - `apps/payments/migrations/0001_initial.py`
  - `apps/payments/migrations/0002_alter_paymentrefund_status_and_more.py`

---

## 1. Entity-Relationship Diagram (ERD)

```mermaid
erDiagram
    Company ||--o| MerchantPaymentAccount : "has merchant config"
    Company ||--o{ Beneficiary : "owns"
    Company ||--o{ PaymentRequest : "initiates (payer)"
    Company ||--o{ PaymentRequest : "receives (recipient)"
    Company ||--o{ UnmatchedPaymentRecord : "suspense ledger"
    
    Beneficiary ||--o{ PaymentRequest : "targeted by"
    Ledger ||--o{ Beneficiary : "linked party"
    
    PaymentRequest ||--o| Voucher : "payer_voucher"
    PaymentRequest ||--o| Voucher : "recipient_voucher"
    PaymentRequest ||--o{ PaymentWebhookEvent : "receives events"
    PaymentRequest ||--o{ PaymentRefund : "refunded by"
    
    MerchantPaymentAccount {
        uuid id PK
        uuid company_id FK
        string merchant_id
        string vpa
        boolean is_onboarded
        string onboarding_status
        uuid default_settlement_ledger_id FK
        uuid payment_clearing_ledger_id FK
        uuid gateway_charges_ledger_id FK
        string virtual_account_prefix
        string virtual_account_ifsc
        string webhook_secret
        boolean auto_post_accounting
        jsonb metadata
        timestamp created_at
        timestamp updated_at
    }

    Beneficiary {
        uuid id PK
        uuid company_id FK
        string beneficiary_type
        string name
        string nickname
        string mobile_number
        string vpa
        string account_number
        string ifsc_code
        string bank_name
        string branch_name
        boolean is_verified
        string verification_status
        string verified_name
        string verification_source
        timestamp verification_timestamp
        boolean is_favorite
        boolean is_active
        uuid linked_party_id FK
        timestamp last_paid_at
        integer total_payments_count
        decimal total_paid_amount
        text notes
        jsonb metadata
        timestamp created_at
        timestamp updated_at
    }

    PaymentRequest {
        uuid id PK
        string srilekh_pay_id UK
        uuid company_id FK
        uuid beneficiary_id FK
        uuid payer_party_id FK
        uuid recipient_company_id FK
        uuid recipient_party_id FK
        string recipient_name
        string recipient_vpa
        string recipient_account_number
        string recipient_ifsc
        uuid invoice_id FK
        decimal amount
        string currency
        string payment_method
        string provider
        string provider_reference
        string utr
        text qr_data
        string payment_url
        string status
        string settlement_status
        string accounting_status
        uuid payer_voucher_id FK
        uuid recipient_voucher_id FK
        string idempotency_key
        text notes
        uuid created_by_id FK
        timestamp confirmed_at
        timestamp settled_at
        jsonb metadata
        timestamp created_at
        timestamp updated_at
    }

    PaymentWebhookEvent {
        uuid id PK
        string provider
        string event_id UK
        string event_type
        string srilekh_pay_id FK
        string signature
        jsonb payload
        jsonb headers
        string processing_status
        text processing_error
        timestamp received_at
        timestamp processed_at
    }

    UnmatchedPaymentRecord {
        uuid id PK
        uuid company_id FK
        uuid payment_request_id FK
        decimal amount
        string utr
        string payer_identifier
        text unmatched_reason
        boolean is_resolved
        uuid resolved_voucher_id FK
        uuid resolved_by_id FK
        timestamp resolved_at
        timestamp created_at
    }
```

---

## 2. Table Specifications & Indexes

### `payments_merchantpaymentaccount`
- `company_id` (Unique ForeignKey to `companies_company`)
- Indexes: `merchant_id`, `created_at`

### `payments_beneficiary`
- Composite Indexes:
  - `[company_id, beneficiary_type, is_active]`
  - `[company_id, mobile_number]`
  - `[company_id, vpa]`
- Foreign Keys:
  - `company_id` -> `companies_company.id` (ON DELETE CASCADE)
  - `linked_party_id` -> `ledgers_ledger.id` (ON DELETE SET NULL)

### `payments_paymentrequest`
- Unique: `srilekh_pay_id`
- Composite / Standard Indexes:
  - `[company_id, status]`
  - `[company_id, idempotency_key]`
  - `provider_reference`
  - `utr`
  - `created_at`
- Foreign Keys:
  - `company_id` -> `companies_company.id`
  - `beneficiary_id` -> `payments_beneficiary.id`
  - `payer_party_id` -> `ledgers_ledger.id`
  - `recipient_company_id` -> `companies_company.id`
  - `invoice_id` -> `accounting_voucher.id`
  - `payer_voucher_id` -> `accounting_voucher.id`
  - `recipient_voucher_id` -> `accounting_voucher.id`

### `payments_paymentwebhookevent`
- Unique: `event_id`
- Indexes: `[provider, event_id]`, `srilekh_pay_id`, `processing_status`, `received_at`

### `payments_unmatchedpaymentrecord`
- Indexes: `[company_id, is_resolved]`, `utr`, `created_at`
- Foreign Keys:
  - `company_id` -> `companies_company.id`
  - `payment_request_id` -> `payments_paymentrequest.id`
  - `resolved_voucher_id` -> `accounting_voucher.id`
