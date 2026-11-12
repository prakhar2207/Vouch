import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { safePurgeTenantData } from '@/lib/db/offlineDb';
import {
  getAccessToken,
  getAuthAbortSignal,
  getAuthEpoch,
  getCsrfToken,
  getRefreshToken,
  hydrateNativeTokens,
  isAuthenticated,
  isBrowserSessionLikelyExpired,
  isCapacitorNative,
  removeTokens,
  setAuthenticatedSession,
  setCsrfToken,
  isTokenExpired,
} from './auth';

const PRODUCTION_WEB_HOSTS = new Set(['srilekh.com', 'www.srilekh.com', 'app.srilekh.com']);
const PRODUCTION_API_HOSTS = new Set(['api.srilekh.com', 'vouch-api-752s.onrender.com']);

export function resolveApiBaseUrl(options?: {
  envApiUrl?: string;
  appEnv?: string;
  hostname?: string;
  native?: boolean;
}): string {
  const envApiUrl = (options?.envApiUrl ?? process.env.NEXT_PUBLIC_API_URL ?? '').trim();
  const appEnv = (options?.appEnv ?? process.env.NEXT_PUBLIC_APP_ENV ?? '').trim().toLowerCase();
  const hostname = (
    options?.hostname ??
    (typeof window !== 'undefined' ? window.location?.hostname : '') ??
    ''
  )
    .trim()
    .toLowerCase();
  const native = options?.native ?? isCapacitorNative();

  if (envApiUrl) {
    try {
      const parsedHost = new URL(envApiUrl).hostname.toLowerCase();
      const isStagingContext =
        appEnv === 'staging' ||
        hostname.includes('staging') ||
        hostname.includes('preview') ||
        hostname.includes('vouch-u3u7');
      if (isStagingContext && PRODUCTION_API_HOSTS.has(parsedHost)) {
        throw new Error(
          `[API Isolation] Refusing to connect staging/preview host (${hostname || appEnv}) to production API (${parsedHost}).`
        );
      }
    } catch (err) {
      if (err instanceof Error && err.message.startsWith('[API Isolation]')) {
        throw err;
      }
    }
    return envApiUrl.replace(/\/+$/, '');
  }

  if (native) {
    return 'https://api.srilekh.com';
  }
  if (hostname && PRODUCTION_WEB_HOSTS.has(hostname)) {
    return 'https://api.srilekh.com';
  }
  if (
    hostname &&
    (hostname.includes('staging') ||
      hostname.includes('preview') ||
      hostname.endsWith('.vercel.app') ||
      hostname.endsWith('.onrender.com'))
  ) {
    return 'https://vouch-u3u7.onrender.com';
  }
  if (hostname && hostname !== 'localhost' && hostname !== '127.0.0.1') {
    return 'https://api.srilekh.com';
  }
  return 'http://localhost:8000';
}

export const API_BASE_URL = resolveApiBaseUrl();

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  withCredentials: true,
});

// Dedicated isolated client for auth refresh & CSRF bootstrap (prevents interceptor recursion)
const refreshClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 12000,
  withCredentials: true,
});

interface RequestStats {
  count: number;
  recentTimestamps: number[];
}
const requestTelemetry = new Map<string, RequestStats>();

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

function isPublicRoute(): boolean {
  if (typeof window === 'undefined') return false;
  const p = window.location.pathname;
  return (
    p.startsWith('/share/') ||
    p.startsWith('/sales/') ||
    p.includes('/print') ||
    p === '/login' ||
    p === '/register'
  );
}

function isApiTargetUrl(url?: string): boolean {
  if (!url) return true;
  if (url.startsWith('/')) return true;
  try {
    const target = new URL(url, API_BASE_URL);
    const apiBase = new URL(API_BASE_URL);
    return target.origin === apiBase.origin;
  } catch {
    return false;
  }
}

