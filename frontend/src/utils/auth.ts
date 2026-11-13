import { safePurgeTenantData } from '@/lib/db/offlineDb';
import Cookies from 'js-cookie';
import { jwtDecode } from 'jwt-decode';

export interface AuthUser {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  role: 'ADMIN' | 'OWNER' | 'CA' | 'EMPLOYEE' | 'VIEWER' | string;
  is_staff?: boolean;
  is_superuser?: boolean;
}

export interface BrowserSessionMeta {
  mode: 'cookie' | 'token';
  userId?: string;
  expiresAt?: number;
  refreshExpiresAt?: number;
  updatedAt: number;
}

interface DecodedTokenPayload {
  exp?: number;
  user_id?: string;
  email?: string;
  role?: string;
  is_staff?: boolean;
  is_superuser?: boolean;
  [key: string]: unknown;
}

const SESSION_META_KEY = 'vouch_session_meta';
const AUTH_LOGOUT_STORAGE_KEY = 'vouch_auth_logout_signal';

// Native/test-only in-memory token custody; NEVER persisted to web localStorage or JS cookies in browsers
let inMemoryNativeAccessToken: string | undefined;
let inMemoryNativeRefreshToken: string | undefined;
let inMemoryCsrfToken: string | undefined;

let authEpoch = 1;
let authAbortController: AbortController | null =
  typeof AbortController !== 'undefined' ? new AbortController() : null;

let authCoordinationChannel: BroadcastChannel | null = null;
let listenersInitialized = false;

export function isCapacitorNative(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const cap = (window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor;
    return Boolean(cap?.isNativePlatform?.());
  } catch {
    return false;
  }
}

export function getAuthEpoch(): number {
  return authEpoch;
}

export function getAuthAbortSignal(): AbortSignal | undefined {
  return authAbortController?.signal;
}

export function bumpAuthEpochAndAbort(): number {
  authEpoch += 1;
  try {
    authAbortController?.abort('AUTH_SESSION_INVALIDATED');
  } catch {}
  if (typeof AbortController !== 'undefined') {
    authAbortController = new AbortController();
  }
  inMemoryNativeAccessToken = undefined;
  inMemoryNativeRefreshToken = undefined;
  inMemoryCsrfToken = undefined;
  return authEpoch;
}

export function setCsrfToken(token?: string | null): void {
  if (token && token.trim()) {
    inMemoryCsrfToken = token.trim();
  }
}

export function getCsrfToken(): string | undefined {
  if (inMemoryCsrfToken) return inMemoryCsrfToken;
  if (typeof document !== 'undefined' && document.cookie) {
    const match = document.cookie
      .split(';')
      .map((c) => c.trim())
      .find((c) => c.startsWith('csrftoken='));
    if (match) {
      const val = decodeURIComponent(match.slice('csrftoken='.length));
      if (val) return val;
    }
  }
  return undefined;
}

const syncCapacitorPreference = (key: string, value: string | null) => {
  if (typeof window !== 'undefined' && isCapacitorNative()) {
    try {
      const cap = (window as unknown as {
        Capacitor?: {
          Plugins?: {
            Preferences?: {
              set: (opts: { key: string; value: string }) => Promise<void> | void;
              remove: (opts: { key: string }) => Promise<void> | void;
            };
          };
        };
      }).Capacitor;
      if (cap?.Plugins?.Preferences) {
        if (value === null) {
          cap.Plugins.Preferences.remove({ key });
        } else {
          cap.Plugins.Preferences.set({ key, value });
        }
      }
    } catch {}
  }
};

export async function hydrateNativeTokens(): Promise<void> {
  if (!isCapacitorNative() || typeof window === 'undefined') return;
  try {
    const cap = (window as unknown as {
      Capacitor?: {
        Plugins?: {
          Preferences?: { get: (opts: { key: string }) => Promise<{ value?: string | null }> };
        };
      };
    }).Capacitor;
    if (!cap?.Plugins?.Preferences) return;
    const [acc, ref] = await Promise.all([
      cap.Plugins.Preferences.get({ key: 'vouch_access_token' }).catch(() => ({ value: null })),
      cap.Plugins.Preferences.get({ key: 'vouch_refresh_token' }).catch(() => ({ value: null })),
    ]);
    if (acc?.value && acc.value !== 'undefined' && acc.value !== 'null') {
      inMemoryNativeAccessToken = acc.value;
    }
    if (ref?.value && ref.value !== 'undefined' && ref.value !== 'null') {
      inMemoryNativeRefreshToken = ref.value;
    }
  } catch {}
}

