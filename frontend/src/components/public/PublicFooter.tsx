"use client";

import React from "react";
import { useIsNativeApp } from "@/hooks/useIsNativeApp";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { VouchLogo } from "@/components/VouchLogo";
import { SRILEKH_PUBLIC } from "./public-constants";
import { ShortcutsHelpButton } from "./ShortcutsHelpButton";

const footerLinkClass =
  "hover:text-foreground transition-colors inline-flex items-center gap-1 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function PublicFooter() {
  const currentYear = new Date().getFullYear();
  const isNative = useIsNativeApp();

  return (
    <footer className="border-t border-border/60 bg-slate-50 dark:bg-zinc-950 py-12 text-xs text-muted-foreground">
      <div className="max-w-7xl mx-auto px-6 grid grid-cols-2 md:grid-cols-5 gap-8 mb-8">
        <div className="space-y-3 col-span-2 md:col-span-1">
          <Link
            href="/"
            className="inline-flex rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <VouchLogo size={24} showWordmark={true} />
          </Link>
          <p className="text-xs text-muted-foreground leading-relaxed max-w-[240px]">
            {SRILEKH_PUBLIC.tagline}
          </p>
        </div>

        <div className="space-y-3">
          <div className="text-xs font-bold uppercase tracking-wider text-foreground">
            Product
          </div>
          <ul className="space-y-2 text-muted-foreground">
            <li>
              <Link href="/dashboard" className={footerLinkClass}>
                <ChevronRight className="w-3 h-3 shrink-0" />
                <span>Dashboard</span>
              </Link>
            </li>
            <li>
              <Link href="/sales" className={footerLinkClass}>
                <ChevronRight className="w-3 h-3 shrink-0" />
                <span>Sales Invoicing (F8)</span>
              </Link>
            </li>
            <li>
              <Link href="/purchases" className={footerLinkClass}>
                <ChevronRight className="w-3 h-3 shrink-0" />
                <span>AI Bill Scanner (F9)</span>
              </Link>
            </li>
            <li>
              <Link href="/vouchers" className={footerLinkClass}>
                <ChevronRight className="w-3 h-3 shrink-0" />
                <span>Payments &amp; Receipts</span>
              </Link>
            </li>
            {!isNative && (
              <li>
                <Link href="/pricing" className={footerLinkClass}>
                  <ChevronRight className="w-3 h-3 shrink-0" />
                  <span>Pricing</span>
                </Link>
              </li>
            )}
          </ul>
        </div>

        <div className="space-y-3">
          <div className="text-xs font-bold uppercase tracking-wider text-foreground">
            Resources
          </div>
          <ul className="space-y-2 text-muted-foreground">
            <li>
              <ShortcutsHelpButton />
            </li>
            <li>
              <Link href="/dashboard" className={footerLinkClass}>
                <ChevronRight className="w-3 h-3 shrink-0" />
                <span>Documentation</span>
              </Link>
            </li>
            <li>
              <Link href="/dashboard" className={footerLinkClass}>
                <ChevronRight className="w-3 h-3 shrink-0" />
                <span>GST Compliance Guide</span>
              </Link>
            </li>
            <li>
              <Link href="/~offline" className={footerLinkClass}>
                <ChevronRight className="w-3 h-3 shrink-0" />
                <span>Offline Support (PWA)</span>
              </Link>
            </li>
          </ul>
        </div>

        <div className="space-y-3">
          <div className="text-xs font-bold uppercase tracking-wider text-foreground">
            Company
          </div>
          <ul className="space-y-2 text-muted-foreground">
            <li>
              <Link href="/contact" className={footerLinkClass}>
                <ChevronRight className="w-3 h-3 shrink-0" />
                <span>Contact</span>
              </Link>
            </li>
            <li>
              <a
                href={`mailto:${SRILEKH_PUBLIC.supportEmail}`}
                className={footerLinkClass}
              >
                <ChevronRight className="w-3 h-3 shrink-0" />
                <span>{SRILEKH_PUBLIC.supportEmail}</span>
              </a>
            </li>
          </ul>
        </div>

        <div className="space-y-3">
          <div className="text-xs font-bold uppercase tracking-wider text-foreground">
            Legal
          </div>
          <ul className="space-y-2 text-muted-foreground">
            <li>
              <Link href="/privacy-policy" className={footerLinkClass}>
                <ChevronRight className="w-3 h-3 shrink-0" />
                <span>Privacy Policy</span>
              </Link>
            </li>
            <li>
              <Link href="/terms" className={footerLinkClass}>
                <ChevronRight className="w-3 h-3 shrink-0" />
                <span>Terms &amp; Conditions</span>
              </Link>
            </li>
            {!isNative && (
              <li>
                <Link href="/refund-policy" className={footerLinkClass}>
                  <ChevronRight className="w-3 h-3 shrink-0" />
                  <span>Refund Policy</span>
                </Link>
              </li>
            )}
            <li>
              <Link href="/delete-account" className={footerLinkClass}>
                <ChevronRight className="w-3 h-3 shrink-0" />
                <span>Delete Account</span>
              </Link>
            </li>
          </ul>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 pt-6 border-t border-border/60 dark:border-border flex flex-col sm:flex-row items-center justify-between gap-4 text-[11px] text-muted-foreground">
        <div>
          © {currentYear} {SRILEKH_PUBLIC.businessLabel}. Built for Modern Indian Businesses.
        </div>
        <div className="flex items-center gap-3 font-mono text-[10px]">
          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 rounded border border-emerald-500/15">
            PWA Enabled
          </span>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-500/10 text-blue-700 dark:text-blue-400 rounded border border-blue-500/15">
            Desktop &amp; Mobile
          </span>
        </div>
      </div>
    </footer>
  );
}
