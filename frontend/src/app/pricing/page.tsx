import React, { Fragment } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Building2,
  Check,
  CheckCircle2,
  FileCheck,
  HelpCircle,
  Landmark,
  Layers,
  Mail,
  Minus,
  Package,
  Receipt,
  Scale,
  ShieldCheck,
  Sparkles,
  WifiOff,
  Zap,
} from "lucide-react";
import { PublicHeader } from "@/components/public/PublicHeader";
import { PublicFooter } from "@/components/public/PublicFooter";
import { NativeCommercialGuard } from "@/components/public/NativeCommercialGuard";
import { SRILEKH_PUBLIC } from "@/components/public/public-constants";

export const metadata: Metadata = {
  title: {
    absolute: "SriLekh Pricing | Transparent Accounting Plans for Indian Businesses",
  },
  description:
    "Explore transparent subscription pricing for SriLekh accounting software. 4 plans starting at ₹599/yr with B2B network, multi-device access, AI OCR, bank reconciliation, and 7-day money-back guarantee.",
  alternates: {
    canonical: "/pricing",
  },
};

interface PricingPlan {
  id: string;
  name: string;
  subtitle: string;
  target: string;
  priceInr: number;
  monthlyEquivalent: number;
  badge?: string;
  popular?: boolean;
  features: string[];
  heroHighlights: string[];
  ocrQuota: {
    fast: number;
    powerful: number;
  };
}

const pricingPlans: PricingPlan[] = [
  {
    id: "starter",
    name: "Starter",
    subtitle: "Essential GST Billing & Khata",
    target: "Micro-Retail / Dukaan / Solo Traders",
    priceInr: 599,
    monthlyEquivalent: 50,
    features: [
      "Unlimited Multi-Device Access (Phone, PC, Tablet)",
      "100% Unlocked B2B Network Inward Auto-Ingestion",
      "5 Fast Printed Bill & Bank OCR Scans / day",
      "1 Powerful Handwritten OCR Scan / day",
      "Full GST Invoicing (B2B / B2C) & POS Thermal Receipts",
      "Complete Double-Entry Accounting & Customer Khata",
      "Single-Godown / Shop Inventory & Safety Stock Alerts",
      "100% Offline-First PWA with Cloud Auto-Sync",
    ],
    heroHighlights: [
      "B2B Network Auto-Bill Ingest",
      "Daily AI OCR Included",
      "Multi-Device Sync",
    ],
    ocrQuota: { fast: 5, powerful: 1 },
  },
  {
    id: "growth",
    name: "Growth",
    subtitle: "Operational Scale & Business Trends",
    target: "Small Retail & Active Traders",
    priceInr: 1499,
    monthlyEquivalent: 125,
    features: [
      "Everything in Starter, plus:",
      "15 Fast Printed Bill & Bank OCR Scans / day",
      "3 Powerful Handwritten OCR Scans / day",
      "Sales Timeline & 7-Day Moving Average Trends",
      "Monthly Trajectory (Revenue, Expense, Margins)",
      "Manufacturer Brand Contribution Mix",
      "Multi-Bank & Cash Ledger Tracking",
      "Detailed Party Aging Reports (0–90+ Days)",
    ],
    heroHighlights: [
      "3x AI OCR Scan Quota",
      "Business Analytics & Trends",
      "Party Aging & Khata Insights",
    ],
    ocrQuota: { fast: 15, powerful: 3 },
  },
  {
    id: "pro-ai",
    name: "Pro AI",
    subtitle: "Automated Recon & Predictive AI",
    target: "Wholesalers, Stockists & CAs",
    priceInr: 2599,
    monthlyEquivalent: 217,
    badge: "Most Popular — Best Value",
    popular: true,
    features: [
      "Everything in Growth, plus:",
      "35 Fast Printed Bill & Bank OCR Scans / day",
      "6 Powerful Handwritten OCR Scans / day",
      "Automated 4-Pass Bank Statement Reconciliation",
      "Contra Voucher Auto-Matching",
      "ITC Shield: GSTR-2B Automated Invoice Reconciliation",
      "30-Day AI Predictive Sales Forecasting",
      "RFM Customer Segmentation Matrix",
      "Multi-Godown Tracking (Up to 3 Warehouses)",
      "Inter-Godown Stock Transfer Vouchers",
    ],
    heroHighlights: [
      "✨ Auto Bank Statement Recon",
      "✨ GSTR-2B ITC Shield",
      "✨ 30-Day Predictive AI Forecast",
      "✨ Multi-Godown Transfers",
    ],
    ocrQuota: { fast: 35, powerful: 6 },
  },
  {
    id: "enterprise",
    name: "Enterprise",
    subtitle: "High Volume & Multi-Branch Intelligence",
    target: "Large Distributors & Multi-Branch",
    priceInr: 3999,
    monthlyEquivalent: 333,
    badge: "Maximum Power",
    features: [
      "Everything in Pro AI, plus:",
      "100 Fast Printed Bill & Bank OCR Scans / day",
      "20 Powerful Handwritten OCR Scans / day",
      "Unlimited Godowns & Multi-Branch Stock Matrix",
      "Customer 80/20 Pareto Matrix Analysis",
      "Customer Churn Radar (>45 Days Inactive)",
      "Net Cash Conversion Cycle (DSO, DIO, DPO, CCC)",
      "Auto-Reconciliation Engine with Custom Matching Rules",
      "Priority CA & Phone Support with Dedicated Onboarding",
    ],
    heroHighlights: [
      "✨ 100+ Daily AI OCR Scans",
      "✨ Unlimited Warehouses",
      "✨ Customer Churn Radar & Pareto",
      "✨ Priority CA Phone Support",
    ],
    ocrQuota: { fast: 100, powerful: 20 },
  },
];

