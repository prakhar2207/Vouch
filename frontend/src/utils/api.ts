import axios from 'axios';
import { getAccessToken } from './auth';

// In production (e.g. Vercel), fallback to Render backend if NEXT_PUBLIC_API_URL isn't set
const getDefaultApiUrl = () => {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return 'https://vouch-api.onrender.com';
  }
  return 'http://localhost:8000';
};

export const API_BASE_URL = getDefaultApiUrl().replace(/\/+$/, '');

export const api = axios.create({
  baseURL: API_BASE_URL,
});

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}, (error) => {
  return Promise.reject(error);
});

export default api;

