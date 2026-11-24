# SriLekh Pay — Architecture Specification

## 1. Architectural Overview & Design Philosophy

**SriLekh Pay** is a native, provider-independent payment infrastructure module built inside the SriLekh ERP platform. Its primary mission is to connect payment execution, instant notification, and double-entry accounting reconciliation into one seamless, atomic, and auditable transaction cycle.

Rather than treating payments as disconnected external bank/gateway transactions, SriLekh Pay treats every payment event as a first-class business event that directly drives financial ledger updates, FIFO invoice clearing, and multi-tenant ledger synchronization.

```
+---------------------------------------------------------------------------------------+
|                                SriLekh Frontend / PWA / Android                       |
|  [Overview] [Send Money] [Collect Money] [Beneficiaries] [Requests] [Transactions]... |
+---------------------------------------------------------------------------------------+
                                            |  HTTPS REST / JWT
                                            v
+---------------------------------------------------------------------------------------+
|                                  Django Backend API                                   |
|                             (apps.payments.views)                                     |
+---------------------------------------------------------------------------------------+
          |                                  |                               |
          v                                  v                               v
+-----------------------+        +-----------------------+       +----------------------+
|  Beneficiary Service  |        |  PaymentOrchestrator  |       | PaymentWebhookService|
|  - Resolution (Phone/ |        |  - Idempotency        |       | - Signature Verify   |
|    VPA/QR/IFSC)       |        |  - State Lifecycle    |       | - Replay Protection  |
|  - Verification       |        |  - Provider Dispatch  |       | - Payload Dispatch   |
+-----------------------+        +-----------------------+       +----------------------+
                                             |                               |
                                             v                               v
                       +-------------------------------------------------------------+
                       |              AccountingPostingService (Atomic DB)           |
                       |  - Payer PAYMENT Voucher (Dr Vendor / Cr Bank)              |
                       |  - Recipient RECEIPT Voucher (Dr Bank / Cr Customer)        |
                       |  - PaymentAllocationService (FIFO Invoice Clearing)         |
                       |  - Suspense Handler (UnmatchedPaymentRecord)                |
                       +-------------------------------------------------------------+
                                     |                               |
                                     v                               v
                       +---------------------------+   +---------------------------+
                       | PaymentNotificationService|   | SettlementReconService    |
                       | - In-App Notification     |   | - Fee Journal Posting     |
                       | - Outbox Events           |   | - Bank Feed Match         |
                       +---------------------------+   +---------------------------+
                                     |
                                     v
                       +---------------------------+
                       | PaymentProviderInterface  |
                       | + SetuPaymentProvider     |
                       | + BankTransferProvider    |
                       +---------------------------+
```

---

## 2. Core Components

### 2.1 Provider Abstraction Layer (`apps/payments/interfaces/` & `providers/`)
- **`PaymentProviderInterface`**: Abstract Base Class enforcing methods:
  - `create_payment_request(payment_request) -> dict`
  - `verify_payment(payment_request) -> dict`
  - `verify_webhook_signature(raw_payload, headers, secret) -> bool`
  - `process_webhook_payload(payload) -> dict`
  - `initiate_refund(payment_request, amount, reason) -> dict`
- **`SetuPaymentProvider`**:
  - Implements UPI DeepLinks (`/api/v2/links`), Dynamic QR (`/api/v1/merchants/dqr`).
  - Implements HMAC-SHA256 signature verification over raw request body.
- **`BankTransferProvider`**:
  - Generates dedicated Virtual Account Numbers (VAN) with merchant-configured prefix (`APEX...`) and bank IFSC (`ICIC0000011`).
  - Processes NEFT / RTGS / IMPS inbound credit webhooks.

### 2.2 Beneficiary Management Layer (`apps/payments/services/`)
- **`BeneficiaryResolutionService`**:
  - Validates and parses 10-digit mobile numbers into UPI Numbers.
  - Validates UPI VPA syntax (`username@bank`).
  - Parses and sanitizes standard NPCI UPI QR code payloads (`upi://pay?pa=...&pn=...&am=...`), with strict protection against CRLF injection and malicious script vectors.
  - Validates 11-digit IFSC codes and maps bank prefixes to institution names.
- **`BeneficiaryVerificationService`**:
  - Verifies legal account/VPA registration before initiating high-value transfers.
  - Records verification timestamp, verified legal name, and verification source.

### 2.3 Orchestration & Accounting Engine
- **`PaymentOrchestrator`**: Central state machine managing payment lifecycle (`INITIATED` -> `PENDING` -> `SUCCESS` / `FAILED`). Enforces unique `srilekh_pay_id` (`SLP-YYYYMM-XXXXXX`) and client idempotency keys.
- **`AccountingPostingService`**: Executes double-entry voucher creation inside database transactions (`@transaction.atomic`). Reuses `VoucherService` and `InvoiceSequenceService`.
- **`PaymentMatchingService`**: Resolves counterparty tenants when both buyer and seller use SriLekh. If an incoming payment cannot be unambiguously linked, it is safely quarantined in `UnmatchedPaymentRecord` suspense.
- **`PaymentAllocationService`**: Automatically calls `auto_allocate_voucher` to clear invoices using FIFO principle with row-level locks.
- **`SettlementReconciliationService`**: Splits settlements into gross amount, gateway service charges, and net bank deposits.
- **`PaymentNotificationService`**: Emits In-App notifications and transactional outbox events for web push and background mail workers.
