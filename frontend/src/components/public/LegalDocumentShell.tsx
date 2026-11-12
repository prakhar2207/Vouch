import React from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, FileText } from "lucide-react";
import { PublicHeader } from "./PublicHeader";
import { PublicFooter } from "./PublicFooter";

export interface LegalSectionLink {
  id: string;
  title: string;
}

interface LegalDocumentShellProps {
  activePath: "/privacy-policy" | "/terms" | "/refund-policy";
  badge: string;
  title: string;
  subtitle: string;
  reviewNotice: string;
  sections: LegalSectionLink[];
  children: React.ReactNode;
}

export function LegalDocumentShell({
  activePath,
  badge,
  title,
  subtitle,
  reviewNotice,
  sections,
  children,
}: LegalDocumentShellProps) {
  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col selection:bg-[#162C5B]/15 selection:text-[#162C5B]">
      <PublicHeader activePath={activePath} />

      <main className="flex-1">
        {/* Hero */}
        <section className="border-b border-border/60 bg-slate-50/70 dark:bg-card/30 py-12 sm:py-16">
          <div className="max-w-5xl mx-auto px-6 space-y-5">
            <div>
              <Link
                href="/"
                className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Back to Home</span>
              </Link>
            </div>

            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#162C5B]/10 dark:bg-[#E28123]/15 border border-[#162C5B]/20 dark:border-[#E28123]/30 text-[#162C5B] dark:text-[#FBA94C] text-xs font-semibold">
              <FileText className="w-3.5 h-3.5" />
              <span>{badge}</span>
            </div>

            <h1 className="text-3xl sm:text-4xl font-black tracking-tight text-foreground">
              {title}
            </h1>
            <p className="text-sm sm:text-base text-muted-foreground max-w-3xl leading-relaxed">
              {subtitle}
            </p>

            <div
              role="note"
              className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs sm:text-sm text-amber-900 dark:text-amber-200 flex items-start gap-2.5 max-w-3xl"
            >
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
              <div>
                <span className="font-semibold">Owner &amp; Legal Review Notice: </span>
                <span>{reviewNotice}</span>
              </div>
            </div>
          </div>
        </section>

        {/* Body + Table of Contents */}
        <section className="py-12 sm:py-16">
          <div className="max-w-5xl mx-auto px-6 grid grid-cols-1 lg:grid-cols-12 gap-10">
            <aside className="lg:col-span-4">
              <div className="lg:sticky lg:top-24 rounded-2xl border border-border bg-card p-5 space-y-4">
                <h2 className="text-xs font-bold uppercase tracking-wider text-foreground">
                  In This Document
                </h2>
                <nav aria-label="Document sections">
                  <ol className="space-y-1.5 text-xs text-muted-foreground">
                    {sections.map((sec) => (
                      <li key={sec.id}>
                        <a
                          href={`#${sec.id}`}
                          className="block py-1 hover:text-foreground transition-colors rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          {sec.title}
                        </a>
                      </li>
                    ))}
                  </ol>
                </nav>

                <div className="pt-4 border-t border-border space-y-2 text-xs">
                  <div className="font-semibold text-foreground">Related Pages</div>
                  <div className="flex flex-col gap-1.5 text-muted-foreground">
                    <Link href="/privacy-policy" className="hover:text-foreground transition-colors">
                      Privacy Policy
                    </Link>
                    <Link href="/terms" className="hover:text-foreground transition-colors">
                      Terms &amp; Conditions
                    </Link>
                    <Link href="/refund-policy" className="hover:text-foreground transition-colors">
                      Refund Policy
                    </Link>
                    <Link href="/pricing" className="hover:text-foreground transition-colors">
                      Pricing
                    </Link>
                    <Link href="/contact" className="hover:text-foreground transition-colors">
                      Contact Support
                    </Link>
                  </div>
                </div>
              </div>
            </aside>

            <article className="lg:col-span-8 space-y-8 text-sm leading-relaxed text-foreground/90">
              {children}
            </article>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
