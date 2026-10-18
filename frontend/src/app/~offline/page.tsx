"use client";
import React from "react";
import Link from "next/link";

export default function OfflineFallback() {
  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col items-center justify-center p-6 text-center">
      <div className="w-16 h-16 bg-primary/10 text-primary rounded-full flex items-center justify-center text-3xl font-bold mb-4 border border-primary/20 shadow-sm">
        ⚡
      </div>
      <h1 className="text-2xl font-extrabold tracking-tight mb-2">You are currently offline</h1>
      <p className="text-sm text-muted-foreground max-w-md mb-6 leading-relaxed">
        It looks like your internet connection is down. Don&apos;t worry — your cached SriLekh records and offline data remain safe and accessible on your device.
      </p>
      <div className="flex flex-wrap gap-3 justify-center items-center">
        <Link
          href="/sales/new"
          className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm rounded-xl shadow-lg flex items-center gap-2 transition-all cursor-pointer"
        >
          📝 Create Sales Invoice Offline
        </Link>
        <button
          onClick={() => window.location.reload()}
          className="px-5 py-2.5 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:bg-primary/90 transition-colors cursor-pointer shadow-sm"
        >
          🔄 Retry Connection
        </button>
        <Link
          href="/sales"
          className="px-5 py-2.5 bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold rounded-lg border border-border transition-colors"
        >
          View Sales Invoices
        </Link>
        <Link
          href="/dashboard"
          className="px-5 py-2.5 bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold rounded-lg border border-border transition-colors"
        >
          Go to Dashboard
        </Link>
      </div>
    </div>
  );
}
