"use client";

import React from "react";
import Link from "next/link";
import { ShieldCheck, ArrowLeft } from "lucide-react";
import { useIsNativeApp } from "@/hooks/useIsNativeApp";

/**
 * Enforces Google Play's initial free/companion commercial rules inside the
 * native Android container without altering public website pages for browsers.
 */
export function NativeCommercialGuard({ children }: { children: React.ReactNode }) {
  const isNative = useIsNativeApp();

  if (isNative) {
    return (
      <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-6">
        <div className="max-w-md w-full rounded-2xl border border-border bg-card p-6 space-y-4 text-center shadow-lg">
          <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary mx-auto flex items-center justify-center">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <h1 className="text-lg font-extrabold text-foreground">
            SriLekh Workspace Access
          </h1>
          <p className="text-xs text-muted-foreground leading-relaxed">
            This Android app provides direct workspace access for authorized SriLekh business accounts.
            Subscription plans and billing checkout are not displayed inside the mobile application.
          </p>
          <div className="flex flex-col sm:flex-row gap-2 justify-center pt-2">
            <Link
              href="/dashboard"
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Go to Workspace</span>
            </Link>
            <Link
              href="/privacy-policy"
              className="inline-flex items-center justify-center px-4 py-2.5 rounded-xl border border-border text-xs font-semibold text-foreground hover:bg-muted transition-colors"
            >
              Privacy Policy
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
