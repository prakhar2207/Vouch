# SRI LEKH — STAGE 4.15 PRECISION AGRO INVENTORY INTEGRITY REPORT

**Environment:** `neondb_staging` (`Precision Agro Tools Pvt Ltd`, UUID `c2771ca4-31bd-47d2-b98c-c1be119f40a1`) & PostgreSQL `test_neondb_staging`  
**Commit SHA:** `c15a64fb` (`fix/stage4-12-day6-remediation`)  
**Database Fingerprint:** `6f4741bdaaf4` (`is_isolated=True`, `Maa Annapurna Belting Store` absent)  
**Execution Timestamp:** `2026-11-12 14:12–14:28 IST`

---

## Executive Finding: **EXPLAINED — SYNTHETIC STRESS-TEST OVERSELLING UNDER DEFAULT `allow_negative_stock=True` (ZERO ACCOUNTING OR LEDGER BUG FOUND)**

Forensic inspection of every SKU, `InventoryEntry`, and `VoucherItem` in `Precision Agro Tools Pvt Ltd` confirmed **`0` orphan `InventoryEntry` rows**, **`0` duplicate stock deductions**, **`0` voucher-quantity mismatches**, and **`0` prior stock rebuild mutations**. No blind stock adjustment was performed on `Precision Agro`.

---

## 1. SKU-by-SKU Forensic Inventory Breakdown (`Precision Agro Tools Pvt Ltd`)

Raw cost valuation across all 7 SKUs sums to exactly **`-Rs 207,216.82`**, while Balance Sheet inventory valuation (`stock_quantity > 0` clamping negative short-sale quantities in `FinancialStatementsService.get_inventory_valuation()` and `ProductCategoryListView`) reports **`Rs 158,235.00`**:

| SKU | Product Name | Costing | Purchase Price (Rs) | Initial Un-entered Open Qty | Inward (`IN`) | Outward (`OUT`) | Closing `stock_quantity` | Raw Value (`qty * price`, Rs) |BS Clamped Value (Rs) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| *(blank)* | `Exempt Agri Belting` | AVG_COST | 300.00 | 0.00 | 0.00 | `4.00` (4 SALES) | **`-4.00`** | **-1,200.00** | 0.00 |
| `SKU-8483-18` | `High Precision Drive Belt` | AVG_COST | 502.43 | 150.00 | `18.00` (`10` PUR, `8` CN) | `642.00` (`640` SALES, `2` DN) | **`-474.00`** | **-238,151.82** | 0.00 |
| `SKU-MSME-PLT-01-8432` | `Hardened Cultivator Shovel` | AVG_COST | 650.00 | 0.00 | 0.00 | `194.00` (41 SALES) | **`-194.00`** | **-126,100.00** | 0.00 |
| `SKU-0601-EXM` | `Exempt Seedling Trays` | AVG_COST | 175.00 | 50.00 | 0.00 | `20.00` (10 SALES) | `30.00` | `5,250.00` | `5,250.00` |
| `SKU-4016-12` | `Hydraulic Nitrile Seals` | AVG_COST | 455.00 | 120.00 | 0.00 | `25.00` (15 SALES) | `95.00` | `43,225.00` | `43,225.00` |
| `SKU-5208-05` | `Industrial Cotton Fabric Casing` | AVG_COST | 336.00 | 80.00 | 0.00 | `20.00` (10 SALES) | `60.00` | `20,160.00` | `20,160.00` |
| `SKU-8708-28` | `Heavy Transmission Assembly` | AVG_COST | 2240.00 | 40.00 | 0.00 | 0.00 | `40.00` | `89,600.00` | `89,600.00` |
| **Total** | **7 Products** | — | — | **440.00** | **18.00** | **905.00** | **Net `-447.00`** | **`-207,216.82`** | **`158,235.00`** |

---

## 2. Root-Cause Classification

1. **Authoritative Movement Parity:** For all 7 SKUs, `InventoryEntry` movements match `POSTED` `VoucherItem` quantities 1:1 (`DRAFT` invoices and `DRAFT` credit notes produced zero stock deductions/additions), and `orphan_inventory_entries == 0`.
2. **Product Policy (`allow_negative_stock=True`):** `Precision Agro` has no `CompanySettings` override (`has_settings=False`), so [StockService.process_voucher_stock](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/inventory/services/stock_service.py#L31) permits negative inventory by default for MSME billing flexibility (`INV/26-27/0006`..`0485`).
3. **Synthetic Stress-Test Origin:** All three negative SKUs originated solely from Stage 4.6–4.11 synthetic verification and load scripts (`scripts/setup_stage4_6_pilot_cohort.py`, `scripts/setup_stage4_9_catalog_and_parties.py`, and `scripts/test_stage4_11_day5_load_report_profiling_outbox_scaling.py` creating `Exempt Agri Belting`), which posted `640` / `194` / `4` unit sales without commensurate purchase vouchers.
4. **No Blind Mutation Applied:** Following Stage 4.15 Section 8, historical stress-test sales were preserved unaltered without inventing synthetic purchases; negative stock valuation is excluded from asset totals (`>= 0.00` clamp in Balance Sheet stock valuation).
5. **Documented Caution on `rebuild_company_stock()`:** Because seeded opening quantities (`field_minus_entries`: `50`, `120`, `80`, `150`, `40`) do not have initial `'IN'` `InventoryEntry` rows, running `StockService.rebuild_company_stock()` blindly (`IN - OUT`) would overwrite un-entered opening stock (`AuditLog` `REBUILD_STOCK` count confirmed `0`).

---

## 3. Inventory Regression Suite Results (`test_neondb_staging`, `task-50430`)

- `apps.inventory.tests_stage4_15_inventory`: **`3 / 3 OK`**
  - `test_01_sale_within_stock_partial_and_negative_stock_policies`: verified `allow_negative_stock=False` raises `ValidationError` cleanly without stock mutation; `allow_negative_stock=True` allows `-2.00` oversell, clamps Balance Sheet asset cleanly, and recovers cleanly to `+8.00` after subsequent `+10.00` Purchase.
  - `test_02_fifo_lot_exhaustion_credit_note_cost_and_debit_note`: verified FIFO multi-lot COGS (`5*100 + 2*200 = 900.00`), Credit Note acquisition cost restoration (`900/7 = 128.57`, not retail selling price `300.00`), Debit Note original purchase return cost (`100.00`), and `VoucherService.create_reversal_voucher` stock restoration (`4.00 -> 11.00`, deleting `s1` entries).
  - `Stage415ConcurrentInventoryTests.test_concurrent_sales_deduct_stock_without_lost_update`: 2 concurrent PostgreSQL threads (`qty 3` + `qty 4`) deducted stock atomically under `select_for_update()` (`20.00 -> 13.00`, `0` lost updates).
- `apps.accounting.tests_sales_stock_audit`: **`3 / 3 OK`** | `apps.inventory.tests`: **`2 / 2 OK`**.
