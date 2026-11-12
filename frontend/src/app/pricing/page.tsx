import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Building2,
  CheckCircle2,
  Clock,
  FileCheck,
  Landmark,
  Layers,
  Mail,
  Package,
  Receipt,
  Scale,
  WifiOff,
} from "lucide-react";
import { PublicHeader } from "@/components/public/PublicHeader";
import { PublicFooter } from "@/components/public/PublicFooter";
import { NativeCommercialGuard } from "@/components/public/NativeCommercialGuard";
import { SRILEKH_PUBLIC } from "@/components/public/public-constants";

export const metadata: Metadata = {
  title: {
    absolute: "SriLekh Pricing | Accounting Software for Indian Businesses",
  },
  description:
    "Explore SriLekh accounting software capabilities for Indian MSMEs, retailers, wholesalers, and small businesses. Contact our team for current pricing and onboarding.",
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
      "Manage warehouses (godowns), product categories, HSN codes, unit & multi-tier pricing, and valuation methods (Average Cost, FIFO, LIFO, Standard). Batch/serial and alternate-unit fields are configurable at item setup (per-batch lot deduction during invoicing is not yet active).",
    status: "Core stock active; batch/unit conversion partial",
  },
  {
    icon: FileCheck,
    title: "GST Calculations & Reporting",
    detail:
      "Automatic CGST, SGST, and IGST computation from state codes, GSTIN checksum validation, GSTR-1/3B/9 summary preparation, and GSTR-2B upload reconciliation. E-Way Bill and portal upload tools currently operate in sandbox mode; live government return filing and IRN generation are not enabled.",
    status: "Reports & tax math active (sandbox portal)",
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
      "Upload CSV, Excel (.xlsx/.xls), PDF, OFX, or QIF bank statements and match transactions against business parties, receipts, payments, and refunds from the banking cockpit.",
    status: "Statement upload active (no live bank feed)",
  },
  {
    icon: WifiOff,
    title: "Offline Capabilities (PWA)",
    detail:
      "Installable Progressive Web App backed by local IndexedDB storage so supported sales/purchase invoice drafting and cached records remain accessible offline; payments, journals, banking, and live reports require connectivity.",
    status: "Supported invoice drafting & read caches",
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
    question: "What is SriLekh?",
    answer:
      "SriLekh is a web and installable PWA accounting, GST billing, and inventory management application designed for Indian MSMEs, traders, wholesalers, and small businesses.",
  },
  {
    question: "Who can use SriLekh?",
    answer:
      "Retailers, wholesalers, distributors, manufacturers, service businesses, and Chartered Accountants collaborating with client teams can use SriLekh with role-based permissions.",
  },
  {
    question: "Does SriLekh support GST accounting?",
    answer:
      "Yes. SriLekh calculates intra-state CGST/SGST and inter-state IGST automatically from state codes, validates GSTIN formats, prepares GSTR-1/3B/9 summaries, and supports GSTR-2B upload reconciliation. Live government GSTN return filing and official IRN/E-Way generation are not yet enabled in production.",
  },
  {
    question: "Can I manage inventory?",
    answer:
      "Yes. You can organize items by category and HSN code, track stock movements and valuation across warehouses, and store alternate-unit or batch/serial metadata on item setup (full per-batch lot deduction during sales invoicing is not yet active).",
  },
  {
    question: "Can I access my business records from multiple devices?",
    answer:
      "Yes. Your company books are stored on our cloud backend so authorized team members can sign in from supported desktop or mobile browsers, with local IndexedDB caching for offline continuity.",
  },
  {
    question: "How can I get pricing information?",
    answer:
      "Commercial subscription tiers and billing plans are currently being finalized. Please contact us through the Contact page or email support@srilekh.com for current onboarding and pricing details.",
  },
];

