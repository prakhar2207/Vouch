# SriLekh — System Architecture & Dependency Map
**Document Reference:** `docs/full-platform-audit/ARCHITECTURE_AND_DEPENDENCIES.md`  
**Execution Timestamp:** 2026-11-02 16:30:00 IST  
**Audit Lead:** Antigravity Principal Systems Architect & Fintech Reliability Auditor  

---

## 1. Architectural Philosophy & Product Invariants

SriLekh is engineered around a core tenet:
> **Tally-like accounting flexibility with modern SaaS simplicity for non-accountants.**

### 1.1 Invariant Rules

1. **Mandatory Sandbox Test Isolation (`GEMINI.md`)**:
   - Under NO circumstances may any test, benchmark, automated script, or verification job mutate, create, or delete records in real user accounts (`Maa Annapurna Belting Store` `5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`).
   - ALL automated tests strictly execute against the dedicated sandbox:
     - **Name:** `Apex Belting & Industrial Store (Demo)`
     - **Company ID:** `4e62863a-08f9-4e99-b0bd-64873acfdd33`
2. **Mathematical Equilibrium of Double-Entry**:
   - Every posted voucher MUST satisfy $\sum \text{Debits} \equiv \sum \text{Credits}$.
   - Unbalanced vouchers cannot be committed to the database.
3. **Natural Group Directions**:
   - Asset / Expense = Natural Debit.
   - Liability / Equity / Income = Natural Credit.
4. **Original Source Evidence Immutability**:
   - Imported bank statements, OCR scans, and external source documents cannot be mutated in-place by accounting interpretations. Evidence and interpretation are strictly decoupled.
5. **Tamper-Evident Audit Chains**:
   - Audit logs are chained via cryptographic SHA-256 hashes ($H_n = \text{SHA-256}(v2 \parallel H_{n-1} \parallel \text{Metadata})$). Any alteration of past rows invalidates all subsequent hashes.

---

## 2. Layered Architecture

```
+-------------------------------------------------------------------------------+
|                             CLIENT TIER (BROWSER & PWA)                       |
|  - Next.js 16.3.8 App Router (SSR + Client Components)                        |
|  - Dexie.js 4.0 (IndexedDB Mirror: Vouchers, Ledgers, Outbox, OCR Cache)     |
|  - Service Worker (Public Cache, Asset Caching, Offline Recovery Boundary)    |
|  - Client-Side 2D Spatial PDF Tokenizer & Statement Parser                    |
+-------------------------------------------------------------------------------+
                                      | (HTTPS / REST API / JWT)
                                      v
+-------------------------------------------------------------------------------+
|                            API GATEWAY & SECURITY                             |
|  - Django 5.x / Django REST Framework (DRF 3.15)                              |
|  - JWT Authentication (SimpleJWT with Token Blacklisting)                     |
|  - Tenant Context Extraction (Header `X-Company-ID` & Role Authorization)     |
|  - Throttling (Anon 60/min, User 1200/min)                                    |
|  - CORS & Security Headers (Strict Origin Matching, No Wildcards)             |
+-------------------------------------------------------------------------------+
                                      |
         +----------------------------+----------------------------+
         v                                                         v
+----------------------------------+     +----------------------------------+
|      CANONICAL ACCOUNTING        |     |       SUPPORTING ENGINES         |
|  - VoucherService (Lifecycle)    |     |  - BankReconciliationService     |
|  - LedgerEntry Engine            |     |  - BankStatementService (PyMuPDF)|
|  - AllocationService (FIFO/Auto) |     |  - FIFO Inventory Valuation      |
|  - IntegrityEngine               |     |  - GSTCalculator (CGST/SGST/IGST)|
|  - PeriodClosingService          |     |  - ProtocolOperation Emitter     |
+----------------------------------+     +----------------------------------+
         |                                                         |
         +----------------------------+----------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
|                               PERSISTENCE TIER                                |
|  - Primary DB: Neon PostgreSQL 18.6 (Connection Pooling + Direct Session)     |
|  - Row Locking: select_for_update() row-level serializability                |
|  - Test DB: test_neondb (Dedicated PostgreSQL isolation, zero SQLite)         |
|  - Cache & Queues: Redis 7.x / Celery 5.x                                     |
+-------------------------------------------------------------------------------+
```

---

## 3. Future Integration Interfaces & Expansion Surface

Per Project Directives, external payment gateways, live bank aggregation, and live statutory GST portal APIs were **not** built in this phase. However, the architecture exposes clear extension hooks:

### 3.1 Account Aggregator (AA) Interface Specification
- **Future Hook:** `apps/accounting/services/bank_statement_service.py:StatementIngestionInterface`
- **Payload Schema:** Reuses `BankTransactionSchema` (`date`, `description`, `reference`, `debit`, `credit`, `balance`).
- **Integration Boundary:** The AA webhook will directly invoke `BankStatementService.ingest_feed(company, bank_ledger, raw_feed)` without requiring any changes to `BankReconciliationService`.

### 3.2 GST Portal & E-Way / E-Invoice Interface Specification
- **Future Hook:** `apps/gst/services/gst_calculator.py:GSTExportService`
- **Payload Schema:** The internal `GSTR1Summary` and `GSTR3BSummary` models match the statutory JSON schemas specified by the GSTN API.
- **Integration Boundary:** When an authorized API connector (e.g., NIC / ClearTax / GSP) is configured, the export adapter converts internal vouchers into GSTR JSON without modifying core ledgers.

### 3.3 Payment Gateway (PG) Webhook Interface Specification
- **Future Hook:** `apps/accounting/banking_views.py:PaymentWebhookAPIView`
- **Integration Boundary:** Maps incoming webhook transactions (`razorpay_payment_id`, `cashfree_order_id`) into `BankTransaction` with `status='UNRESOLVED'`, utilizing deterministic reference matching against outstanding sales invoices.

---
*Verified against active repository HEAD `b6c020e`.*
