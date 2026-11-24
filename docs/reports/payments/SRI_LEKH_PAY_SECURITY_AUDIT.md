# SriLekh Pay — Security & Financial Integrity Audit

## 1. Threat Modeling & Mitigation Analysis

| Threat Vector | Attack Scenario | Mitigation in SriLekh Pay | Verification Status |
|---|---|---|---|
| **Webhook Spoofing** | Attacker posts forged HTTP POST payload to `/api/v1/payments/webhooks/setu/` claiming payment success. | HMAC-SHA256 signature verification over raw request body using tenant or platform webhook secret (`X-Setu-Signature` / `X-Bank-Signature`). | **PASSED & VERIFIED** (`test_webhook_hmac_verification_and_replay_protection`) |
| **Replay Attacks** | Attacker replays genuine webhook notification multiple times to generate multiple vouchers. | Idempotent event deduplication via `PaymentWebhookEvent.objects.create(event_id=...)` with unique index. Duplicate events return cached response and exit without posting. | **PASSED & VERIFIED** |
| **Client-Side State Tampering** | Malicious user modifies client JS or intercepts redirect URL to fake payment success. | Client redirects and client status flags are strictly untrusted. Voucher posting occurs **only** when verified by server-side webhook signature or direct provider status API check (`PaymentVerifyStatusAPIView`). | **PASSED & VERIFIED** |
| **Cross-Tenant Information Disclosure** | Tenant A attempts to read or initiate payments for Tenant B (`IDOR`). | Strict company scoping via `get_authorized_company(request)`. All queries enforce `company_id` filter. Cross-tenant access attempts raise `PermissionDenied (403)`. | **PASSED & VERIFIED** (`test_beneficiary_crud_and_tenant_isolation`) |
| **CRLF Injection via QR** | Malicious actor generates QR code embedding newline characters to manipulate HTTP response headers or logs. | Strict sanitization in `BeneficiaryResolutionService.parse_upi_qr` rejecting any string containing `\r` or `\n`. | **PASSED & VERIFIED** |
| **Double Spend & Race Conditions** | Concurrent requests attempt to confirm or allocate the same payment simultaneously. | Database row-level locks (`select_for_update`) wrapped inside `@transaction.atomic` blocks in `PaymentOrchestrator` and `PaymentAllocationService`. | **PASSED & VERIFIED** |
| **Unlinked / Orphaned Accounting Entries** | System crash during voucher creation leaves one ledger entry posted and the other missing. | Atomic transaction rollback (`transaction.atomic`). Outbox events and notifications are isolated in nested savepoints to guarantee financial atomicity. | **PASSED & VERIFIED** |
| **Bank Account Data Exposure** | Plaintext bank account numbers visible across UI or logged in plaintext. | Account numbers and mobile numbers are stored protected and exposed via computed properties `masked_account_number` (`••••••••1234`) and `masked_mobile_number` (`••••••3210`). | **PASSED & VERIFIED** |

---

## 2. Regulatory & Banking Invariants
- **No Holding of Funds**: SriLekh does not escrow, pool, or hold merchant funds.
- **No Storing of Sensitive Auth Data**: SriLekh Pay **never** requests, transmits, or stores UPI PINs, net banking passwords, or card CVVs. All user authorization occurs strictly within the user's authentic banking or UPI application.
