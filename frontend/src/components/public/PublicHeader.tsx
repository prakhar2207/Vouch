"use client";

import React from "react";
import { useIsNativeApp } from "@/hooks/useIsNativeApp";
import Link from "next/link";
import { VouchLogo } from "@/components/VouchLogo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { PublicAuthActions } from "./PublicAuthActions";

interface PublicHeaderProps {
  activePath?: "/pricing" | "/contact" | "/privacy-policy" | "/terms" | "/refund-policy";
}

export function PublicHeader({ activePath }: PublicHeaderProps) {
  const isNative = useIsNativeApp();
  const navItems = isNative
    ? ([
        { href: "/", label: "Home" },
        { href: "/contact", label: "Contact" },
      ] as const)
    : ([
        { href: "/", label: "Home" },
        { href: "/pricing", label: "Pricing" },
        { href: "/contact", label: "Contact" },
      ] as const);

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/50 bg-background/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 sm:gap-6">
          <Link
            href="/"
            className="flex items-center gap-2.5 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <VouchLogo size={28} showWordmark={true} />
            <span className="hidden sm:inline-block px-2 py-0.5 text-[10px] font-mono bg-[#162C5B]/10 text-[#162C5B] dark:bg-[#E28123]/15 dark:text-[#FBA94C] rounded border border-[#162C5B]/20 dark:border-[#E28123]/30 font-bold">
              Cloud Core
            </span>
          </Link>

          <nav aria-label="Primary navigation" className="hidden md:flex items-center gap-1 text-[13px] font-medium">
            {navItems.map((item) => {
              const isActive = activePath === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-3 py-1.5 rounded-lg transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                    isActive
                      ? "bg-muted text-foreground font-semibold"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <nav aria-label="Mobile quick links" className="flex md:hidden items-center gap-1 text-xs font-medium">
            {!isNative && (
              <Link
                href="/pricing"
                className={`px-2 py-1 rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  activePath === "/pricing"
                    ? "bg-muted text-foreground font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Pricing
              </Link>
            )}
            <Link
              href="/contact"
              className={`px-2 py-1 rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                activePath === "/contact"
                  ? "bg-muted text-foreground font-semibold"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Contact
            </Link>
          </nav>
          <ThemeToggle />
          <PublicAuthActions />
        </div>
      </div>
    </header>
  );
}
