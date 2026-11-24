# SriLekh Pay — Provider Capability & Commercial Matrix

## 1. Setu Product Capability Matrix

The following matrix documents Setu product capabilities verified against Setu official technical documentation and production API specifications (`https://docs.setu.co/`).

| Feature | Setu Support | Specific Product / API | Commercial / Onboarding Requirement | Architecture Handling in SriLekh Pay |
|---|---|---|---|---|
| **UPI Dynamic QR** | **Supported** | UPI Setu (DQR API v1) | Merchant Onboarding, VPA mapping, Webhook URL | Handled via `SetuPaymentProvider.create_payment_request` (`/api/v1/merchants/dqr`) |
| **UPI DeepLinks (Intent)** | **Supported** | UPI DeepLinks (v2 Links API) | Merchant Category Code (MCC), PAN, GSTIN | Handled via `SetuPaymentProvider` (`/api/v2/links`), returns `upi://` URI |
| **VPA Verification** | **Supported** | Setu Verify (VPA Check) | API Key, Org ID | Handled via `BeneficiaryVerificationService.verify_vpa` |
| **UPI Number Lookup** | **Supported** | Setu UPI Number API | NPCI Agreement / Bank sponsorship | Handled via `BeneficiaryResolutionService.resolve_mobile_number` |
| **Payment Status Query** | **Supported** | GET `/api/v2/links/{platform_bill_id}` | Bearer Token / Org ID | Handled via `PaymentOrchestrator.verify_status` |
| **Webhook Delivery** | **Supported** | Webhooks v2 | Webhook secret configured on Bridge | Handled via `SetuWebhookAPIView` with HMAC-SHA256 signature verification |
| **Refunds** | **Supported** | POST `/api/v2/links/{id}/refund` | Available account balance, KYC | Handled via `SetuPaymentProvider.initiate_refund` |
| **Settlement Reports** | **Supported** | Daily Settlement Files & Webhooks | Bank Partner Settlement Agreement | Handled via `SettlementReconciliationService.record_settlement` |
| **Virtual Accounts (NEFT/RTGS/IMPS)** | **Supported (via Setu Co-Lending / BBPS / Bank Partner)** | Virtual Accounts API | Bank Partnership (ICICI / Axis / Yes Bank) | Handled via `BankTransferProvider` with customized VANs |
| **Commercial Merchant Payouts** | **Separate Product (Setu Payouts)** | Setu Payouts API | Escrow/Nodal Account or RBI Aggregator License | Abstracted via `PaymentProviderInterface.initiate_transfer` |

---

## 2. Multi-Tenant SaaS & Merchant Onboarding Model

1. **Technology Partner Model vs Escrow Pooling**:
   - SriLekh operates as a **Technology Service Provider (TSP)**.
   - SriLekh does **NOT** pool or hold funds in a proprietary account. Customer funds flow directly from payer to recipient bank account or designated virtual account.
2. **Merchant Onboarding (`MerchantPaymentAccount`)**:
   - Each tenant company completes independent digital merchant registration.
   - Merchant credentials (Merchant ID, VPA, Webhook Secret) are stored in `MerchantPaymentAccount` isolated per company.
3. **Regulatory Compliance**:
   - In accordance with RBI Guidelines on Payment Aggregators and Payment Gateways (DPSS.CO.PD.No.1810/02.14.008/2019-20), SriLekh acts strictly as a technology interface and does not intermediate settlements.
