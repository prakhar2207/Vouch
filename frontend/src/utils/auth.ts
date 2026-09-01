import Cookies from 'js-cookie';
import { jwtDecode } from 'jwt-decode';

export const setTokens = (access: string, refresh: string) => {
  Cookies.set('access_token', access, { expires: 1 });
  Cookies.set('refresh_token', refresh, { expires: 7 });
};

export const getAccessToken = () => {
  return Cookies.get('access_token');
};

export const removeTokens = () => {
  Cookies.remove('access_token');
  Cookies.remove('refresh_token');
};

export const isAuthenticated = () => {
  const token = getAccessToken();
  if (!token) return false;
  
  try {
    const decoded: any = jwtDecode(token);
    return decoded.exp * 1000 > Date.now();
  } catch (e) {
    return false;
  }
};
