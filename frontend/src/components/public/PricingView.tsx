"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Check,
  X,
  Sparkles,
  Zap,
  ShieldCheck,
  Building,
  HelpCircle,
  ArrowRight,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import api from "@/utils/api";
import { isAuthenticated } from "@/utils/auth";
import { useCompany } from "@/context/CompanyContext";
import { openRazorpayCheckout } from "@/lib/billing/razorpay-checkout";

interface Plan {
  id: string;
  name: string;
  tagline: string;
  description: string;
  target_persona: string;
  billing_interval: string;
  base_amount_paise: number;
  base_amount_rupees: string;
  tax_amount_rupees: string;
  total_amount_rupees: string;
  total_amount_paise: number;
  tier_order: number;
  features: Record<string, boolean>;
  limits: {
    ocr_fast_daily: number;
    ocr_deep_daily: number;
  };
}

const STATIC_FALLBACK_PLANS: Plan[] = [
  {
    id: "starter",
    name: "Starter",
    tagline: "Micro-Retail / Dukaan",
    description: "Essential double-entry accounting, GST invoicing, B2B network, and daily OCR automation for micro-retailers.",
    target_persona: "Micro-Retail / Dukaan",
    billing_interval: "annual",
    base_amount_paise: 59900,
    base_amount_rupees: "599.00",
    tax_amount_rupees: "107.82",
    total_amount_rupees: "706.82",
    total_amount_paise: 70682,
    tier_order: 1,
    features: {
      b2b_edi_network: true,
      sales_invoicing: true,
      double_entry_accounting: true,
      gst_compliance: true,
      inventory_management: true,
      banking_reconciliation: true,
      offline_pwa: true,
      audit_trail: true,
      bi_sales_timeline: false,
      bi_monthly_trajectory: false,
      bi_brand_mix: false,
      bi_sales_forecast: false,
      bi_rfm_segmentation: false,
      bi_inventory_turnover: false,
      bi_pareto_matrix: false,
      bi_churn_radar: false,
      bi_cash_cycle: false,
    },
    limits: {
      ocr_fast_daily: 5,
      ocr_deep_daily: 1,
    },
  },
  {
    id: "growth",
    name: "Growth",
    tagline: "Small Retail & Traders",
    description: "Comprehensive accounting plus Business Analytics, 7-day sales trends, brand contribution mix, and higher OCR capacity.",
    target_persona: "Small Retail & Traders",
    billing_interval: "annual",
    base_amount_paise: 149900,
    base_amount_rupees: "1499.00",
    tax_amount_rupees: "269.82",
    total_amount_rupees: "1768.82",
    total_amount_paise: 176882,
    tier_order: 2,
    features: {
      b2b_edi_network: true,
      sales_invoicing: true,
      double_entry_accounting: true,
      gst_compliance: true,
      inventory_management: true,
      banking_reconciliation: true,
      offline_pwa: true,
      audit_trail: true,
      bi_sales_timeline: true,
      bi_monthly_trajectory: true,
      bi_brand_mix: true,
      bi_sales_forecast: false,
      bi_rfm_segmentation: false,
      bi_inventory_turnover: false,
      bi_pareto_matrix: false,
      bi_churn_radar: false,
      bi_cash_cycle: false,
    },
    limits: {
      ocr_fast_daily: 15,
      ocr_deep_daily: 3,
    },
  },
  {
    id: "pro_ai",
    name: "Pro AI",
    tagline: "Wholesalers & Stockists",
    description: "Predictive 30-day sales forecasting, RFM customer segmentation, inventory turnover analytics, and expanded OCR automation.",
    target_persona: "Wholesalers & Stockists",
    billing_interval: "annual",
    base_amount_paise: 259900,
    base_amount_rupees: "2599.00",
    tax_amount_rupees: "467.82",
    total_amount_rupees: "3066.82",
    total_amount_paise: 306682,
    tier_order: 3,
    features: {
      b2b_edi_network: true,
      sales_invoicing: true,
      double_entry_accounting: true,
      gst_compliance: true,
      inventory_management: true,
      banking_reconciliation: true,
      offline_pwa: true,
      audit_trail: true,
      bi_sales_timeline: true,
      bi_monthly_trajectory: true,
      bi_brand_mix: true,
      bi_sales_forecast: true,
      bi_rfm_segmentation: true,
      bi_inventory_turnover: true,
      bi_pareto_matrix: false,
      bi_churn_radar: false,
      bi_cash_cycle: false,
    },
    limits: {
      ocr_fast_daily: 35,
      ocr_deep_daily: 6,
    },
  },
  {
    id: "enterprise",
    name: "Enterprise",
    tagline: "Large Distributors",
    description: "Full platform access with 80/20 Pareto Matrix, Churn Radar, Cash Conversion Cycle analytics, and high-volume OCR scanning.",
    target_persona: "Large Distributors",
    billing_interval: "annual",
    base_amount_paise: 399900,
    base_amount_rupees: "3999.00",
    tax_amount_rupees: "719.82",
    total_amount_rupees: "4718.82",
    total_amount_paise: 471882,
    tier_order: 4,
    features: {
      b2b_edi_network: true,
      sales_invoicing: true,
      double_entry_accounting: true,
      gst_compliance: true,
      inventory_management: true,
      banking_reconciliation: true,
      offline_pwa: true,
      audit_trail: true,
      bi_sales_timeline: true,
      bi_monthly_trajectory: true,
      bi_brand_mix: true,
      bi_sales_forecast: true,
      bi_rfm_segmentation: true,
      bi_inventory_turnover: true,
      bi_pareto_matrix: true,
      bi_churn_radar: true,
      bi_cash_cycle: true,
    },
    limits: {
      ocr_fast_daily: 100,
      ocr_deep_daily: 20,
    },
  },
];

