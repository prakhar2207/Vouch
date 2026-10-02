'use client';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html>
      <body style={{ backgroundColor: '#09090b', color: '#fafafa', margin: 0, fontFamily: 'system-ui, sans-serif' }}>
        <div style={{ display: 'flex', height: '100vh', width: '100vw', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '1rem' }}>Something went wrong!</h2>
          <button
            onClick={() => reset()}
            style={{ 
              padding: '0.5rem 1rem', 
              backgroundColor: '#fafafa', 
              color: '#09090b', 
              border: 'none', 
              borderRadius: '0.375rem',
              fontWeight: 500,
              cursor: 'pointer'
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