function getCleanEndpoint(url?: string): string {
  if (!url) return 'unknown';
  try {
    const parsed = new URL(url, API_BASE_URL);
    return parsed.pathname
      .replace(/\/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}/gi, '/:id')
      .replace(/\/\d+(?=\/|$)/g, '/:id');
  } catch {
    return url.split('?')[0];
  }
}

let csrfBootstrapPromise: Promise<string | undefined> | null = null;

export async function ensureCsrfToken(): Promise<string | undefined> {
  if (isCapacitorNative()) return undefined;
  const existing = getCsrfToken();
  if (existing) return existing;
  if (
    typeof navigator !== 'undefined' &&
    !navigator.onLine
  ) {
    return undefined;
  }
  if (typeof window === 'undefined') {
    return undefined;
  }
  // Never issue network CSRF bootstrap calls inside Node unit-test runners
  if (typeof process !== 'undefined' && process.env?.NODE_TEST_CONTEXT) {
    return undefined;
  }
  if (csrfBootstrapPromise) {
    return await csrfBootstrapPromise;
  }
  csrfBootstrapPromise = (async () => {
    try {
      const res = await refreshClient.get('/api/v1/auth/csrf/', {
        withCredentials: true,
        headers: { 'X-Client-Type': 'web' },
      });
      const token = res.data?.csrf_token;
      if (token) {
        setCsrfToken(token);
        return token;
      }
    } catch {
      // Non-fatal if offline or endpoint unreachable
    } finally {
      csrfBootstrapPromise = null;
    }
    return getCsrfToken();
  })();
  return await csrfBootstrapPromise;
}

// ---------------------------------------------------------------------------
// Shared in-flight refresh promise mutex across all callers
// ---------------------------------------------------------------------------
let refreshPromise: Promise<boolean> | null = null;

