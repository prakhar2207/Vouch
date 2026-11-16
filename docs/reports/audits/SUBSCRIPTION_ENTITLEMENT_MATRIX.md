# SRI LEKH — OFFICIAL SUBSCRIPTION ENTITLEMENT & PRICING MATRIX

**Document Authority:** Single Source of Truth derived from [`docs/vouch_tier_feature_matrix.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/docs/vouch_tier_feature_matrix.md).  
**Baseline Tax Rule:** Base Annual Subscription *(+ 18% GST)*. All currency values in INR and integer paise.

---

## 1. Commercial Pricing Matrix

| Attribute | Free Baseline | Tier 1: Starter | Tier 2: Growth *(Popular)* | Tier 3: Pro AI | Tier 4: Enterprise |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Target Persona** | New Signups | Micro-Retail / Dukaan | Small Retail & Traders | Wholesalers & Stockists | Large Distributors |
| **Billing Interval** | Indefinite | Annual | Annual | Annual | Annual |
| **Base Price (INR)** | ₹0.00 | **₹599.00 / yr** | **₹1,499.00 / yr** | **₹2,599.00 / yr** | **₹3,999.00 / yr** |
| **Base Amount (Paise)** | 0 | 59,900 | 149,900 | 259,900 | 399,900 |
| **Applicable GST (18%)** | ₹0.00 | ₹107.82 *(10,782 p)* | ₹269.82 *(26,982 p)* | ₹467.82 *(46,782 p)* | ₹719.82 *(71,982 p)* |
| **Total Payable (INR)** | ₹0.00 | **₹706.82** | **₹1,768.82** | **₹3,066.82** | **₹4,718.82** |
| **Total Payable (Paise)**| 0 | 70,682 | 176,882 | 306,682 | 471,882 |
| **Monthly Equivalent** | ₹0 | ~₹50 / mo | ~₹125 / mo | ~₹217 / mo | ~₹333 / mo |

---

## 2. AI OCR Scan Automation Quotas

| Model / Feature | Free Baseline | Starter (Tier 1) | Growth (Tier 2) | Pro AI (Tier 3) | Enterprise (Tier 4) | Backend Enforcement |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Printed Bill & Bank OCR** *(Fast Model)* | **2 scans / day** | **5 scans / day** | **15 scans / day** | **35 scans / day** | **100 scans / day** | `apps/accounting/ocr_views.py` (`ocr_fast_daily`) |
| **Handwritten Bill OCR** *(Deep Model)* | **0 scans / day** | **1 scan / day** | **3 scans / day** | **6 scans / day** | **20 scans / day** | `apps/accounting/ocr_views.py` (`ocr_deep_daily`) |
| **Split-Screen OCR Split View** | ✅ Unlocked | ✅ Unlocked | ✅ Unlocked | ✅ Unlocked | ✅ Unlocked | `PurchaseOcrSplitView` |
| **Auto-Vendor & Item Matching** | ✅ Unlocked | ✅ Unlocked | ✅ Unlocked | ✅ Unlocked | ✅ Unlocked | `InvoiceOCRService` |

---

## 3. Business Analytics & Intelligence (BI) Gating

| Analytics Feature | Free / Starter | Growth | Pro AI | Enterprise | Backend View / Gate |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Sales Timeline & 7-Day SMA Trends** | ❌ Blocked | ✅ Unlocked | ✅ Unlocked | ✅ Unlocked | `InsightsAPIView` (`bi_sales_timeline`) |
| **Monthly Revenue & Margin Trajectory** | ❌ Blocked | ✅ Unlocked | ✅ Unlocked | ✅ Unlocked | `MonthlyComparisonView` (`bi_monthly_trajectory`) |
| **Brand Contribution Mix** | ❌ Blocked | ✅ Unlocked | ✅ Unlocked | ✅ Unlocked | `AnalyticsEngine` (`bi_brand_mix`) |
| **30-Day Predictive Sales Forecast** | ❌ Blocked | ❌ Blocked | ✅ Unlocked | ✅ Unlocked | `SalesForecastView` (`bi_sales_forecast`) |
| **RFM Customer Segmentation Matrix** | ❌ Blocked | ❌ Blocked | ✅ Unlocked | ✅ Unlocked | `RFMAnalysisView` (`bi_rfm_segmentation`) |
| **Inventory Turnover & Valuation** | ❌ Blocked | ❌ Blocked | ✅ Unlocked | ✅ Unlocked | `AnalyticsEngine` (`bi_inventory_turnover`) |
| **Customer 80/20 Pareto Matrix** | ❌ Blocked | ❌ Blocked | ❌ Blocked | ✅ Unlocked | `AnalyticsEngine` (`bi_pareto_matrix`) |
| **Customer Churn Radar (>45 Days)** | ❌ Blocked | ❌ Blocked | ❌ Blocked | ✅ Unlocked | `AnalyticsEngine` (`bi_churn_radar`) |
| **Cash Conversion Cycle (DSO, DIO, DPO)**| ❌ Blocked | ❌ Blocked | ❌ Blocked | ✅ Unlocked | `CashCycleSnapshotView` (`bi_cash_cycle`) |

---

## 4. Universal Core Modules (100% Unlocked Across All Tiers)

To commoditize accounting ERP for Indian MSMEs, the following modules are never blocked by subscriptions:
1. **Double-Entry Accounting:** Multi-line Journals, Contra transfers, Receipts, Payments, Credit/Debit Notes, Trial Balance, P&L, and Balance Sheet.
2. **Sales & Purchases:** GST B2B/B2C invoicing, Proforma quotations, Thermal POS & A4/A5 PDF generation, and WhatsApp bill links.
3. **GST & CA Bridges:** 1-click GSTR-1/3B summary preparation, GSTR-2B reconciliation, and Tally-compatible XML exports.
4. **Inventory & Godowns:** Live stock valuation (FIFO, Weighted Average, LIFO, Standard), godowns, categories, and min-stock alerts.
5. **Banking Cockpit:** Bank statement upload (Excel, CSV, PDF) and auto-contra matching.
6. **Platform & Security:** Offline-first PWA, conflict-free cloud sync, multi-user RBAC, and SHA-256 tamper-evident audit trails.
