import Cookies from 'js-cookie';
import { jwtDecode } from 'jwt-decode';

export const setTokens = (access: string, refresh?: string) => {
  const isSecure = typeof window !== 'undefined' && window.location.protocol === 'https:';
  if (access && access !== 'undefined' && access !== 'null') {
    Cookies.set('access_token', access, { expires: 1, sameSite: 'strict', secure: isSecure });
  }
  if (refresh && refresh !== 'undefined' && refresh !== 'null') {
    Cookies.set('refresh_token', refresh, { expires: 30, sameSite: 'strict', secure: isSecure });
  }
};

export const getAccessToken = (): string | undefined => {
  const token = Cookies.get('access_token');
  if (!token || token === 'undefined' || token === 'null' || token.trim() === '') {
    return undefined;
  }
  return token;
};

export const getRefreshToken = (): string | undefined => {
  const token = Cookies.get('refresh_token');
  if (!token || token === 'undefined' || token === 'null' || token.trim() === '') {
    return undefined;
  }
  return token;
};

export const removeTokens = () => {
  Cookies.remove('access_token');
  Cookies.remove('refresh_token');
  removeUser();
  if (typeof window !== 'undefined') {
    try {
      localStorage.removeItem('vouch_active_company_id');
      localStorage.removeItem('vouch_user');
    } catch {}
  }
};

interface DecodedTokenPayload {
  exp?: number;
  user_id?: string;
  email?: string;
  role?: string;
  is_staff?: boolean;
  is_superuser?: boolean;
  [key: string]: unknown;
}

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

export const isAuthenticated = (): boolean => {
  const token = getAccessToken();
  const refreshToken = getRefreshToken();
  if (!token && !refreshToken) return false;

  // If access token is still fresh, user is fully authenticated
  if (token && !isTokenExpired(token)) {
    return true;
  }

  // If access token expired but refresh token is still valid, session is restorable via refresh
  if (refreshToken && !isTokenExpired(refreshToken)) {
    return true;
  }

  return false;
};

export interface AuthUser {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  role: 'ADMIN' | 'OWNER' | 'CA' | 'EMPLOYEE' | 'VIEWER' | string;
  is_staff?: boolean;
  is_superuser?: boolean;
}

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

  // Prioritize cryptographically signed JWT claims for role & identity to prevent localStorage privilege tampering
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
          is_staff: decoded.is_staff !== undefined ? Boolean(decoded.is_staff) : Boolean(storedUser?.is_staff),
          is_superuser: decoded.is_superuser !== undefined ? Boolean(decoded.is_superuser) : Boolean(storedUser?.is_superuser),
        };
      }
    } catch {}
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
  return Boolean(
    user.is_superuser ||
    (user.is_staff && user.role?.toUpperCase() === 'ADMIN')
  );
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
  return allowedRoles.map(r => r.toUpperCase()).includes(role);
};

