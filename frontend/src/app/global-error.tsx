'use client';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const handleHardReset = async () => {
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
      }
    } catch {}
    window.location.href = '/dashboard';
  };

  return (
    <html>
      <body style={{ backgroundColor: '#09090b', color: '#fafafa', margin: 0, fontFamily: 'system-ui, sans-serif' }}>
        <div style={{ display: 'flex', minHeight: '100vh', width: '100vw', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '1rem', boxSizing: 'border-box' }}>
          <div style={{ maxWidth: '400px', textAlign: 'center' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' }}>Something went wrong!</h2>
            <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '1.25rem', lineHeight: 1.5 }}>
              A fatal error prevented the application shell from rendering.
            </p>
            {error?.message && (
              <div style={{ background: '#27272a', padding: '0.75rem', borderRadius: '0.5rem', fontSize: '0.75rem', color: '#f87171', fontFamily: 'monospace', textAlign: 'left', marginBottom: '1.25rem', wordBreak: 'break-all' }}>
                {error.message}
              </div>
            )}
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
              <button
                onClick={() => reset()}
                style={{ 
                  padding: '0.625rem 1.25rem', 
                  backgroundColor: '#2563eb', 
                  color: '#ffffff', 
                  border: 'none', 
                  borderRadius: '0.5rem',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                  cursor: 'pointer'
                }}
              >
                Try Again
              </button>
              <button
                onClick={handleHardReset}
                style={{ 
                  padding: '0.625rem 1.25rem', 
                  backgroundColor: '#27272a', 
                  color: '#e4e4e7', 
                  border: '1px solid #3f3f46', 
                  borderRadius: '0.5rem',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                  cursor: 'pointer'
                }}
              >
                Reset & Reload
              </button>
            </div>
          </div>
        </div>
      </body>
    </html>
  );
}