export function purgeLegacyJsTokens(): void {
  try {
    Cookies.remove('access_token', { path: '/' });
    Cookies.remove('refresh_token', { path: '/' });
    Cookies.remove('access_token');
    Cookies.remove('refresh_token');
  } catch {}
  if (typeof window !== 'undefined') {
    try {
      localStorage.removeItem('vouch_access_token');
      localStorage.removeItem('vouch_refresh_token');
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
    } catch {}
  }
}

function readSessionMeta(): BrowserSessionMeta | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(SESSION_META_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as BrowserSessionMeta;
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function writeSessionMeta(meta: BrowserSessionMeta): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(SESSION_META_KEY, JSON.stringify(meta));
  } catch {}
}

function clearClientAuthAndTenantStorage(options?: { wipeDeviceKeys?: boolean }): void {
  if (typeof window === 'undefined') return;
  const fixedKeys = [
    SESSION_META_KEY,
    'vouch_access_token',
    'vouch_refresh_token',
    'access_token',
    'refresh_token',
    'vouch_user',
    'vouch_active_company_id',
    'activeCompanyId',
    'vouch_active_company',
    'vouch_active_company_name',
    'vouch_cached_companies_list',
    'current_company_id',
  ];
  if (options?.wipeDeviceKeys) {
    fixedKeys.push(
      'vouch_device_id',
      'vouch_protocol_replica_id',
      'vouch_ed25519_key_id',
      'vouch_ed25519_pub_hex',
      'vouch_ed25519_priv_jwk',
    );
  }
  for (const k of fixedKeys) {
    try {
      localStorage.removeItem(k);
    } catch {}
  }

  // Clear dynamic cached forecasts and company-scoped localStorage/sessionStorage caches
  try {
    const lsKeysToDelete: string[] = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (
        key &&
        (key.startsWith('vouch_authoritative_forecast_') ||
          key.startsWith('vouch_health_') ||
          key.startsWith('vouch_cached_'))
      ) {
        lsKeysToDelete.push(key);
      }
    }
    for (const k of lsKeysToDelete) {
      localStorage.removeItem(k);
    }
  } catch {}

  try {
    if (typeof sessionStorage !== 'undefined') {
      const ssKeysToDelete: string[] = [];
      for (let i = 0; i < sessionStorage.length; i += 1) {
        const key = sessionStorage.key(i);
        if (key && key.startsWith('vouch_')) {
          ssKeysToDelete.push(key);
        }
      }
      for (const k of ssKeysToDelete) {
        sessionStorage.removeItem(k);
      }
    }
  } catch {}
}

function initCrossTabAuthListener(): void {
  if (listenersInitialized || typeof window === 'undefined') return;
  listenersInitialized = true;

  try {
    if ('BroadcastChannel' in window) {
      authCoordinationChannel = new BroadcastChannel('vouch_auth_coordination');
      (authCoordinationChannel as unknown as { unref?: () => void }).unref?.();
      authCoordinationChannel.onmessage = (event) => {
        const msg = event.data as { type?: string } | null;
        if (msg?.type === 'AUTH_LOGOUT') {
          bumpAuthEpochAndAbort();
          purgeLegacyJsTokens();
          clearClientAuthAndTenantStorage();
          if (!window.location.pathname.startsWith('/login')) {
            window.location.replace('/login?expired=1');
          }
        }
      };
    }
  } catch {}

  try {
    window.addEventListener?.('storage', (event: StorageEvent) => {
      if (event.key === AUTH_LOGOUT_STORAGE_KEY && event.newValue) {
        bumpAuthEpochAndAbort();
        purgeLegacyJsTokens();
        clearClientAuthAndTenantStorage();
        if (!window.location.pathname.startsWith('/login')) {
          window.location.replace('/login?expired=1');
        }
      }
    });
  } catch {}
}

if (typeof window !== 'undefined') {
  initCrossTabAuthListener();
}

export function broadcastAuthLogout(reason: 'logout' | 'expired' = 'logout'): void {
  if (typeof window === 'undefined') return;
  try {
    authCoordinationChannel?.postMessage({ type: 'AUTH_LOGOUT', reason, timestamp: Date.now() });
  } catch {}
  try {
    localStorage.setItem(AUTH_LOGOUT_STORAGE_KEY, `${reason}:${Date.now()}`);
    localStorage.removeItem(AUTH_LOGOUT_STORAGE_KEY);
  } catch {}
}

