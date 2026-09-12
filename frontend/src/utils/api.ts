import axios from 'axios';
import { getAccessToken } from './auth';

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
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}

api.interceptors.request.use(recordAndGuardRequest, (error) => Promise.reject(error));
axios.interceptors.request.use(recordAndGuardRequest, (error) => Promise.reject(error));

export default api;

