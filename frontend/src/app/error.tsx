'use client';

import { useEffect } from 'react';

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex h-screen w-full flex-col items-center justify-center bg-background text-foreground">
      <div className="mx-auto flex max-w-[400px] flex-col items-center justify-center space-y-4 text-center">
        <h2 className="text-2xl font-semibold tracking-tight">Something went wrong!</h2>
        <p className="text-sm text-muted-foreground">
          An unexpected error occurred while loading this page.
        </p>
        <button
          onClick={() => reset()}
          className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 transition-colors"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
