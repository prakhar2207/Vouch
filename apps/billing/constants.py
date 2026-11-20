"""
Official SriLekh Subscription Plans and Tier-Wise Feature Matrix
Single Source of Truth derived directly from docs/vouch_tier_feature_matrix.md
All amounts are in integer paise (1 INR = 100 paise).
Tax Baseline: Base Annual Subscription (+ 18% GST).
"""

from decimal import Decimal

APPROVED_PLANS = [
    {
        "id": "starter",
        "name": "Starter",
        "tagline": "Micro-Retail / Dukaan",
        "description": "Essential double-entry accounting, GST invoicing, B2B network, and daily OCR automation for micro-retailers.",
        "target_persona": "Micro-Retail / Dukaan",
        "billing_interval": "annual",
        "base_amount_paise": 59900,  # ₹599
        "tax_rate": Decimal("18.00"),
        "tax_amount_paise": 10782,   # ₹107.82
        "total_amount_paise": 70682, # ₹706.82
        "currency": "INR",
        "tier_order": 1,
        "features": {
            "b2b_edi_network": True,
            "sales_invoicing": True,
            "double_entry_accounting": True,
            "gst_compliance": True,
            "inventory_management": True,
            "banking_reconciliation": True,
            "offline_pwa": True,
            "audit_trail": True,
            "bi_sales_timeline": False,
            "bi_monthly_trajectory": False,
            "bi_brand_mix": False,
            "bi_sales_forecast": False,
            "bi_rfm_segmentation": False,
            "bi_inventory_turnover": False,
            "bi_pareto_matrix": False,
            "bi_churn_radar": False,
            "bi_cash_cycle": False,
        },
        "limits": {
            "ocr_fast_daily": 5,
            "ocr_deep_daily": 1,
        },
    },
    {
        "id": "growth",
        "name": "Growth",
        "tagline": "Small Retail & Traders",
        "description": "Comprehensive accounting plus Business Analytics, 7-day sales trends, brand contribution mix, and higher OCR capacity.",
        "target_persona": "Small Retail & Traders",
        "billing_interval": "annual",
        "base_amount_paise": 149900,  # ₹1,499
        "tax_rate": Decimal("18.00"),
        "tax_amount_paise": 26982,   # ₹269.82
        "total_amount_paise": 176882, # ₹1,768.82
        "currency": "INR",
        "tier_order": 2,
        "features": {
            "b2b_edi_network": True,
            "sales_invoicing": True,
            "double_entry_accounting": True,
            "gst_compliance": True,
            "inventory_management": True,
            "banking_reconciliation": True,
            "offline_pwa": True,
            "audit_trail": True,
            "bi_sales_timeline": True,
            "bi_monthly_trajectory": True,
            "bi_brand_mix": True,
            "bi_sales_forecast": False,
            "bi_rfm_segmentation": False,
            "bi_inventory_turnover": False,
            "bi_pareto_matrix": False,
            "bi_churn_radar": False,
            "bi_cash_cycle": False,
        },
        "limits": {
            "ocr_fast_daily": 15,
            "ocr_deep_daily": 3,
        },
    },
    {
        "id": "pro_ai",
        "name": "Pro AI",
        "tagline": "Wholesalers & Stockists",
        "description": "Predictive 30-day sales forecasting, RFM customer segmentation, inventory turnover analytics, and expanded OCR automation.",
        "target_persona": "Wholesalers & Stockists",
        "billing_interval": "annual",
        "base_amount_paise": 259900,  # ₹2,599
        "tax_rate": Decimal("18.00"),
        "tax_amount_paise": 46782,   # ₹467.82
        "total_amount_paise": 306682, # ₹3,066.82
        "currency": "INR",
        "tier_order": 3,
        "features": {
            "b2b_edi_network": True,
            "sales_invoicing": True,
            "double_entry_accounting": True,
            "gst_compliance": True,
            "inventory_management": True,
            "banking_reconciliation": True,
            "offline_pwa": True,
            "audit_trail": True,
            "bi_sales_timeline": True,
            "bi_monthly_trajectory": True,
            "bi_brand_mix": True,
            "bi_sales_forecast": True,
            "bi_rfm_segmentation": True,
            "bi_inventory_turnover": True,
            "bi_pareto_matrix": False,
            "bi_churn_radar": False,
            "bi_cash_cycle": False,
        },
        "limits": {
            "ocr_fast_daily": 35,
            "ocr_deep_daily": 6,
        },
    },
    {
        "id": "enterprise",
        "name": "Enterprise",
        "tagline": "Large Distributors",
        "description": "Full platform access with 80/20 Pareto Matrix, Churn Radar, Cash Conversion Cycle analytics, and high-volume OCR scanning.",
        "target_persona": "Large Distributors",
        "billing_interval": "annual",
        "base_amount_paise": 399900,  # ₹3,999
        "tax_rate": Decimal("18.00"),
        "tax_amount_paise": 71982,   # ₹719.82
        "total_amount_paise": 471882, # ₹4,718.82
        "currency": "INR",
        "tier_order": 4,
        "features": {
            "b2b_edi_network": True,
            "sales_invoicing": True,
            "double_entry_accounting": True,
            "gst_compliance": True,
            "inventory_management": True,
            "banking_reconciliation": True,
            "offline_pwa": True,
            "audit_trail": True,
            "bi_sales_timeline": True,
            "bi_monthly_trajectory": True,
            "bi_brand_mix": True,
            "bi_sales_forecast": True,
            "bi_rfm_segmentation": True,
            "bi_inventory_turnover": True,
            "bi_pareto_matrix": True,
            "bi_churn_radar": True,
            "bi_cash_cycle": True,
        },
        "limits": {
            "ocr_fast_daily": 100,
            "ocr_deep_daily": 20,
        },
    },
]

# Baseline fallback entitlements for unsubscribed/free workspaces
DEFAULT_BASELINE_ENTITLEMENTS = {
    "plan_id": "free_tier",
    "plan_name": "Free Starter Access",
    "status": "active",
    "features": {
        "b2b_edi_network": True,
        "sales_invoicing": True,
        "double_entry_accounting": True,
        "gst_compliance": True,
        "inventory_management": True,
        "banking_reconciliation": True,
        "offline_pwa": True,
        "audit_trail": True,
        "bi_sales_timeline": False,
        "bi_monthly_trajectory": False,
        "bi_brand_mix": False,
        "bi_sales_forecast": False,
        "bi_rfm_segmentation": False,
        "bi_inventory_turnover": False,
        "bi_pareto_matrix": False,
        "bi_churn_radar": False,
        "bi_cash_cycle": False,
    },
    "limits": {
        "ocr_fast_daily": 2,
        "ocr_deep_daily": 0,
    },
}
