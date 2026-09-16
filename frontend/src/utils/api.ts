import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getAccessToken, getRefreshToken, setTokens, removeTokens, isTokenExpired } from './auth';

// In production (e.g. Vercel), fallback to Render backend if NEXT_PUBLIC_API_URL isn't set
const getDefaultApiUrl = () => {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return 'https://vouch-api-752s.onrender.com';
  }
  return 'http://localhost:8000';
};

export const API_BASE_URL = getDefaultApiUrl().replace(/\/+$/, '');

export const api = axios.create({
  baseURL: API_BASE_URL,
});

// Request Telemetry & Loop Guard (Phase 1 & 19)
interface RequestStats {
  count: number;
  recentTimestamps: number[];
}
const requestTelemetry = new Map<string, RequestStats>();

function getCleanEndpoint(url?: string): string {
  if (!url) return 'unknown';
  try {
    const parsed = new URL(url, API_BASE_URL);
    return parsed.pathname;
  } catch {
    return url.split('?')[0];
  }
}

function recordAndGuardRequest(config: any) {
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

  const token = getAccessToken();
  const currentAuth = config.headers?.Authorization;
  const isInvalidAuth = !currentAuth || currentAuth === 'Bearer undefined' || currentAuth === 'Bearer null' || currentAuth === 'Bearer ';

  if (token && isInvalidAuth) {
    if (!config.headers) config.headers = {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}

api.interceptors.request.use(recordAndGuardRequest, (error) => Promise.reject(error));
axios.interceptors.request.use(recordAndGuardRequest, (error) => Promise.reject(error));

// ---------------------------------------------------------------------------
// Automatic 401 Unauthorized Session Refresh & Retry Interceptor
// ---------------------------------------------------------------------------
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value: string) => void;
  reject: (reason?: any) => void;
}> = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else if (token) {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

async function handleResponseError(error: AxiosError) {
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

  if (isRefreshing) {
    // Another request is already refreshing the session, queue this request
    return new Promise<string>((resolve, reject) => {
      failedQueue.push({ resolve, reject });
    })
      .then((newToken) => {
        if (!originalRequest.headers) originalRequest.headers = {} as any;
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return axios(originalRequest);
      })
      .catch((err) => Promise.reject(err));
  }

  isRefreshing = true;
  const refreshToken = getRefreshToken();

  const isPublicRoute = typeof window !== 'undefined' && (
    window.location.pathname.startsWith('/sales/') ||
    window.location.pathname.includes('/print')
  );

  if (!refreshToken || isTokenExpired(refreshToken)) {
    isRefreshing = false;
    processQueue(error, null);
    removeTokens();
    if (typeof window !== 'undefined' && window.location.pathname !== '/login' && !isPublicRoute) {
      console.warn('[AUTH] Session expired and refresh token unavailable, redirecting to /login');
      window.location.href = '/login?expired=1';
    }
    return Promise.reject(error);
  }

  try {
    // Call refresh endpoint directly with raw axios to bypass interceptor recursion
    const refreshResponse = await axios.post(
      `${API_BASE_URL}/api/v1/auth/refresh/`,
      { refresh: refreshToken },
      { headers: { 'Content-Type': 'application/json' } }
    );

    const newAccessToken = refreshResponse.data?.access;
    const newRefreshToken = refreshResponse.data?.refresh || refreshToken;

    if (!newAccessToken) {
      throw new Error('No access token returned by refresh endpoint');
    }

    // Persist fresh tokens in cookies
    setTokens(newAccessToken, newRefreshToken);

    // Resolve any concurrent requests waiting in queue
    processQueue(null, newAccessToken);

    // Update original request with new token and retry seamlessly
    if (!originalRequest.headers) originalRequest.headers = {} as any;
    originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;

    return axios(originalRequest);
  } catch (refreshErr) {
    processQueue(refreshErr, null);
    removeTokens();
    if (typeof window !== 'undefined' && window.location.pathname !== '/login' && !isPublicRoute) {
      console.warn('[AUTH] Refresh token rejected, redirecting to /login');
      window.location.href = '/login?expired=1';
    }
    return Promise.reject(refreshErr);
  } finally {
    isRefreshing = false;
  }
}

api.interceptors.response.use((response) => response, handleResponseError);
axios.interceptors.response.use((response) => response, handleResponseError);

export default api;

