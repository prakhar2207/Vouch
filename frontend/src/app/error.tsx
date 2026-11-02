'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    console.error('[ErrorBoundary caught error]:', error);
  }, [error]);

  const handleClearCacheAndReload = async () => {
    setClearing(true);
    try {
      if (typeof window !== 'undefined') {
        if ('caches' in window) {
          const keys = await caches.keys();
          await Promise.all(keys.map((k) => caches.delete(k)));
        }
        if ('serviceWorker' in navigator) {
          const regs = await navigator.serviceWorker.getRegistrations();
          for (const reg of regs) {
            await reg.unregister();
          }
        }
        sessionStorage.clear();
      }
    } catch (e) {
      console.warn('Cache clearing error:', e);
    }
    window.location.href = '/dashboard';
  };

  return (
    <div className="flex min-h-screen w-full flex-col items-center justify-center bg-background text-foreground p-4">
      <div className="mx-auto flex max-w-[420px] flex-col items-center justify-center space-y-4 text-center">
        <div className="w-12 h-12 rounded-2xl bg-destructive/15 text-destructive flex items-center justify-center font-bold text-xl border border-destructive/20 shadow-xs">
          ⚠️
        </div>
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight">Something went wrong!</h2>
        <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed">
          An unexpected error occurred while loading this view on your device.
        </p>

        {error?.message && (
          <div className="w-full text-left bg-muted/60 border border-border/80 rounded-xl p-3 text-xs font-mono text-muted-foreground overflow-auto max-h-32">
            <span className="text-destructive font-semibold">Error:</span> {error.message}
            {error.digest && <div className="text-[10px] text-muted-foreground/70 mt-1">Digest: {error.digest}</div>}
          </div>
        )}

        <div className="flex flex-col sm:flex-row items-center gap-2.5 w-full pt-2">
          <button
            onClick={() => reset()}
            className="w-full sm:flex-1 inline-flex items-center justify-center rounded-xl bg-primary px-4 py-2.5 text-xs sm:text-sm font-semibold text-primary-foreground shadow-xs hover:bg-primary/90 transition-colors cursor-pointer"
          >
            Try Again
          </button>
          <button
            onClick={handleClearCacheAndReload}
            disabled={clearing}
            className="w-full sm:flex-1 inline-flex items-center justify-center rounded-xl bg-secondary border border-border px-4 py-2.5 text-xs sm:text-sm font-semibold text-secondary-foreground hover:bg-secondary/80 transition-colors cursor-pointer"
          >
            {clearing ? 'Clearing...' : 'Clear Cache & Reload'}
          </button>
        </div>

        <Link
          href="/dashboard"
          className="text-xs text-primary hover:underline font-medium pt-1"
        >
          Return to Dashboard →
        </Link>
      </div>
    </div>
  );
}
