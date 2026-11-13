"use client";

import React, { useSyncExternalStore } from "react";
import Link from "next/link";
import { isAuthenticated } from "@/utils/auth";

const emptySubscribe = () => () => {};

export function PublicAuthActions() {
  const isAuth = useSyncExternalStore(
    emptySubscribe,
    () => isAuthenticated(),
    () => false
  );

  if (isAuth) {
    return (
      <Link
        href="/dashboard"
        className="px-4 py-2 bg-[#162C5B] hover:bg-[#0F1E3D] dark:bg-[#E28123] dark:hover:bg-[#c86815] text-white rounded-lg text-xs font-bold shadow-md shadow-[#162C5B]/20 dark:shadow-[#E28123]/20 transition-all inline-flex items-center gap-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span>Go to Dashboard</span>
        <span aria-hidden="true">→</span>
      </Link>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Link
        href="/login"
        className="px-3.5 py-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        Sign In
      </Link>
      <Link
        href="/register"
        className="px-4 py-2 bg-[#162C5B] hover:bg-[#0F1E3D] dark:bg-[#E28123] dark:hover:bg-[#c86815] text-white rounded-lg text-xs font-bold shadow-md shadow-[#162C5B]/20 dark:shadow-[#E28123]/20 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        Get Started
      </Link>
    </div>
  );
}