/**
 * Records an authenticated browser (HttpOnly cookie) or Capacitor native session
 * without storing JWT strings in web localStorage or JS-readable document.cookie.
 */
export const setAuthenticatedSession = (params: {
  user?: AuthUser | null;
  csrfToken?: string | null;
  expiresAt?: number;
  refreshExpiresAt?: number;
  access?: string;
  refresh?: string;
}) => {
  initCrossTabAuthListener();
  // Always strip any legacy browser-readable JWT copies
  purgeLegacyJsTokens();

  if (params.csrfToken) {
    setCsrfToken(params.csrfToken);
  }

  if (params.user) {
    setUser(params.user);
  }

  if (isCapacitorNative()) {
    if (params.access && params.access !== 'undefined' && params.access !== 'null') {
      inMemoryNativeAccessToken = params.access;
      syncCapacitorPreference('vouch_access_token', params.access);
    }
    if (params.refresh && params.refresh !== 'undefined' && params.refresh !== 'null') {
      inMemoryNativeRefreshToken = params.refresh;
      syncCapacitorPreference('vouch_refresh_token', params.refresh);
    }
  }

  const now = Date.now();
  let expMs = params.expiresAt || now + 30 * 60 * 1000;
  let userId = params.user?.id;
  if (params.access && !params.expiresAt) {
    try {
      const dec = jwtDecode<DecodedTokenPayload>(params.access);
      if (dec.exp) expMs = dec.exp * 1000;
      if (!userId && dec.user_id) userId = String(dec.user_id);
      if (!params.user && dec.user_id) {
        setUser({
          id: String(dec.user_id),
          email: String(dec.email || ''),
          role: String(dec.role || 'VIEWER'),
          is_staff: Boolean(dec.is_staff),
          is_superuser: Boolean(dec.is_superuser),
        });
      }
    } catch {}
  }

  writeSessionMeta({
    mode: isCapacitorNative() && params.access ? 'token' : 'cookie',
    userId: userId || getUser()?.id,
    expiresAt: expMs,
    refreshExpiresAt: params.refreshExpiresAt || now + 7 * 24 * 60 * 60 * 1000,
    updatedAt: now,
  });
};

export const setTokens = (access: string, refresh?: string) => {
  setAuthenticatedSession({ access, refresh });
};

/**
 * Returns access token ONLY for Capacitor native clients (never exposes browser HttpOnly JWTs to JS).
 */
export const getAccessToken = (): string | undefined => {
  if (!isCapacitorNative()) {
    return undefined;
  }
  if (
    !inMemoryNativeAccessToken ||
    inMemoryNativeAccessToken === 'undefined' ||
    inMemoryNativeAccessToken === 'null' ||
    inMemoryNativeAccessToken.trim() === ''
  ) {
    return undefined;
  }
  return inMemoryNativeAccessToken;
};

/**
 * Returns refresh token ONLY for Capacitor native clients (never exposes browser HttpOnly JWTs to JS).
 */
export const getRefreshToken = (): string | undefined => {
  if (!isCapacitorNative()) {
    return undefined;
  }
  if (
    !inMemoryNativeRefreshToken ||
    inMemoryNativeRefreshToken === 'undefined' ||
    inMemoryNativeRefreshToken === 'null' ||
    inMemoryNativeRefreshToken.trim() === ''
  ) {
    return undefined;
  }
  return inMemoryNativeRefreshToken;
};

export const removeTokens = (options?: {
  wipeLocalDeviceData?: boolean;
  skipOfflinePurge?: boolean;
  broadcastReason?: 'logout' | 'expired';
}) => {
  bumpAuthEpochAndAbort();

  if (!options?.skipOfflinePurge) {
    try {
      safePurgeTenantData(undefined, { forceDestroyAll: Boolean(options?.wipeLocalDeviceData) }).catch(() => {});
    } catch {}
  }

  purgeLegacyJsTokens();
  removeUser();
  clearClientAuthAndTenantStorage({ wipeDeviceKeys: Boolean(options?.wipeLocalDeviceData) });

  if (typeof window !== 'undefined') {
    syncCapacitorPreference('vouch_access_token', null);
    syncCapacitorPreference('vouch_refresh_token', null);
    syncCapacitorPreference('vouch_user', null);
    syncCapacitorPreference('vouch_active_company_id', null);
    syncCapacitorPreference('vouch_active_company_name', null);
    syncCapacitorPreference('vouch_active_company_state_code', null);
    syncCapacitorPreference('vouch_active_company_gstin', null);
  }

  if (options?.broadcastReason) {
    broadcastAuthLogout(options.broadcastReason);
  }
};

