# SriLekh — Missing Features, Functional Gaps & Future Roadmap
**Document Reference:** `docs/full-platform-audit/MISSING_FEATURES_AND_GAPS.md`  
**Execution Timestamp:** 2026-11-02 16:30:00 IST  
**Audit Lead:** Antigravity Principal Systems Architect & Fintech Reliability Auditor  

---

## 1. Intentional Exclusions vs Deferred Integrations

Per Master Directives, the following integrations were **explicitly excluded** from the current scope to maintain focus on core financial integrity:

| Integration / Feature | Classification | Rationale | Extension Hook in Codebase |
|---|:---:|---|---|
| **GST Portal / GSTN Direct API** | Out of Scope | Avoid third-party GSP dependency before core ledger stabilization | `apps/gst/services/gst_calculator.py:GSTExportService` |
| **Live Account Aggregator (AA)** | Out of Scope | AA ecosystem requires commercial NBFC-AA licenses | `apps/accounting/services/bank_statement_service.py:ingest_feed` |
| **Payment Gateway Checkout (PG)** | Out of Scope | B2B settlements are primarily NEFT/RTGS/Cheque | `apps/accounting/banking_views.py:PaymentWebhookAPIView` |

---

## 2. Identified Functional Gaps & Non-Blocking Limitations

The following non-blocking functional gaps were identified during the module-by-module audit:

### 2.1 Automated Fixed Asset Depreciation
- **Current Behavior:** Depreciation must be manually posted via standard `JOURNAL` vouchers (Debit Depreciation Expense, Credit Fixed Asset).
- **Impact:** Low for MSMEs; CAs prefer calculating depreciation at year-end per Income Tax Act rules (WDV method).
- **Roadmap:** Schedule automated monthly/yearly depreciation schedules for Phase 2.

### 2.2 Multi-Currency FX Revaluation
- **Current Behavior:** System operates natively in Indian Rupees (INR, ₹). Export invoices with foreign currencies require manual conversion to INR.
- **Impact:** Negligible for domestic Indian wholesalers and retailers; relevant only for export-oriented units.
- **Roadmap:** Introduce multi-currency ledger support and automated FX gain/loss adjustments.

### 2.3 Camera-Based Barcode Scanner
- **Current Behavior:** Barcode lookup in inventory and POS supports physical USB / Bluetooth barcode scanners (which emulate keyboard keystrokes into the SKU field).
- **Impact:** Handheld scanners work out-of-the-box; built-in smartphone camera scanning via WebRTC is not yet enabled.
- **Roadmap:** Integrate `@zxing/library` or HTML5 QR/Barcode scanner into the PWA.

### 2.4 WhatsApp Cloud API Integration
- **Current Behavior:** Invoice sharing and payment reminders trigger the native `https://wa.me/?text=...` URI, opening WhatsApp with pre-filled text.
- **Impact:** Requires user to tap "Send" in WhatsApp; zero cost and zero Meta API approval overhead.
- **Roadmap:** Add automated background WhatsApp Business Cloud API webhook delivery.

---

## 3. Prioritized Post-Launch Roadmap

```
+-----------------------------------------------------------------------------------+
|                           PHASE 2 ROADMAP (POST-LAUNCH)                           |
|                                                                                   |
|  [Sprint 1] WhatsApp Business Cloud API automated PDF invoice delivery            |
|  [Sprint 2] WebRTC mobile camera barcode scanner for inventory stocktaking        |
|  [Sprint 3] NIC E-Way Bill & E-Invoice direct API generation via GSP              |
|  [Sprint 4] Fixed asset register & automated WDV/SLM depreciation engine          |
+-----------------------------------------------------------------------------------+
```

---
*Verified against active repository HEAD `b6c020e`.*