export default function PricingPage() {
  return (
    <NativeCommercialGuard>
    <div className="min-h-screen bg-background text-foreground flex flex-col selection:bg-[#162C5B]/15 selection:text-[#162C5B]">
      <PublicHeader activePath="/pricing" />

      <main className="flex-1">
        {/* A. Hero */}
        <section className="relative overflow-hidden border-b border-border/60 py-16 sm:py-20">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[720px] h-[320px] bg-gradient-to-b from-[#162C5B]/8 via-[#E28123]/5 to-transparent blur-3xl pointer-events-none rounded-full" />

          <div className="max-w-5xl mx-auto px-6 text-center space-y-6 relative z-10">
            <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#E28123]/10 dark:bg-[#E28123]/15 border border-[#E28123]/25 text-[#C86815] dark:text-[#FBA94C] text-xs font-semibold">
              <Clock className="w-3.5 h-3.5 text-[#E28123]" />
              <span>Pricing Plans Being Finalized</span>
            </div>

            <h1 className="text-3xl sm:text-5xl font-black tracking-tight text-balance">
              Simple, transparent accounting software pricing.
            </h1>

            <p className="text-sm sm:text-base text-muted-foreground max-w-2xl mx-auto leading-relaxed">
              SriLekh helps Indian MSMEs, retailers, wholesalers, and small business owners manage
              double-entry accounting, inventory, GST compliance, and financial records in one
              organized workspace.
            </p>

            <div className="flex items-center justify-center gap-3 flex-wrap pt-2">
              <Link
                href="/register"
                className="px-6 py-3 bg-[#162C5B] hover:bg-[#0F1E3D] dark:bg-[#E28123] dark:hover:bg-[#c86815] text-white rounded-xl text-sm font-bold shadow-md shadow-[#162C5B]/20 dark:shadow-[#E28123]/20 transition-all inline-flex items-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span>Get Started</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                href="/contact"
                className="px-6 py-3 bg-card hover:bg-muted border border-border rounded-xl text-sm font-semibold text-foreground transition-colors inline-flex items-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Mail className="w-4 h-4 text-muted-foreground" />
                <span>Contact Sales</span>
              </Link>
            </div>
          </div>
        </section>

        {/* B. Honest Pricing Status Card */}
        <section className="py-14 sm:py-16 border-b border-border/60 bg-slate-50/60 dark:bg-card/20">
          <div className="max-w-4xl mx-auto px-6">
            <div className="rounded-2xl border border-border bg-card p-6 sm:p-10 shadow-sm space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-6">
                <div className="space-y-1.5">
                  <span className="inline-block px-2.5 py-0.5 rounded-md bg-amber-500/10 border border-amber-500/25 text-amber-700 dark:text-amber-300 text-xs font-semibold">
                    Pricing Coming Soon
                  </span>
                  <h2 className="text-2xl font-extrabold text-foreground">
                    Contact Us for Pricing
                  </h2>
                </div>
                <Link
                  href="/contact"
                  className="shrink-0 px-5 py-2.5 bg-[#162C5B] hover:bg-[#0F1E3D] dark:bg-[#E28123] dark:hover:bg-[#c86815] text-white rounded-xl text-xs font-bold transition-colors inline-flex items-center justify-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span>Request Pricing Details</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>

              <div className="space-y-3 text-sm text-muted-foreground leading-relaxed">
                <p>
                  Official subscription plans, rupee pricing tiers, billing intervals, and trial or
                  entitlement terms have <strong className="text-foreground">not yet been published</strong>{" "}
                  for {SRILEKH_PUBLIC.brandName}.
                </p>
                <p>
                  Online self-serve subscription checkout is not yet active on the website. To avoid
                  misleading commercial commitments, no automated billing tiers or promotional
                  trials are listed here until finalized by the business owner.
                </p>
                <p>
                  For onboarding inquiries or commercial pricing discussions, please reach out via
                  our{" "}
                  <Link href="/contact" className="text-primary font-semibold hover:underline">
                    Contact page
                  </Link>{" "}
                  or email{" "}
                  <a
                    href={`mailto:${SRILEKH_PUBLIC.supportEmail}`}
                    className="text-primary font-semibold hover:underline"
                  >
                    {SRILEKH_PUBLIC.supportEmail}
                  </a>
                  .
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* C. Verified Capabilities Comparison */}
        <section className="py-16 sm:py-20 border-b border-border/60">
          <div className="max-w-6xl mx-auto px-6 space-y-10">
            <div className="max-w-2xl space-y-2">
              <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
                Platform Capabilities Included in SriLekh
              </h2>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Below is an accurate overview of the accounting, GST, inventory, and reconciliation
                modules currently implemented in the SriLekh application.
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

        {/* D. FAQ */}
        <section className="py-16 sm:py-20 border-b border-border/60 bg-slate-50/60 dark:bg-card/20">
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

        {/* E. CTA */}
        <section className="py-16 sm:py-20">
          <div className="max-w-4xl mx-auto px-6 text-center space-y-6">
            <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
              Ready to set up your business books?
            </h2>
            <p className="text-sm text-muted-foreground max-w-xl mx-auto">
              Create your company workspace or contact our support team to discuss pricing and
              migration from Tally or spreadsheets.
            </p>
            <div className="flex items-center justify-center gap-3 flex-wrap">
              <Link
                href="/register"
                className="px-6 py-3 bg-[#162C5B] hover:bg-[#0F1E3D] dark:bg-[#E28123] dark:hover:bg-[#c86815] text-white rounded-xl text-sm font-bold shadow-md transition-all inline-flex items-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span>Create Account</span>
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