const matrixComparisonRows = [
  {
    category: "Platform & Multi-Device",
    items: [
      { name: "Multi-Device Login (Phone, PC, Tablet, Mac)", starter: true, growth: true, pro: true, enterprise: true },
      { name: "100% Offline-First PWA (Zero Internet Billing)", starter: true, growth: true, pro: true, enterprise: true },
      { name: "Conflict-Free Background Cloud Auto-Sync", starter: true, growth: true, pro: true, enterprise: true },
      { name: "Tamper-Proof Audit Trail & Version Logs (/audit)", starter: true, growth: true, pro: true, enterprise: true },
    ],
  },
  {
    category: "B2B EDI Network (Open for All)",
    items: [
      { name: "B2B Inward Network Inbox (/network/inbox)", starter: true, growth: true, pro: true, enterprise: true },
      { name: "1-Click Inward Bill Accept & Purchase Ledger Ingest", starter: true, growth: true, pro: true, enterprise: true },
      { name: "Viral Invoice Claim System (/claim)", starter: true, growth: true, pro: true, enterprise: true },
      { name: "Digital Cryptographic Bill Verification", starter: true, growth: true, pro: true, enterprise: true },
    ],
  },
  {
    category: "AI OCR Automation",
    items: [
      { name: "Printed Bill & Bank OCR (Fast Model)", starter: "5 / day", growth: "15 / day", pro: "35 / day", enterprise: "100 / day" },
      { name: "Handwritten Bill OCR (Powerful Model)", starter: "1 / day", growth: "3 / day", pro: "6 / day", enterprise: "20 / day" },
      { name: "Split-Screen Verification (PurchaseOcrSplitView)", starter: true, growth: true, pro: true, enterprise: true },
      { name: "Auto-Vendor & Item Matching", starter: true, growth: true, pro: true, enterprise: true },
    ],
  },
  {
    category: "Hero Automation: Banking & Reconciliation",
    items: [
      { name: "Multi-Bank & Cash Ledger Tracking", starter: true, growth: true, pro: true, enterprise: true },
      { name: "Bank Statement Upload (Excel / CSV / PDF)", starter: "View only", growth: "View only", pro: true, enterprise: true },
      { name: "4-Pass Automated Reconciliation Engine", starter: false, growth: false, pro: true, enterprise: "Custom Rules" },
      { name: "Contra Voucher Auto-Matching", starter: false, growth: false, pro: true, enterprise: true },
    ],
  },
  {
    category: "Hero Automation: GST ITC Shield & Compliance",
    items: [
      { name: "1-Click GSTR-1 & GSTR-3B Portal JSON Export", starter: true, growth: true, pro: true, enterprise: true },
      { name: "1-Click Native Tally XML Export for CAs", starter: true, growth: true, pro: true, enterprise: true },
      { name: "ITC Shield: GSTR-2B Invoice Reconciliation", starter: false, growth: false, pro: true, enterprise: "Discrepancy Radar" },
    ],
  },
  {
    category: "Hero Automation: Predictive AI & Business Intelligence",
    items: [
      { name: "Sales Timeline & 7-Day SMA Trends", starter: false, growth: true, pro: true, enterprise: true },
      { name: "Monthly Trajectory (Revenue, Expense, Margin)", starter: false, growth: true, pro: true, enterprise: true },
      { name: "Brand Contribution Mix (Volume & Margin)", starter: false, growth: true, pro: true, enterprise: true },
      { name: "AI Predictive Sales Forecast (30-Day Projections)", starter: false, growth: false, pro: true, enterprise: true },
      { name: "RFM Customer Segmentation Matrix", starter: false, growth: false, pro: true, enterprise: true },
      { name: "Customer 80/20 Pareto Matrix Analysis", starter: false, growth: false, pro: false, enterprise: true },
      { name: "Customer Churn Radar (>45 Days Inactive)", starter: false, growth: false, pro: false, enterprise: true },
      { name: "Cash Conversion Cycle (DSO, DIO, DPO, Net CCC)", starter: false, growth: false, pro: false, enterprise: true },
    ],
  },
  {
    category: "Warehousing & Inventory Scaling",
    items: [
      { name: "Real-Time Live Stock Tracking & Valuation", starter: true, growth: true, pro: true, enterprise: true },
      { name: "Safety Minimum Quantity & Low-Stock Alerts", starter: true, growth: true, pro: true, enterprise: true },
      { name: "Slow-Moving / Bench Stock Alerts (30/60/90+ Days)", starter: true, growth: true, pro: true, enterprise: true },
      { name: "Multi-Godown / Warehouse Tracking", starter: "Single Godown", growth: "Single Godown", pro: "Up to 3 Godowns", enterprise: "Unlimited" },
      { name: "Inter-Godown Stock Transfer Vouchers", starter: false, growth: false, pro: true, enterprise: true },
    ],
  },
  {
    category: "Core Invoicing & Complete Accounting",
    items: [
      { name: "GST Invoicing (B2B, B2C, Proforma, Credit/Debit Notes)", starter: true, growth: true, pro: true, enterprise: true },
      { name: "Thermal POS & A4/A5 PDF Invoice Printing", starter: true, growth: true, pro: true, enterprise: true },
      { name: "1-Click WhatsApp Invoice & Payment Link Dispatch", starter: true, growth: true, pro: true, enterprise: true },
      { name: "Complete Double-Entry (Receipt, Payment, Journal, Contra)", starter: true, growth: true, pro: true, enterprise: true },
      { name: "Balance Sheet, Profit & Loss, Trial Balance Reports", starter: true, growth: true, pro: true, enterprise: true },
    ],
  },
];

