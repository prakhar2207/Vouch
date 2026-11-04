import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getAccessToken, getRefreshToken, setTokens, removeTokens, isTokenExpired } from './auth';

// In production (e.g. Vercel), fallback to Render backend if NEXT_PUBLIC_API_URL isn't set
const getDefaultApiUrl = () => {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  // When running inside native Android or iOS Capacitor WebView container, route to cloud API
  if (typeof window !== 'undefined' && (Boolean((window as any).Capacitor?.isNativePlatform?.()) || (window as any).Capacitor !== undefined)) {
    return 'https://api.srilekh.com';
  }
  if (typeof window !== 'undefined' && window.location?.hostname && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return 'https://api.srilekh.com';
  }
  return 'http://localhost:8000';
};

export const API_BASE_URL = getDefaultApiUrl().replace(/\/+$/, '');

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
});

// Dedicated isolated client for auth refresh to prevent interceptor recursion
const refreshClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 12000,
});

// Request Telemetry & Loop Guard (Phase 1 & 19)
interface RequestStats {
  count: number;
  recentTimestamps: number[];
}
const requestTelemetry = new Map<string, RequestStats>();

function isPublicRoute(): boolean {
  if (typeof window === 'undefined') return false;
  const p = window.location.pathname;
  return p.startsWith('/share/') || p.startsWith('/sales/') || p.includes('/print') || p === '/login' || p === '/register';
}

function getCleanEndpoint(url?: string): string {
  if (!url) return 'unknown';
  try {
    const parsed = new URL(url, API_BASE_URL);
    // Normalize UUIDs and numeric IDs to prevent unbounded Map growth
    return parsed.pathname
      .replace(/\/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}/gi, '/:id')
      .replace(/\/\d+(?=\/|$)/g, '/:id');
  } catch {
    return url.split('?')[0];
  }
}

// ---------------------------------------------------------------------------
// Shared in-flight refresh promise mutex across all callers (P0 Concurrency Fix)
// ---------------------------------------------------------------------------
let refreshPromise: Promise<string | null> | null = null;

