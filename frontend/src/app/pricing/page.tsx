import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Building2,
  CheckCircle2,
  FileCheck,
  Landmark,
  Layers,
  Package,
  Receipt,
  Scale,
  WifiOff,
} from "lucide-react";
import { PublicHeader } from "@/components/public/PublicHeader";
import { PublicFooter } from "@/components/public/PublicFooter";
import { NativeCommercialGuard } from "@/components/public/NativeCommercialGuard";
import { PricingView } from "@/components/public/PricingView";
import { SRILEKH_PUBLIC } from "@/components/public/public-constants";

export const metadata: Metadata = {
  title: {
    absolute: "SriLekh Pricing | Accounting Software & GST Billing for Indian Businesses",
  },
  description:
    "Transparent annual pricing for SriLekh ERP. Micro-retailers to large distributors get unlimited double-entry accounting, GST invoicing, and tiered AI OCR & business intelligence.",
  alternates: {
    canonical: "/pricing",
  },
};

const verifiedCapabilities = [
  {
    icon: Receipt,
    title: "Sales & Purchase Management",
    detail:
      "Keyboard-fast sales invoicing (F8), purchase bill entry (F9), proforma quotations, credit notes, and AI-assisted bill scanning from uploaded PDFs or images.",
    status: "Available in platform",
  },
  {
    icon: Scale,
    title: "Double-Entry Accounting",
    detail:
      "Structured voucher system across Sales, Purchase, Receipt, Payment, Contra, Journal, and Credit/Debit Note entries with automatic debit-credit equilibrium checks.",
    status: "Available in platform",
  },
  {
    icon: Landmark,
    title: "Payment & Receipt Management",
    detail:
      "Track party receipts, supplier payments, invoice-level payment allocations, and pending receivables or payables across accounting periods.",
    status: "Available in platform",
  },
  {
    icon: Package,
    title: "Inventory & Stock Tracking",
    detail:
      "Manage godowns, product categories, HSN codes, unit & multi-tier pricing, and valuation methods (Average Cost, FIFO, LIFO, Standard).",
    status: "Core stock active",
  },
  {
    icon: FileCheck,
    title: "GST Calculations & Reporting",
    detail:
      "Automatic CGST, SGST, and IGST computation from state codes, GSTIN checksum validation, GSTR-1/3B/9 summary preparation, and GSTR-2B reconciliation.",
    status: "Reports & tax math active",
  },
  {
    icon: BarChart3,
    title: "Financial Reports",
    detail:
      "Generate Trial Balance, Profit & Loss Statement, Balance Sheet, Party Aging, and detailed Ledger Statements, plus Tally XML data export.",
    status: "Available in platform",
  },
  {
    icon: Layers,
    title: "Bank Reconciliation",
    detail:
      "Upload CSV, Excel (.xlsx/.xls), PDF, OFX, or QIF bank statements and match transactions against business parties, receipts, payments, and contra transfers.",
    status: "Statement upload active",
  },
  {
    icon: WifiOff,
    title: "Offline Capabilities (PWA)",
    detail:
      "Progressive Web App backed by local IndexedDB storage so sales/purchase billing and customer khata remain accessible offline with automatic cloud sync.",
    status: "Offline billing & auto-sync active",
  },
  {
    icon: Building2,
    title: "Business & Party Management",
    detail:
      "Manage multiple companies under one login with role-based permissions (Owner, Admin, CA, Employee, Viewer), customer/supplier masters, and B2B invoice inbox.",
    status: "Available in platform",
  },
];

const faqs = [
  {
    question: "What is SriLekh's pricing model?",
    answer:
      "SriLekh commoditizes core accounting and monetizes AI automation. All essential double-entry bookkeeping, GST invoicing, inventory, and banking features are completely unlocked across all tiers. Tiers differ by daily AI OCR scanning volume and business intelligence analytics depth.",
  },
  {
    question: "Are prices inclusive of GST?",
    answer:
      "Prices are listed as base annual subscriptions. Applicable 18% Goods and Services Tax (GST) is calculated and added during Razorpay checkout, and an official computer-generated GST tax invoice is issued for your records.",
  },
  {
    question: "Can I pay using UPI or Credit/Debit Cards?",
    answer:
      "Yes. Razorpay supports all major Indian payment methods including UPI (Google Pay, PhonePe, Paytm, BHIM), RuPay/Visa/Mastercard credit and debit cards, NetBanking, and corporate wallets.",
  },
  {
    question: "What happens if I exceed my daily OCR scan limit?",
    answer:
      "Your core accounting and manual bill entry continue uninterrupted. Your daily scan quota resets every night at midnight. You can also upgrade your plan at any time to immediately receive higher scan capacity.",
  },
  {
    question: "Can I cancel my subscription?",
    answer:
      "Yes. You can cancel your subscription anytime from the Settings > Billing dashboard. Your plan benefits and account access remain fully active until the end of your prepaid annual billing period.",
  },
  {
    question: "Will my financial records be deleted if my subscription expires?",
    answer:
      "Never. Your historical vouchers, ledgers, balance sheets, and uploaded bills remain securely preserved and accessible for audits and export, even if you choose not to renew.",
  },
];