export function PricingView() {
  const router = useRouter();
  const { activeCompany, availableCompanies } = useCompany();
  const [plans, setPlans] = useState<Plan[]>(STATIC_FALLBACK_PLANS);
  const [loading, setLoading] = useState(true);
  const [processingPlanId, setProcessingPlanId] = useState<string | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [currentSubPlanId, setCurrentSubPlanId] = useState<string | null>(null);
  const isAuthed = isAuthenticated();

  useEffect(() => {
    async function fetchPlansAndSub() {
      try {
        const res = await api.get("/api/v1/billing/plans/");
        if (res.data?.success && Array.isArray(res.data.plans) && res.data.plans.length > 0) {
          setPlans(res.data.plans);
        }
      } catch (err) {
        console.warn("Could not fetch live plans, using verified matrix fallback.", err);
      } finally {
        setLoading(false);
      }

      if (isAuthed && activeCompany?.id) {
        try {
          const subRes = await api.get(`/api/v1/billing/subscription/?company_id=${activeCompany.id}`);
          if (subRes.data?.subscription?.plan?.id) {
            setCurrentSubPlanId(subRes.data.subscription.plan.id);
          }
        } catch {
          // ignore error for free tier
        }
      }
    }

    fetchPlansAndSub();
  }, [isAuthed, activeCompany?.id]);

  const handleSelectPlan = async (plan: Plan) => {
    setCheckoutError(null);

    // If not authenticated, redirect to register/login with intent
    if (!isAuthed) {
      router.push(`/register?plan=${plan.id}`);
      return;
    }

    if (!activeCompany?.id) {
      setCheckoutError("Please select or create an active company workspace to assign the subscription.");
      return;
    }

    setProcessingPlanId(plan.id);

    try {
      // 1. Create checkout order on backend
      const orderRes = await api.post("/api/v1/billing/checkout/create-order/", {
        plan_id: plan.id,
        company_id: activeCompany.id,
      });

      if (!orderRes.data?.success || !orderRes.data.checkout) {
        throw new Error(orderRes.data?.error || "Failed to initialize payment checkout order.");
      }

      const checkout = orderRes.data.checkout;

      // 2. Open Razorpay Checkout Modal
      await openRazorpayCheckout({
        key: checkout.key_id,
        amount: checkout.amount,
        currency: checkout.currency,
        orderId: checkout.order_id,
        name: "SriLekh Accounting",
        description: `${plan.name} Annual Subscription (+ 18% GST)`,
        prefill: {
          name: activeCompany.name,
          email: activeCompany.email || "",
        },
        notes: {
          company_id: activeCompany.id,
          plan_id: plan.id,
        },
        onSuccess: async (paymentData) => {
          try {
            // 3. Cryptographically verify payment on backend
            const verifyRes = await api.post("/api/v1/billing/checkout/verify/", {
              company_id: activeCompany.id,
              razorpay_order_id: paymentData.razorpay_order_id,
              razorpay_payment_id: paymentData.razorpay_payment_id,
              razorpay_signature: paymentData.razorpay_signature,
            });

            if (verifyRes.data?.success) {
              // Redirect to settings billing page with invoice confirmation
              router.push("/settings/billing?activated=true");
            } else {
              setCheckoutError("Payment verification failed on the server. Please contact support.");
            }
          } catch (err: any) {
            setCheckoutError(err.response?.data?.error || "Failed to verify payment with server.");
          } finally {
            setProcessingPlanId(null);
          }
        },
        onError: (err: any) => {
          setCheckoutError(err.description || err.message || "Payment cancelled or failed.");
          setProcessingPlanId(null);
        },
        onDismiss: () => {
          setProcessingPlanId(null);
        },
      });
    } catch (err: any) {
      setCheckoutError(err.response?.data?.error || err.message || "Checkout failed. Please try again.");
      setProcessingPlanId(null);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      {/* Header */}
      <div className="text-center max-w-3xl mx-auto space-y-4">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-900 text-blue-700 dark:text-blue-300 text-xs font-semibold">
          <Sparkles className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
          <span>Transparent Pricing for Indian Businesses</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-black tracking-tight text-slate-900 dark:text-white">
          Accounting ERP Built for Indian MSMEs
        </h1>
        <p className="text-base sm:text-lg text-slate-600 dark:text-slate-400">
          Core double-entry accounting and GST compliance are unlocked across all plans.
          Choose the tier that matches your daily OCR scan volume and business analytics needs.
        </p>

        {isAuthed && activeCompany && (
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800 text-xs text-emerald-800 dark:text-emerald-300">
            <Building className="w-3.5 h-3.5" />
            <span>
              Active Workspace: <strong>{activeCompany.name}</strong>
            </span>
          </div>
        )}

        {checkoutError && (
          <div className="p-3 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-900 rounded-xl text-xs text-red-700 dark:text-red-300 flex items-center justify-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{checkoutError}</span>
          </div>
        )}
      </div>

      {/* Pricing Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mt-12">
        {plans.map((plan) => {
          const isCurrent = currentSubPlanId === plan.id;
          const isPopular = plan.id === "growth";
          const isProcessing = processingPlanId === plan.id;

          return (
            <div
              key={plan.id}
              className={`relative rounded-2xl p-6 flex flex-col justify-between transition-all duration-200 ${
                isPopular
                  ? "border-2 border-[#162C5B] dark:border-[#E28123] shadow-xl bg-card"
                  : "border border-border bg-card hover:border-border/80 shadow-sm"
              }`}
            >
              {isPopular && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full bg-[#162C5B] dark:bg-[#E28123] text-white text-[11px] font-bold tracking-wide uppercase shadow-sm">
                  Most Popular
                </div>
              )}

              <div>
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-xl font-bold text-foreground">{plan.name}</h3>
                  <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-muted text-muted-foreground">
                    {plan.target_persona}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-2 leading-relaxed min-h-[36px]">
                  {plan.description}
                </p>

                {/* Price Display */}
                <div className="mt-6 border-t border-border pt-4">
                  <div className="flex items-baseline gap-1">
                    <span className="text-3xl font-extrabold text-foreground">
                      ₹{Math.round(parseFloat(plan.base_amount_rupees)).toLocaleString("en-IN")}
                    </span>
                    <span className="text-xs text-muted-foreground">/ year</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    + 18% GST (₹{plan.tax_amount_rupees}) = <strong>₹{plan.total_amount_rupees}</strong> total
                  </p>
                </div>

                {/* Key Quota Highlights */}
                <div className="mt-6 space-y-2.5 text-xs">
                  <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-zinc-900 border border-border flex items-center justify-between">
                    <span className="text-muted-foreground font-medium">Printed &amp; Bank OCR</span>
                    <strong className="text-foreground">{plan.limits.ocr_fast_daily} scans/day</strong>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-zinc-900 border border-border flex items-center justify-between">
                    <span className="text-muted-foreground font-medium">Handwritten OCR</span>
                    <strong className="text-foreground">{plan.limits.ocr_deep_daily} scans/day</strong>
                  </div>
                </div>

                {/* Features List */}
                <ul className="mt-6 space-y-2 text-xs text-muted-foreground border-t border-border pt-4">
                  <li className="flex items-center gap-2 text-foreground font-medium">
                    <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                    <span>Complete Double-Entry Accounting</span>
                  </li>
                  <li className="flex items-center gap-2 text-foreground font-medium">
                    <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                    <span>GST Invoicing &amp; Return JSON</span>
                  </li>
                  <li className="flex items-center gap-2 text-foreground font-medium">
                    <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                    <span>Real-Time Inventory Tracking</span>
                  </li>
                  <li className="flex items-center gap-2 text-foreground font-medium">
                    <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                    <span>Bank Statement Reconciliation</span>
                  </li>
                  <li className="flex items-center gap-2 text-foreground font-medium">
                    <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                    <span>100% Offline-First PWA Billing</span>
                  </li>

                  {/* Tier-Specific BI Highlights */}
                  <li className={`flex items-center gap-2 ${plan.features.bi_sales_timeline ? "text-foreground font-medium" : "text-muted-foreground/60"}`}>
                    {plan.features.bi_sales_timeline ? (
                      <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                    ) : (
                      <X className="w-4 h-4 text-muted-foreground/40 shrink-0" />
                    )}
                    <span>Sales Timeline &amp; 7-Day Trends</span>
                  </li>

                  <li className={`flex items-center gap-2 ${plan.features.bi_sales_forecast ? "text-foreground font-medium" : "text-muted-foreground/60"}`}>
                    {plan.features.bi_sales_forecast ? (
                      <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                    ) : (
                      <X className="w-4 h-4 text-muted-foreground/40 shrink-0" />
                    )}
                    <span>30-Day Predictive Sales Forecast</span>
                  </li>

                  <li className={`flex items-center gap-2 ${plan.features.bi_rfm_segmentation ? "text-foreground font-medium" : "text-muted-foreground/60"}`}>
                    {plan.features.bi_rfm_segmentation ? (
                      <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                    ) : (
                      <X className="w-4 h-4 text-muted-foreground/40 shrink-0" />
                    )}
                    <span>RFM Customer Matrix &amp; Turnover</span>
                  </li>

                  <li className={`flex items-center gap-2 ${plan.features.bi_cash_cycle ? "text-foreground font-medium" : "text-muted-foreground/60"}`}>
                    {plan.features.bi_cash_cycle ? (
                      <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                    ) : (
                      <X className="w-4 h-4 text-muted-foreground/40 shrink-0" />
                    )}
                    <span>Cash Conversion Cycle &amp; Churn Radar</span>
                  </li>
                </ul>
              </div>

              {/* Action Button */}
              <div className="mt-8 pt-4 border-t border-border">
                {isCurrent ? (
                  <button
                    disabled
                    className="w-full py-2.5 px-4 bg-muted text-muted-foreground rounded-xl text-xs font-bold cursor-not-allowed flex items-center justify-center gap-1.5"
                  >
                    <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                    <span>Current Active Plan</span>
                  </button>
                ) : (
                  <button
                    onClick={() => handleSelectPlan(plan)}
                    disabled={isProcessing}
                    className={`w-full py-3 px-4 rounded-xl text-xs font-bold transition-all shadow-md flex items-center justify-center gap-2 ${
                      isPopular
                        ? "bg-[#162C5B] hover:bg-[#0F1E3D] dark:bg-[#E28123] dark:hover:bg-[#c86815] text-white"
                        : "bg-slate-900 hover:bg-slate-800 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-white"
                    }`}
                  >
                    {isProcessing ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Initializing Checkout...</span>
                      </>
                    ) : (
                      <>
                        <span>{isAuthed ? "Subscribe with Razorpay" : "Get Started"}</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Trust & Guarantee Banner */}
      <div className="mt-16 p-6 sm:p-8 rounded-2xl bg-slate-50 dark:bg-card/40 border border-border grid grid-cols-1 md:grid-cols-3 gap-6 text-center md:text-left">
        <div className="flex flex-col sm:flex-row items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-600 flex items-center justify-center shrink-0">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-foreground">Secure Razorpay Payments</h4>
            <p className="text-xs text-muted-foreground mt-0.5">
              Encrypted UPI, Cards, NetBanking, and automated GST billing receipts.
            </p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/10 text-blue-600 flex items-center justify-center shrink-0">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-foreground">Instant Plan Activation</h4>
            <p className="text-xs text-muted-foreground mt-0.5">
              OCR scan quotas and analytics unlock immediately upon payment verification.
            </p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 text-amber-600 flex items-center justify-center shrink-0">
            <Building className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-foreground">Double-Entry Accounting Unlocked</h4>
            <p className="text-xs text-muted-foreground mt-0.5">
              Zero paywalls on sales invoicing, ledger books, inventory, and GST reports.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
