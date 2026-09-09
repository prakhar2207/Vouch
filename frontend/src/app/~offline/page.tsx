"use client";
import React from "react";
import Link from "next/link";

export default function OfflineFallback() {
  return (
    <div className="min-h-screen bg-zinc-950 text-foreground flex flex-col items-center justify-center p-6 text-center">
      <div className="w-16 h-16 bg-blue-600/10 text-blue-500 rounded-full flex items-center justify-center text-3xl font-bold mb-4 border border-blue-500/20">
        ⚡
      </div>
      <h1 className="text-2xl font-bold mb-2">You are currently offline</h1>
      <p className="text-sm text-muted-foreground max-w-md mb-6">
        It looks like your internet connection is down. Don't worry, your cached Vouch records and offline data remain secure on your device.
      </p>
      <div className="flex gap-4">
        <button
          onClick={() => window.location.reload()}
          className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-foreground text-xs font-bold rounded-lg transition-colors cursor-pointer"
        >
          🔄 Retry Connection
        </button>
        <Link
          href="/dashboard"
          className="px-5 py-2.5 bg-muted hover:bg-zinc-700 text-foreground/80 text-xs font-bold rounded-lg border border-input transition-colors"
        >
          Go to Dashboard
        </Link>
      </div>
    </div>
  );
}