export const isTokenExpired = (token?: string): boolean => {
  if (!token || token === 'undefined' || token === 'null' || token.trim() === '') return true;
  try {
    const decoded = jwtDecode<DecodedTokenPayload>(token);
    if (!decoded || !decoded.exp) return true;
    // Buffer by 10 seconds to preempt edge-of-expiry network races
    return decoded.exp * 1000 <= Date.now() + 10000;
  } catch {
    return true;
  }
};

export const isBrowserSessionLikelyExpired = (): boolean => {
  const meta = readSessionMeta();
  if (!meta) return true;
  if (!meta.expiresAt) return false;
  return meta.expiresAt <= Date.now() + 10000;
};

export const isAuthenticated = (): boolean => {
  if (isCapacitorNative()) {
    const token = getAccessToken();
    const refreshToken = getRefreshToken();
    if (!token && !refreshToken) return false;
    if (typeof navigator !== 'undefined' && !navigator.onLine) return true;
    if (token && !isTokenExpired(token)) return true;
    if (refreshToken && !isTokenExpired(refreshToken)) return true;
    return Boolean(refreshToken || token);
  }

  const meta = readSessionMeta();
  if (!meta) return false;
  // While offline, preserve authenticated workspace UI access until reconnection
  if (typeof navigator !== 'undefined' && !navigator.onLine) {
    return true;
  }
  if (meta.refreshExpiresAt && meta.refreshExpiresAt <= Date.now()) {
    return Boolean(meta.expiresAt && meta.expiresAt > Date.now());
  }
  return true;
};

export const setUser = (user: AuthUser) => {
  if (typeof window !== 'undefined' && user) {
    try {
      localStorage.setItem('vouch_user', JSON.stringify(user));
    } catch (e) {
      console.error('Error saving user to localStorage', e);
    }
  }
};

export const getUser = (): AuthUser | null => {
  if (typeof window === 'undefined') return null;

  let storedUser: AuthUser | null = null;
  try {
    const raw = localStorage.getItem('vouch_user');
    if (raw) {
      storedUser = JSON.parse(raw);
    }
  } catch (e) {
    console.error('Error reading user from localStorage', e);
  }

  if (isCapacitorNative()) {
    const token = getAccessToken();
    if (token) {
      try {
        const decoded = jwtDecode<DecodedTokenPayload>(token);
        if (decoded && decoded.user_id) {
          return {
            id: decoded.user_id,
            email: decoded.email || storedUser?.email || '',
            first_name: storedUser?.first_name,
            last_name: storedUser?.last_name,
            role: decoded.role || storedUser?.role || 'VIEWER',
            is_staff:
              decoded.is_staff !== undefined ? Boolean(decoded.is_staff) : Boolean(storedUser?.is_staff),
            is_superuser:
              decoded.is_superuser !== undefined
                ? Boolean(decoded.is_superuser)
                : Boolean(storedUser?.is_superuser),
          };
        }
      } catch {}
    }
  }

  return storedUser;
};

export const removeUser = () => {
  if (typeof window !== 'undefined') {
    try {
      localStorage.removeItem('vouch_user');
    } catch {}
  }
};

export const getUserRole = (): string => {
  const user = getUser();
  return (user?.role || 'VIEWER').toUpperCase();
};

export const isSuperAdmin = (authUser?: AuthUser | null): boolean => {
  const user = authUser || getUser();
  if (!user) return false;
  return Boolean(user.is_superuser || (user.is_staff && user.role?.toUpperCase() === 'ADMIN'));
};

export const isAdmin = (): boolean => {
  return isSuperAdmin();
};

export const isOwnerOrAdmin = (): boolean => {
  const user = getUser();
  if (!user) return false;
  const role = user.role?.toUpperCase();
  return role === 'OWNER' || role === 'ADMIN';
};

export const canPerformAccounting = (): boolean => {
  const user = getUser();
  if (!user) return false;
  const role = user.role?.toUpperCase();
  return role === 'ADMIN' || role === 'OWNER' || role === 'CA';
};

export const isReadOnlyUser = (): boolean => {
  const user = getUser();
  if (!user) return true;
  const role = user.role?.toUpperCase();
  return role === 'VIEWER';
};

export const hasRole = (allowedRoles: string[]): boolean => {
  const user = getUser();
  if (!user) return false;
  const role = (user.role || '').toUpperCase();
  if (role === 'OWNER') return true;
  return allowedRoles.map((r) => r.toUpperCase()).includes(role);
};