export async function getValidAccessToken(forceRefresh = false): Promise<string | null> {
  const token = getAccessToken();
  if (!forceRefresh && token && !isTokenExpired(token)) {
    return token;
  }

  const refreshToken = getRefreshToken();
  if (!refreshToken || isTokenExpired(refreshToken)) {
    // If no valid refresh token is available and we're online, clear tokens and redirect to login
    if (typeof window !== 'undefined' && !isPublicRoute() && typeof navigator !== 'undefined' && navigator.onLine) {
      console.warn('[AUTH] Session expired: No valid refresh token available. Redirecting to login.');
      removeTokens();
      window.location.replace('/login?expired=1');
    }
    return null;
  }

  // If currently offline, return stored token without attempting network refresh
  if (typeof navigator !== 'undefined' && !navigator.onLine) {
    return token || null;
  }

  // Mutex: If a refresh is already in flight, reuse the exact same promise (prevents token rotation race)
  if (refreshPromise) {
    try {
      const refreshedToken = await refreshPromise;
      return refreshedToken || getAccessToken() || null;
    } catch {
      return getAccessToken() || null;
    }
  }

  refreshPromise = (async () => {
    try {
      const currentRefreshToken = getRefreshToken() || refreshToken;
      const res = await refreshClient.post(
        '/api/v1/auth/refresh/',
        { refresh: currentRefreshToken },
        { headers: { 'Content-Type': 'application/json' }, timeout: 12000 }
      );
      const newAccess = res.data?.access;
      const newRefresh = res.data?.refresh || currentRefreshToken;
      if (newAccess) {
        setTokens(newAccess, newRefresh);
        return newAccess;
      }
      return null;
    } catch (err: any) {
      console.warn('[AUTH] Token refresh request failed:', err?.message || err);
      // ONLY invalidate session if server explicitly returned 401/400 (token invalid/blacklisted/expired)
      // AND it was NOT a network error or timeout.
      const isNetworkError =
        (typeof navigator !== 'undefined' && !navigator.onLine) ||
        !err.response ||
        err.code === 'ERR_NETWORK' ||
        err.code === 'ECONNABORTED' ||
        err.message?.toLowerCase().includes('timeout') ||
        err.message?.toLowerCase().includes('network');

      if (!isNetworkError && err.response && (err.response.status === 401 || err.response.status === 400)) {
        console.warn('[AUTH] Refresh token explicitly rejected by server (401/400). Clearing session.');
        removeTokens();
        if (typeof window !== 'undefined' && !isPublicRoute()) {
          window.location.replace('/login?expired=1');
        }
      }
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return await refreshPromise;
}

async function recordAndGuardRequest(config: InternalAxiosRequestConfig) {
  // Skip telemetry tracking during SSR to prevent server-side memory leaks
  if (typeof window === 'undefined') {
    const token = getAccessToken();
    const currentAuth = config.headers?.Authorization;
    const isInvalidAuth = !currentAuth || currentAuth === 'Bearer undefined' || currentAuth === 'Bearer null' || currentAuth === 'Bearer ';
    if (token && isInvalidAuth) {
      if (!config.headers) config.headers = {} as InternalAxiosRequestConfig['headers'];
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  }

  const endpoint = getCleanEndpoint(config.url);
  const now = Date.now();
  let stats = requestTelemetry.get(endpoint);
  if (!stats) {
    stats = { count: 0, recentTimestamps: [] };
    requestTelemetry.set(endpoint, stats);
  }

  stats.count += 1;
  // Keep only timestamps within last 10 seconds
  stats.recentTimestamps = stats.recentTimestamps.filter((ts) => now - ts < 10000);
  stats.recentTimestamps.push(now);

  // Diagnostic log (never logs tokens, payloads, or PII)
  if (process.env.NODE_ENV !== 'production' || typeof window !== 'undefined') {
    console.log(`[API] ${endpoint} count=${stats.count}`);
  }

  // Loop detection: > 5 requests to same endpoint within 10s
  if (stats.recentTimestamps.length > 5) {
    console.warn(
      `[API LOOP DETECTED] endpoint=${endpoint} count=${stats.recentTimestamps.length} window=10s`
    );
  }

  let token = getAccessToken();
  const isAuthEndpoint = endpoint.includes('/api/v1/auth/refresh/') || endpoint.includes('/api/v1/auth/login/') || endpoint.includes('/api/v1/auth/token/');

  // Preemptive token refresh: If access token is expired or missing, obtain a valid token via shared mutex
  if (!isAuthEndpoint && (!token || isTokenExpired(token))) {
    const validToken = await getValidAccessToken();
    if (validToken) {
      token = validToken;
    }
  }

  const currentAuth = config.headers?.Authorization;
  // Determine if Authorization header is missing, malformed, or stale/expired
  let isInvalidAuth = !currentAuth || currentAuth === 'Bearer undefined' || currentAuth === 'Bearer null' || currentAuth === 'Bearer ';
  if (!isInvalidAuth && typeof currentAuth === 'string' && currentAuth.startsWith('Bearer ')) {
    const raw = currentAuth.slice(7).trim();
    if (isTokenExpired(raw)) {
      isInvalidAuth = true;
    }
  }

  if (token && (isInvalidAuth || (config.headers?.Authorization !== `Bearer ${token}` && !isAuthEndpoint))) {
    if (!config.headers) config.headers = {} as InternalAxiosRequestConfig['headers'];
    config.headers.Authorization = `Bearer ${token}`;
  }

  // Automatic tenant isolation: attach X-Company-ID from localStorage
  if (typeof window !== 'undefined') {
    const activeCompanyId = localStorage.getItem('vouch_active_company_id') || localStorage.getItem('current_company_id');
    if (activeCompanyId && !config.headers?.['X-Company-ID']) {
      if (!config.headers) config.headers = {} as InternalAxiosRequestConfig['headers'];
      config.headers['X-Company-ID'] = activeCompanyId;
    }
  }

  return config;
}

api.interceptors.request.use(recordAndGuardRequest, (error) => Promise.reject(error));

// ---------------------------------------------------------------------------
// Automatic 401 Unauthorized Session Refresh & Retry Interceptor
// ---------------------------------------------------------------------------
async function handleResponseError(error: AxiosError) {
  // CRITICAL: Never queue or refresh tokens during SSR
  if (typeof window === 'undefined') {
    return Promise.reject(error);
  }

  const originalRequest = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;

  // Only handle 401 Unauthorized errors with a valid request config
  if (!error.response || error.response.status !== 401 || !originalRequest) {
    return Promise.reject(error);
  }

  const endpoint = getCleanEndpoint(originalRequest.url);

  // If this was an auth endpoint itself (refresh or login), do NOT retry
  if (endpoint.includes('/api/v1/auth/refresh/') || endpoint.includes('/api/v1/auth/login/') || endpoint.includes('/api/v1/auth/token/')) {
    return Promise.reject(error);
  }

  // Guard against infinite refresh loops on the same request
  if (originalRequest._retry) {
    return Promise.reject(error);
  }

  originalRequest._retry = true;

  // If user is currently OFFLINE, never drop the session or attempt network refresh
  if (typeof navigator !== 'undefined' && !navigator.onLine) {
    console.warn('[AUTH] Offline: Skipping remote token refresh. Preserving local session.');
    return Promise.reject(error);
  }

  try {
    // Force refresh since the server rejected the current token with 401
    const newToken = await getValidAccessToken(true);
    if (!newToken) {
      return Promise.reject(error);
    }

    // Update original request with new token and retry seamlessly
    if (!originalRequest.headers) originalRequest.headers = {} as InternalAxiosRequestConfig['headers'];
    originalRequest.headers.Authorization = `Bearer ${newToken}`;

    return api(originalRequest);
  } catch (refreshErr) {
    return Promise.reject(refreshErr);
  }
}

api.interceptors.response.use((response) => response, handleResponseError);

export default api;
