import type { Metadata } from "next";
import Link from "next/link";
import { AlertCircle, Building2, Clock, Mail, MapPin, Phone } from "lucide-react";
import { PublicHeader } from "@/components/public/PublicHeader";
import { PublicFooter } from "@/components/public/PublicFooter";
import { ContactForm } from "@/components/public/ContactForm";
import { SRILEKH_PUBLIC } from "@/components/public/public-constants";

export const metadata: Metadata = {
  title: {
    absolute: "Contact SriLekh | Business Support",
  },
  description:
    "Contact the SriLekh team for business onboarding, pricing inquiries, GST workflow support, and account assistance.",
  alternates: {
    canonical: "/contact",
  },
};

export default function ContactPage() {
  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col selection:bg-[#162C5B]/15 selection:text-[#162C5B]">
      <PublicHeader activePath="/contact" />

      <main className="flex-1">
        {/* A. Hero */}
        <section className="border-b border-border/60 bg-slate-50/70 dark:bg-card/30 py-14 sm:py-18">
          <div className="max-w-5xl mx-auto px-6 space-y-4">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#162C5B]/10 dark:bg-[#E28123]/15 border border-[#162C5B]/20 dark:border-[#E28123]/30 text-[#162C5B] dark:text-[#FBA94C] text-xs font-semibold">
              <Mail className="w-3.5 h-3.5" />
              <span>Support &amp; Business Inquiries</span>
            </div>

            <h1 className="text-3xl sm:text-4xl font-black tracking-tight text-foreground">
              We&apos;re here to help your business.
            </h1>

            <p className="text-sm sm:text-base text-muted-foreground max-w-2xl leading-relaxed">
              Reach out to SriLekh for account onboarding, Tally migration help, technical
              questions, or commercial pricing inquiries.
            </p>
          </div>
        </section>

        {/* B & C. Contact Details + Inquiry Form */}
        <section className="py-12 sm:py-16">
          <div className="max-w-5xl mx-auto px-6 grid grid-cols-1 lg:grid-cols-12 gap-8">
            {/* Contact Information */}
            <div className="lg:col-span-5 space-y-5">
              <div className="rounded-2xl border border-border bg-card p-6 space-y-5 shadow-sm">
                <h2 className="text-base font-extrabold text-foreground">
                  Official Contact Details
                </h2>

                <div className="space-y-4 text-xs sm:text-sm">
                  <div className="flex items-start gap-3">
                    <Mail className="w-4 h-4 shrink-0 mt-0.5 text-[#162C5B] dark:text-[#FBA94C]" />
                    <div className="space-y-0.5">
                      <div className="font-semibold text-foreground">Official Support Email</div>
                      <a
                        href={`mailto:${SRILEKH_PUBLIC.supportEmail}`}
                        className="text-primary hover:underline font-medium break-all"
                      >
                        {SRILEKH_PUBLIC.supportEmail}
                      </a>
                    </div>
                  </div>

                  <div className="flex items-start gap-3">
                    <Building2 className="w-4 h-4 shrink-0 mt-0.5 text-[#162C5B] dark:text-[#FBA94C]" />
                    <div className="space-y-0.5">
                      <div className="font-semibold text-foreground">Platform &amp; Legal Entity</div>
                      <div className="text-muted-foreground">{SRILEKH_PUBLIC.businessLabel}</div>
                      <div className="text-xs text-amber-700 dark:text-amber-300">
                        Registered legal entity name: [Pending Owner Confirmation]
                      </div>
                    </div>
                  </div>

                  <div className="flex items-start gap-3">
                    <Phone className="w-4 h-4 shrink-0 mt-0.5 text-muted-foreground" />
                    <div className="space-y-0.5">
                      <div className="font-semibold text-foreground">Support Phone</div>
                      <div className="text-xs text-amber-700 dark:text-amber-300">
                        [Pending Owner Confirmation — publish verified business phone before payment
                        gateway KYC submission]
                      </div>
                    </div>
                  </div>

                  <div className="flex items-start gap-3">
                    <MapPin className="w-4 h-4 shrink-0 mt-0.5 text-muted-foreground" />
                    <div className="space-y-0.5">
                      <div className="font-semibold text-foreground">Registered Business Address</div>
                      <div className="text-xs text-amber-700 dark:text-amber-300">
                        [Pending Owner Confirmation — add physical office address matching KYC
                        documents]
                      </div>
                    </div>
                  </div>

                  <div className="flex items-start gap-3">
                    <Clock className="w-4 h-4 shrink-0 mt-0.5 text-muted-foreground" />
                    <div className="space-y-0.5">
                      <div className="font-semibold text-foreground">Support Availability</div>
                      <div className="text-xs text-amber-700 dark:text-amber-300">
                        [Pending Owner Confirmation — specify official business support hours]
                      </div>
                    </div>
                  </div>
                </div>

                <div
                  role="note"
                  className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-900 dark:text-amber-200 flex items-start gap-2"
                >
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
                  <span>
                    Unavailable business fields above are intentionally marked pending owner
                    confirmation rather than guessed.
                  </span>
                </div>
              </div>

              <div className="rounded-2xl border border-border bg-card p-6 space-y-3 text-xs text-muted-foreground">
                <div className="font-bold text-foreground uppercase tracking-wider">
                  Quick Links
                </div>
                <div className="flex flex-col gap-2">
                  <Link href="/pricing" className="hover:text-foreground transition-colors">
                    → Pricing &amp; Platform Capabilities
                  </Link>
                  <Link href="/privacy-policy" className="hover:text-foreground transition-colors">
                    → Privacy Policy
                  </Link>
                  <Link href="/terms" className="hover:text-foreground transition-colors">
                    → Terms &amp; Conditions
                  </Link>
                  <Link href="/refund-policy" className="hover:text-foreground transition-colors">
                    → Refund Policy
                  </Link>
                </div>
              </div>
            </div>

            {/* Contact Form */}
            <div className="lg:col-span-7">
              <ContactForm />
            </div>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