const faqs = [
  {
    question: "How does the 7-day money-back guarantee work?",
    answer:
      "All SriLekh annual subscriptions include a 7-day money-back guarantee. If you are not satisfied with the software for any reason within 7 days of purchase, email support@srilekh.com. We will initiate a 100% refund via Razorpay back to your original payment method within 5–7 business days.",
  },
  {
    question: "Do all plans include multi-device access?",
    answer:
      "Yes! You can sign in to your SriLekh account simultaneously on your Android phone, tablet, desktop PC, Mac, or laptop. Your data automatically synchronizes in real-time across all connected devices.",
  },
  {
    question: "What happens if I exceed my daily AI OCR scan quota?",
    answer:
      "Your daily OCR quota resets automatically every night at 00:00 IST. If you need more scans immediately, you can upgrade your plan or manually enter purchase bills anytime without restriction.",
  },
  {
    question: "Does SriLekh support GST input tax credit (ITC) for my purchase?",
    answer:
      "Yes. Upon subscription payment through Razorpay, you receive a valid GST tax invoice with our GSTIN and your business GSTIN so you can claim 100% Input Tax Credit on the 18% GST paid.",
  },
  {
    question: "Can I use SriLekh when my internet is disconnected?",
    answer:
      "Yes. SriLekh is engineered as an installable Progressive Web App (PWA) with local IndexedDB storage. You can create invoices, manage khata, and record sales offline; your entries sync automatically as soon as internet connectivity returns.",
  },
  {
    question: "Can I upgrade my plan midway through the year?",
    answer:
      "Yes. You can upgrade from Starter or Growth to Pro AI or Enterprise anytime. The unused portion of your current annual subscription will be prorated and credited toward your new plan.",
  },
];