export async function ensureValidSession(forceRefresh = false): Promise<boolean> {
  if (typeof window === 'undefined') {
    return false;
  }

  if (isCapacitorNative()) {
    await hydrateNativeTokens();
    const token = getAccessToken();
    if (!forceRefresh && token && !isTokenExpired(token)) {
      return true;
    }
    const refreshToken = getRefreshToken();
    if (!refreshToken || isTokenExpired(refreshToken)) {
      if (!isPublicRoute() && typeof navigator !== 'undefined' && navigator.onLine) {
        removeTokens({ broadcastReason: 'expired' });
        window.location.replace('/login?expired=1');
      }
      return false;
    }
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      return Boolean(token || refreshToken);
    }
  } else {
    if (!isAuthenticated()) {
      return false;
    }
    if (!forceRefresh && !isBrowserSessionLikelyExpired()) {
      return true;
    }
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      return true;
    }
  }

  if (refreshPromise) {
    return await refreshPromise;
  }

  const startEpoch = getAuthEpoch();

  refreshPromise = (async () => {
    try {
      const native = isCapacitorNative();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        'X-Client-Type': native ? 'capacitor' : 'web',
      };
      if (!native) {
        const csrf = await ensureCsrfToken();
        if (csrf) {
          headers['X-CSRFToken'] = csrf;
        }
      }

      const body = native ? { refresh: getRefreshToken() } : {};
      const res = await refreshClient.post('/api/v1/auth/refresh/', body, {
        headers,
        withCredentials: !native,
        timeout: 12000,
      });

      // Discard stale refresh result if user logged out while refresh was in flight
      if (getAuthEpoch() !== startEpoch) {
        return false;
      }

      const newAccess = res.data?.access;
      const newRefresh = res.data?.refresh;
      const csrfToken = res.data?.csrf_token;

      if (native && !newAccess) {
        return false;
      }

      setAuthenticatedSession({
        access: native ? newAccess : undefined,
        refresh: native ? newRefresh : undefined,
        csrfToken,
        expiresAt: res.data?.expires_at,
        refreshExpiresAt: res.data?.refresh_expires_at,
        user: res.data?.user,
      });
      return true;
    } catch (err: unknown) {
      const axiosErr = err as AxiosError;
      console.warn('[AUTH] Token refresh request failed:', axiosErr?.message || err);
      if (getAuthEpoch() !== startEpoch) {
        return false;
      }

      const isNetworkError =
        (typeof navigator !== 'undefined' && !navigator.onLine) ||
        !axiosErr?.response ||
        axiosErr?.code === 'ERR_NETWORK' ||
        axiosErr?.code === 'ECONNABORTED' ||
        axiosErr?.message?.toLowerCase().includes('timeout') ||
        axiosErr?.message?.toLowerCase().includes('network');

      if (
        !isNetworkError &&
        axiosErr?.response &&
        (axiosErr.response.status === 401 ||
          axiosErr.response.status === 400 ||
          axiosErr.response.status === 403)
      ) {
        console.warn('[AUTH] Refresh session explicitly rejected by server. Clearing session.');
        removeTokens({ broadcastReason: 'expired' });
        if (typeof window !== 'undefined' && !isPublicRoute()) {
          window.location.replace('/login?expired=1');
        }
      }
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return await refreshPromise;
}

export async function getValidAccessToken(forceRefresh = false): Promise<string | null> {
  const valid = await ensureValidSession(forceRefresh);
  if (!valid) return null;
  if (isCapacitorNative()) {
    return getAccessToken() || null;
  }
  return null;
}

async function prepareRequestConfig(config: InternalAxiosRequestConfig) {
  const targetUrl = config.url ? `${config.baseURL || ''}${config.url}` : '';
  if (config.url && !config.baseURL && config.url.startsWith('http') && !isApiTargetUrl(config.url)) {
    return config;
  }
  if (targetUrl && !isApiTargetUrl(config.url)) {
    return config;
  }

  if (typeof window === 'undefined') {
    const token = getAccessToken();
    const currentAuth = config.headers?.Authorization;
    const isInvalidAuth =
      !currentAuth ||
      currentAuth === 'Bearer undefined' ||
      currentAuth === 'Bearer null' ||
      currentAuth === 'Bearer ';
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
  stats.recentTimestamps = stats.recentTimestamps.filter((ts) => now - ts < 10000);
  stats.recentTimestamps.push(now);

  if (process.env.NODE_ENV !== 'production') {
    console.log(`[API] ${endpoint} count=${stats.count}`);
  }
  if (stats.recentTimestamps.length > 5) {
    console.warn(
      `[API LOOP DETECTED] endpoint=${endpoint} count=${stats.recentTimestamps.length} window=10s`
    );
  }

  const isAuthEndpoint =
    endpoint.includes('/api/v1/auth/refresh/') ||
    endpoint.includes('/api/v1/auth/login/') ||
    endpoint.includes('/api/v1/auth/logout/') ||
    endpoint.includes('/api/v1/auth/csrf/') ||
    endpoint.includes('/api/v1/auth/token/');

  const native = isCapacitorNative();
  if (!config.headers) config.headers = {} as InternalAxiosRequestConfig['headers'];
  config.headers['X-Client-Type'] = native ? 'capacitor' : 'web';

  // Strip any accidental "Bearer undefined" / "Bearer null" from legacy callers
  const currentAuth = config.headers.Authorization;
  if (
    typeof currentAuth === 'string' &&
    (currentAuth === 'Bearer undefined' ||
      currentAuth === 'Bearer null' ||
      currentAuth.trim() === 'Bearer' ||
      (!native && currentAuth.startsWith('Bearer ')))
  ) {
    delete config.headers.Authorization;
  }

  if (!isAuthEndpoint && isAuthenticated()) {
    await ensureValidSession(false);
  }

  // Abort in-flight API calls automatically if user logs out unless caller provided custom signal
  if (!isAuthEndpoint && !config.signal) {
    const sig = getAuthAbortSignal();
    if (sig) config.signal = sig;
  }

  if (native) {
    const token = getAccessToken();
    if (token && !isAuthEndpoint) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    config.withCredentials = false;
  } else {
    config.withCredentials = true;
    const method = (config.method || 'GET').toUpperCase();
    if (UNSAFE_METHODS.has(method)) {
      const csrf = await ensureCsrfToken();
      if (csrf) {
        config.headers['X-CSRFToken'] = csrf;
      }
    }
  }

  // Automatic tenant isolation header
  const activeCompanyId =
    localStorage.getItem('vouch_active_company_id') || localStorage.getItem('current_company_id');
  if (activeCompanyId && !config.headers['X-Company-ID']) {
    config.headers['X-Company-ID'] = activeCompanyId;
  }

  return config;
}

async function handleResponseError(error: AxiosError) {
  if (typeof window === 'undefined') {
    return Promise.reject(error);
  }

  const originalRequest = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;
  if (!error.response || error.response.status !== 401 || !originalRequest) {
    return Promise.reject(error);
  }

  if (!isApiTargetUrl(originalRequest.url)) {
    return Promise.reject(error);
  }

  const endpoint = getCleanEndpoint(originalRequest.url);
  if (
    endpoint.includes('/api/v1/auth/refresh/') ||
    endpoint.includes('/api/v1/auth/login/') ||
    endpoint.includes('/api/v1/auth/logout/') ||
    endpoint.includes('/api/v1/auth/token/')
  ) {
    return Promise.reject(error);
  }

  if (originalRequest._retry) {
    return Promise.reject(error);
  }
  originalRequest._retry = true;

  if (typeof navigator !== 'undefined' && !navigator.onLine) {
    return Promise.reject(error);
  }

  const epochBefore = getAuthEpoch();
  const refreshed = await ensureValidSession(true);
  if (!refreshed || getAuthEpoch() !== epochBefore) {
    return Promise.reject(error);
  }

  if (isCapacitorNative()) {
    const newToken = getAccessToken();
    if (!newToken) return Promise.reject(error);
    if (!originalRequest.headers) originalRequest.headers = {} as InternalAxiosRequestConfig['headers'];
    originalRequest.headers.Authorization = `Bearer ${newToken}`;
  } else {
    originalRequest.withCredentials = true;
    const method = (originalRequest.method || 'GET').toUpperCase();
    if (UNSAFE_METHODS.has(method)) {
      const csrf = getCsrfToken();
      if (csrf) {
        if (!originalRequest.headers) originalRequest.headers = {} as InternalAxiosRequestConfig['headers'];
        originalRequest.headers['X-CSRFToken'] = csrf;
      }
    }
  }

  return axios.request(originalRequest);
}

api.interceptors.request.use(prepareRequestConfig, (error) => Promise.reject(error));
api.interceptors.response.use((response) => response, handleResponseError);

// Install global axios defaults & interceptors once so legacy direct-axios callers
// automatically use HttpOnly cookies + CSRF in browsers without manual Bearer headers.
const GLOBAL_AXIOS_FLAG = '__srilekhAuthInterceptorsInstalled';
if (!(axios as unknown as Record<string, boolean>)[GLOBAL_AXIOS_FLAG]) {
  (axios as unknown as Record<string, boolean>)[GLOBAL_AXIOS_FLAG] = true;
  axios.defaults.withCredentials = true;
  axios.interceptors.request.use(prepareRequestConfig, (error) => Promise.reject(error));
  axios.interceptors.response.use((response) => response, handleResponseError);
}

/**
 * Fetch wrapper supporting browser HttpOnly cookies + CSRF, Capacitor native Bearer tokens,
 * logout AbortSignal cancellation, and automatic 401 refresh retry.
 */
function toHeaderRecord(raw?: HeadersInit): Record<string, string> {
  const out: Record<string, string> = {};
  if (!raw) return out;
  if (raw instanceof Headers) {
    raw.forEach((v, k) => {
      out[k] = v;
    });
  } else if (Array.isArray(raw)) {
    for (const [k, v] of raw) {
      out[k] = v;
    }
  } else {
    Object.assign(out, raw);
  }
  return out;
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const native = isCapacitorNative();
  const method = (init.method || 'GET').toUpperCase();
  const headers = toHeaderRecord(init.headers);
  headers['X-Client-Type'] = native ? 'capacitor' : 'web';

  const authKey = Object.keys(headers).find((k) => k.toLowerCase() === 'authorization');
  const authVal = authKey ? headers[authKey] : undefined;
  if (
    authKey &&
    authVal &&
    (authVal === 'Bearer undefined' ||
      authVal === 'Bearer null' ||
      authVal.trim() === 'Bearer' ||
      (!native && authVal.startsWith('Bearer ')))
  ) {
    delete headers[authKey];
  }

  if (native) {
    const token = getAccessToken();
    if (token && !authKey) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  } else if (UNSAFE_METHODS.has(method)) {
    const csrf = await ensureCsrfToken();
    if (csrf) {
      headers['X-CSRFToken'] = csrf;
    }
  }

  const signal = init.signal || getAuthAbortSignal();
  const credentials: RequestCredentials = native ? 'omit' : 'include';

  const res = await fetch(input, { ...init, headers, credentials, signal });
  if (res.status !== 401 || !isAuthenticated()) {
    return res;
  }

  const epochBefore = getAuthEpoch();
  const refreshed = await ensureValidSession(true);
  if (!refreshed || getAuthEpoch() !== epochBefore) {
    return res;
  }

  const retryHeaders: Record<string, string> = { ...headers };
  if (native) {
    const freshToken = getAccessToken();
    if (freshToken) retryHeaders['Authorization'] = `Bearer ${freshToken}`;
  } else if (UNSAFE_METHODS.has(method)) {
    const freshCsrf = getCsrfToken();
    if (freshCsrf) retryHeaders['X-CSRFToken'] = freshCsrf;
  }
  return await fetch(input, { ...init, headers: retryHeaders, credentials, signal });
}

/**
 * Coordinated server + client logout:
 * 1. Revokes server session (token_version increment + refresh blacklist + HttpOnly cookie clear).
 * 2. Stops background sync & aborts in-flight requests via authEpoch bump.
 * 3. Clears tenant read caches (or full local device wipe when wipeLocalDeviceData=true).
 * 4. Notifies Service Worker & open tabs before redirecting to /login.
 */
export async function performLogout(options?: { wipeLocalDeviceData?: boolean }): Promise<void> {
  const native = isCapacitorNative();
  const refresh = native ? getRefreshToken() : undefined;
  const nativeAccess = native ? getAccessToken() : undefined;

  if (typeof navigator === 'undefined' || navigator.onLine) {
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        'X-Client-Type': native ? 'capacitor' : 'web',
      };
      if (native && nativeAccess) {
        headers.Authorization = `Bearer ${nativeAccess}`;
      } else if (!native) {
        const csrf = await ensureCsrfToken();
        if (csrf) headers['X-CSRFToken'] = csrf;
      }
      await refreshClient.post(
        '/api/v1/auth/logout/',
        refresh ? { refresh } : {},
        { headers, withCredentials: !native, timeout: 4000 }
      );
    } catch {
      // Never trap user logged in if offline or server unreachable
    }
  }

  try {
    await safePurgeTenantData(undefined, { forceDestroyAll: Boolean(options?.wipeLocalDeviceData) });
    if (typeof window !== 'undefined' && 'caches' in window) {
      caches.delete('srilekh-pages-cache').catch(() => {});
    }
    if (typeof navigator !== 'undefined' && 'serviceWorker' in navigator && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ type: 'CLEAR_SESSION_CACHES' });
    }
  } catch {}

  removeTokens({
    wipeLocalDeviceData: Boolean(options?.wipeLocalDeviceData),
    skipOfflinePurge: true,
    broadcastReason: 'logout',
  });
}

export default api;