export default function PricingPage() {
  return (
    <NativeCommercialGuard>
      <div className="min-h-screen bg-background text-foreground flex flex-col selection:bg-[#162C5B]/15 selection:text-[#162C5B]">
        <PublicHeader activePath="/pricing" />

        <main className="flex-1">
          {/* A. Live Interactive Pricing & Razorpay Checkout */}
          <PricingView />

          {/* B. Verified Capabilities Comparison */}
          <section className="py-16 sm:py-20 border-t border-border/60">
            <div className="max-w-6xl mx-auto px-6 space-y-10">
              <div className="max-w-2xl space-y-2">
                <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
                  Platform Capabilities Included in SriLekh
                </h2>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Below is an accurate overview of the accounting, GST, inventory, and reconciliation
                  modules implemented in the SriLekh application.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {verifiedCapabilities.map((item) => {
                  const Icon = item.icon;
                  return (
                    <div
                      key={item.title}
                      className="rounded-2xl border border-border bg-card p-6 flex flex-col justify-between gap-4 hover:border-border/80 transition-colors"
                    >
                      <div className="space-y-3">
                        <div className="w-10 h-10 rounded-xl bg-[#162C5B]/10 dark:bg-[#E28123]/15 flex items-center justify-center text-[#162C5B] dark:text-[#FBA94C]">
                          <Icon className="w-5 h-5" />
                        </div>
                        <h3 className="text-base font-bold text-foreground">{item.title}</h3>
                        <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed">
                          {item.detail}
                        </p>
                      </div>

                      <div className="pt-3 border-t border-border/60 flex items-center gap-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-400">
                        <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                        <span>{item.status}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>

          {/* C. FAQ */}
          <section className="py-16 sm:py-20 border-t border-border/60 bg-slate-50/60 dark:bg-card/20">
            <div className="max-w-4xl mx-auto px-6 space-y-8">
              <div className="space-y-2">
                <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
                  Frequently Asked Questions
                </h2>
                <p className="text-sm text-muted-foreground">
                  Common questions from Indian MSMEs and accounting teams evaluating SriLekh.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {faqs.map((faq) => (
                  <div
                    key={faq.question}
                    className="rounded-2xl border border-border bg-card p-6 space-y-2"
                  >
                    <h3 className="text-sm font-bold text-foreground">{faq.question}</h3>
                    <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed">
                      {faq.answer}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* D. CTA */}
          <section className="py-16 sm:py-20 border-t border-border/60">
            <div className="max-w-4xl mx-auto px-6 text-center space-y-6">
              <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
                Ready to set up your business books?
              </h2>
              <p className="text-sm text-muted-foreground max-w-xl mx-auto">
                Create your company workspace or contact our support team to discuss onboarding and
                migration from Tally or spreadsheets.
              </p>
              <div className="flex items-center justify-center gap-3 flex-wrap">
                <Link
                  href="/register"
                  className="px-6 py-3 bg-[#162C5B] hover:bg-[#0F1E3D] dark:bg-[#E28123] dark:hover:bg-[#c86815] text-white rounded-xl text-sm font-bold shadow-md transition-all inline-flex items-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span>Create Free Account</span>
                  <ArrowRight className="w-4 h-4" />
                </Link>
                <Link
                  href="/contact"
                  className="px-6 py-3 bg-card hover:bg-muted border border-border rounded-xl text-sm font-semibold text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Contact Support
                </Link>
              </div>
              <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground pt-2">
                <Link href="/terms" className="hover:text-foreground underline-offset-4 hover:underline">
                  Terms &amp; Conditions
                </Link>
                <span aria-hidden="true">·</span>
                <Link href="/privacy-policy" className="hover:text-foreground underline-offset-4 hover:underline">
                  Privacy Policy
                </Link>
                <span aria-hidden="true">·</span>
                <Link href="/refund-policy" className="hover:text-foreground underline-offset-4 hover:underline">
                  Refund Policy
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
