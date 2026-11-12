# SRI LEKH — STAGE 4.13 OUTBOX RECOVERY & DELIVERY AUDIT

**Date:** 2026-11-12  
**Database Audited:** `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`, fingerprint `6f4741bdaaf4`)  
**Code Changes:** [apps/notifications/tasks.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/tasks.py), [apps/notifications/outbox_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/outbox_service.py)

---

## 1. Classification of `170` Pre-Remediation `PENDING` Outbox Events

Read-only forensic inspection (`classify_pending_events`) of all **170 / 170** `PENDING` `TransactionalOutboxEvent` rows prior to recovery showed:
- **Tenant:** `Precision Agro Tools Pvt Ltd` (`170 / 170`)
- **Event Type / Aggregate:** `INVOICE_POSTED` / `Voucher` (`170 / 170`)
- **Claim / Retry State:** `retry_count = 0`, `claimed_at = None`, `lease_expires_at = None` (`170 / 170`, created on `2026-11-06`)
- **Referenced Voucher Status:** `POSTED` (`170 / 170`)
- **Resolved Recipient Email:** `None` (`170 / 170` — synthetic pilot invoices without a customer email address; e.g. `bfec05f6-744f-423b-bf7a-17ee461bd09c` -> `INV/26-27/0316`)
- **Operational Root Cause:** Render's `Procfile` runs only `web:` (no `worker:`/`beat:` service executing Celery tasks), and `tasks.py` previously sliced `[:50]` without deterministic `.order_by('created_at', 'id')`.

---

## 2. Inspection of `9` Pre-Existing `DEAD_LETTER` Events

All `9` pre-existing `DEAD_LETTER` events belong to historical pilot tests on `Precision Agro Tools Pvt Ltd` (`2026-11-06`) and were preserved without modification:
- **`2` missing referenced vouchers (`retry_count=0`, `Referenced voucher does not exist`):**
  - `cec825c7-88cb-41d5-b2c9-4ae1b2b4eb9a` (voucher `d8a13d65-801a-420f-a80a-309128983343`)
  - `50cbc8e3-458f-465d-bde4-aa46ee6c7448` (voucher `ae61a7ee-b809-42eb-9509-8f892473117b`)
- **`7` simulated fatal-delivery test artifacts (`retry_count=3`, `Simulated Fatal Delivery Error`):**
  - `af6d4708-a63a-48d8-a031-0036cee35823`, `c94ddcb3-bced-499d-a4cb-4bf7f134d96f`, `b0c873df-1383-4d09-907f-e94efe3662fb`, `cb417888-0975-4461-ba4d-0d26dbbba12e`, `f40c4e00-87bb-4ef6-b73d-6a656cb8195c`, `c176dd0e-6024-47e6-94c9-67b6347c9c32`, `f71c3b6b-13c9-4e9e-8ea7-b39cf36733d1`

---

## 3. Hardening & Safe Idempotent Recovery Results

### Code Improvements Implemented
1. **`apps/notifications/tasks.py`:** Sweeper queries now slice deterministically via `.order_by('created_at', 'id')[:100]`.
2. **`apps/notifications/outbox_service.py`:**
   - Added non-dict payload validation transitioning malformed payloads safely to `DEAD_LETTER` rather than crashing worker ticks.
   - Added read-only `OutboxService.classify_pending_events(...)`.
   - Added bounded idempotent `OutboxService.recover_pending_outbox_events(batch_limit=...)` supporting stale-lease reclamation and duplicate-free state transition via the production `process_event(...)` path.

### Recovery Run Results (`batch_limit=300`)

| Metric | Before Recovery | After Recovery | Delta |
|---|---:|---:|---:|
| Outbox `PENDING` | **170** | **0** | **-170** |
| Outbox `SKIPPED` | 227 | **397** | +170 |
| Outbox `PROCESSED` | 603 | 603 | 0 |
| Outbox `DEAD_LETTER` | 9 | 9 | 0 |
| `EmailDeliveryLog` `SENT` | **621** | **621** | **0 (zero duplicate/spurious emails)** |
| `EmailDeliveryLog` `SKIPPED` | 227 | **397** | +170 |

- **Automated Regression Guard:** `Stage413OutboxAndAgingTests.test_classify_and_recover_pending_outbox_without_duplicate_send` verified passing on PostgreSQL (`test_neondb_staging`).