export default function PricingPage() {
  return (
    <NativeCommercialGuard>
      <div className="min-h-screen bg-background text-foreground flex flex-col selection:bg-[#162C5B]/15 selection:text-[#162C5B]">
        <PublicHeader activePath="/pricing" />

        <main className="flex-1">
          {/* A. Hero Section */}
          <section className="relative overflow-hidden border-b border-border/60 py-16 sm:py-24">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[720px] h-[320px] bg-gradient-to-b from-[#162C5B]/10 via-[#E28123]/8 to-transparent blur-3xl pointer-events-none rounded-full" />

            <div className="max-w-5xl mx-auto px-6 text-center space-y-6 relative z-10">
              <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#E28123]/10 dark:bg-[#E28123]/15 border border-[#E28123]/25 text-[#C86815] dark:text-[#FBA94C] text-xs font-semibold">
                <Sparkles className="w-3.5 h-3.5 text-[#E28123]" />
                <span>Simple, Fair &amp; Transparent MSME Pricing</span>
              </div>

              <h1 className="text-3xl sm:text-5xl font-black tracking-tight text-balance">
                Honest accounting software pricing for Indian businesses.
              </h1>

              <p className="text-sm sm:text-base text-muted-foreground max-w-2xl mx-auto leading-relaxed">
                Start at just ₹50/month. B2B Network, unlimited invoicing, multi-device access, and
                daily AI OCR are included on all plans. Unlock automated bank reconciliation and
                GSTR-2B ITC Shield as your business grows.
              </p>

              {/* Trust Badges */}
              <div className="pt-2 flex items-center justify-center gap-6 sm:gap-8 text-xs text-muted-foreground flex-wrap">
                <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
                  <ShieldCheck className="w-4 h-4 text-emerald-600" />
                  <span>7-Day Money-Back Guarantee</span>
                </span>
                <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
                  <Zap className="w-4 h-4 text-amber-600" />
                  <span>Instant Razorpay Checkout</span>
                </span>
                <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
                  <CheckCircle2 className="w-4 h-4 text-blue-600" />
                  <span>100% Input Tax Credit (GST Invoice)</span>
                </span>
              </div>
            </div>
          </section>

          {/* B. 4-Tier Pricing Cards Grid */}
          <section className="py-14 sm:py-20 border-b border-border/60 bg-slate-50/50 dark:bg-card/20">
            <div className="max-w-7xl mx-auto px-6 space-y-12">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 items-stretch">
                {pricingPlans.map((plan) => {
                  const isPopular = plan.popular;
                  const gstAmount = Math.round(plan.priceInr * 0.18);
                  const totalWithGst = plan.priceInr + gstAmount;

                  return (
                    <div
                      key={plan.id}
                      className={`relative rounded-3xl border flex flex-col justify-between p-6 sm:p-7 transition-all duration-200 ${
                        isPopular
                          ? "border-[#162C5B] dark:border-[#E28123] bg-card shadow-xl ring-2 ring-[#162C5B]/20 dark:ring-[#E28123]/30 scale-[1.02]"
                          : "border-border bg-card/80 hover:border-border/80 hover:shadow-md"
                      }`}
                    >
                      {/* Popular / Best Value Badge */}
                      {plan.badge && (
                        <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                          <span
                            className={`px-3 py-1 rounded-full text-[11px] font-bold tracking-wide uppercase shadow-sm ${
                              isPopular
                                ? "bg-[#162C5B] text-white dark:bg-[#E28123] dark:text-slate-950"
                                : "bg-slate-800 text-white"
                            }`}
                          >
                            {plan.badge}
                          </span>
                        </div>
                      )}

                      <div className="space-y-5">
                        {/* Plan Header */}
                        <div className="space-y-1.5">
                          <h2 className="text-xl font-black text-foreground">{plan.name}</h2>
                          <p className="text-xs text-muted-foreground min-h-[32px] leading-snug">
                            {plan.subtitle}
                          </p>
                        </div>

                        {/* Price */}
                        <div className="pt-2 border-t border-border/60">
                          <div className="flex items-baseline gap-1">
                            <span className="text-3xl sm:text-4xl font-black text-foreground">
                              ₹{plan.priceInr.toLocaleString("en-IN")}
                            </span>
                            <span className="text-xs text-muted-foreground font-semibold">/ year</span>
                          </div>
                          <div className="text-[11px] text-muted-foreground flex items-center justify-between mt-1">
                            <span>~₹{plan.monthlyEquivalent}/mo</span>
                            <span className="font-medium text-slate-700 dark:text-slate-300">
                              +18% GST (₹{totalWithGst})
                            </span>
                          </div>
                        </div>

                        {/* Persona Pill */}
                        <div className="py-1.5 px-3 rounded-xl bg-muted/60 text-[11px] font-medium text-muted-foreground">
                          Target: <strong className="text-foreground">{plan.target}</strong>
                        </div>

                        {/* Hero Highlights */}
                        <div className="space-y-1.5 py-2 border-y border-border/60">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                            Key Highlights:
                          </span>
                          <div className="space-y-1">
                            {plan.heroHighlights.map((hl, i) => (
                              <div
                                key={i}
                                className="text-xs font-semibold text-emerald-800 dark:text-emerald-400 flex items-center gap-1.5"
                              >
                                <Check className="w-3.5 h-3.5 shrink-0" />
                                <span>{hl}</span>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Features List */}
                        <div className="space-y-2.5 pt-1">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                            Included in this plan:
                          </span>
                          <ul className="space-y-2 text-xs text-muted-foreground">
                            {plan.features.map((feat, i) => (
                              <li key={i} className="flex items-start gap-2 leading-relaxed">
                                <CheckCircle2 className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
                                <span className={i === 0 && plan.id !== "starter" ? "font-bold text-foreground" : ""}>
                                  {feat}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>

                      {/* CTA Button */}
                      <div className="pt-6 mt-6 border-t border-border/60">
                        <Link
                          href="/register"
                          className={`w-full py-2.5 px-4 rounded-xl text-xs font-bold transition-all inline-flex items-center justify-center gap-1.5 shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                            isPopular
                              ? "bg-[#162C5B] hover:bg-[#0F1E3D] dark:bg-[#E28123] dark:hover:bg-[#c86815] text-white dark:text-slate-950 shadow-md"
                              : "bg-primary hover:bg-primary/90 text-primary-foreground"
                          }`}
                        >
                          <span>Get Started</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Payment & Security Notice Banner */}
              <div className="rounded-2xl border border-border bg-card p-6 flex flex-col sm:flex-row items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 flex items-center justify-center text-emerald-600 shrink-0">
                    <ShieldCheck className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-foreground">
                      Razorpay Verified Merchant &amp; 7-Day Money-Back Guarantee
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      All online payments are securely processed via Razorpay with 128-bit encryption. If
                      SriLekh does not meet your business needs within 7 days, get a 100% refund.
                    </p>
                  </div>
                </div>
                <Link
                  href="/refund-policy"
                  className="shrink-0 text-xs font-semibold text-primary hover:underline inline-flex items-center gap-1"
                >
                  <span>Read Refund Policy</span>
                  <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
            </div>
          </section>

          {/* C. Complete Feature Comparison Matrix */}
          <section className="py-16 sm:py-24 border-b border-border/60">
            <div className="max-w-6xl mx-auto px-6 space-y-10">
              <div className="max-w-2xl space-y-2">
                <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
                  Compare SriLekh Plans Side-by-Side
                </h2>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Detailed module-by-module breakdown across all four subscription tiers.
                </p>
              </div>

              <div className="overflow-x-auto rounded-2xl border border-border bg-card shadow-xs">
                <table className="w-full text-left border-collapse min-w-[720px]">
                  <thead>
                    <tr className="border-b border-border bg-muted/40 text-xs font-bold text-foreground">
                      <th className="p-4 w-1/3">Feature / Module</th>
                      <th className="p-4 text-center">Starter<br /><span className="text-[11px] font-normal text-muted-foreground">₹599/yr</span></th>
                      <th className="p-4 text-center">Growth<br /><span className="text-[11px] font-normal text-muted-foreground">₹1,499/yr</span></th>
                      <th className="p-4 text-center bg-[#162C5B]/5 dark:bg-[#E28123]/5">Pro AI<br /><span className="text-[11px] font-bold text-primary">₹2,599/yr</span></th>
                      <th className="p-4 text-center">Enterprise<br /><span className="text-[11px] font-normal text-muted-foreground">₹3,999/yr</span></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60 text-xs">
                    {matrixComparisonRows.map((cat, catIdx) => (
                      <React.Fragment key={catIdx}>
                        <tr className="bg-muted/60 font-bold text-foreground">
                          <td colSpan={5} className="py-2.5 px-4 text-[11px] uppercase tracking-wider text-primary">
                            {cat.category}
                          </td>
                        </tr>
                        {cat.items.map((item, itemIdx) => (
                          <tr key={itemIdx} className="hover:bg-muted/20 transition-colors">
                            <td className="p-3.5 text-foreground font-medium">{item.name}</td>
                            <td className="p-3.5 text-center">{renderCell(item.starter)}</td>
                            <td className="p-3.5 text-center">{renderCell(item.growth)}</td>
                            <td className="p-3.5 text-center bg-[#162C5B]/5 dark:bg-[#E28123]/5 font-semibold">
                              {renderCell(item.pro)}
                            </td>
                            <td className="p-3.5 text-center">{renderCell(item.enterprise)}</td>
                          </tr>
                        ))}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          {/* D. FAQ Section */}
          <section className="py-16 sm:py-20 border-b border-border/60 bg-slate-50/50 dark:bg-card/20">
            <div className="max-w-4xl mx-auto px-6 space-y-8">
              <div className="space-y-2">
                <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
                  Frequently Asked Questions
                </h2>
                <p className="text-sm text-muted-foreground">
                  Clear answers regarding billing, Razorpay payments, refunds, and plan features.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {faqs.map((faq) => (
                  <div
                    key={faq.question}
                    className="rounded-2xl border border-border bg-card p-6 space-y-2"
                  >
                    <h3 className="text-sm font-bold text-foreground flex items-start gap-2">
                      <HelpCircle className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                      <span>{faq.question}</span>
                    </h3>
                    <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed pl-6">
                      {faq.answer}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* E. CTA Section */}
          <section className="py-16 sm:py-24">
            <div className="max-w-4xl mx-auto px-6 text-center space-y-6">
              <h2 className="text-2xl sm:text-4xl font-black tracking-tight text-foreground">
                Start managing your business books today.
              </h2>
              <p className="text-sm text-muted-foreground max-w-xl mx-auto">
                Join thousands of Indian businesses modernizing their double-entry accounting,
                inventory, and GST compliance with SriLekh.
              </p>
              <div className="flex items-center justify-center gap-3 flex-wrap">
                <Link
                  href="/register"
                  className="px-6 py-3 bg-[#162C5B] hover:bg-[#0F1E3D] dark:bg-[#E28123] dark:hover:bg-[#c86815] text-white dark:text-slate-950 rounded-xl text-sm font-bold shadow-md transition-all inline-flex items-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span>Create Account</span>
                  <ArrowRight className="w-4 h-4" />
                </Link>
                <Link
                  href="/contact"
                  className="px-6 py-3 bg-card hover:bg-muted border border-border rounded-xl text-sm font-semibold text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Contact Sales &amp; Support
                </Link>
              </div>
              <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground pt-4">
                <Link href="/terms" className="hover:text-foreground underline-offset-4 hover:underline">
                  Terms &amp; Conditions
                </Link>
                <span aria-hidden="true">·</span>
                <Link href="/privacy-policy" className="hover:text-foreground underline-offset-4 hover:underline">
                  Privacy Policy
                </Link>
                <span aria-hidden="true">·</span>
                <Link href="/refund-policy" className="hover:text-foreground underline-offset-4 hover:underline">
                  Refund Policy (7-Day Guarantee)
                </Link>
              </div>
            </div>
          </section>
        </main>

        <PublicFooter />
      </div>
    </NativeCommercialGuard>
  );
}

function renderCell(val: boolean | string) {
  if (typeof val === "boolean") {
    return val ? (
      <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 mx-auto" />
    ) : (
      <Minus className="w-4 h-4 text-muted-foreground/40 mx-auto" />
    );
  }
  return <span className="font-semibold text-foreground">{val}</span>;
}
