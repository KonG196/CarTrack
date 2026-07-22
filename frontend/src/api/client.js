import axios from 'axios';
import i18n from '../i18n';

export const TOKEN_KEY = 'kapot_tracker_token';
export const REFRESH_KEY = 'kapot_tracker_refresh';

const BASE = import.meta.env.VITE_API_URL || '/api';

const client = axios.create({
  // Same-origin '/api' is what the nginx image serves; a split deployment
  // (frontend on a CDN, API elsewhere) sets VITE_API_URL to the full origin.
  baseURL: BASE,
});

export function setTokens({ access_token, refresh_token } = {}) {
  if (access_token) localStorage.setItem(TOKEN_KEY, access_token);
  if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

const PUBLIC_PATHS = ['/login', '/register', '/reset', '/verify', '/join'];

const isPublicPath = (pathname) =>
  PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

function hardLogout() {
  clearTokens();
  if (!isPublicPath(window.location.pathname)) {
    window.location.href = '/login';
  }
}

// Single-flight: many requests can 401 at once when the access token expires;
// they all await one refresh call rather than firing a stampede of them.
let refreshPromise = null;

function refreshAccessToken() {
  const refresh = localStorage.getItem(REFRESH_KEY);
  if (!refresh) return Promise.reject(new Error('no refresh token'));
  if (!refreshPromise) {
    // Bare axios, not `client`: the refresh call must not loop through this
    // same 401 interceptor.
    refreshPromise = axios
      .post(`${BASE}/auth/refresh`, { refresh_token: refresh })
      .then((res) => {
        setTokens(res.data);
        return res.data.access_token;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const { response, config } = error;
    if (!response || response.status !== 401 || !config) {
      return Promise.reject(error);
    }
    const url = config.url || '';
    // A 401 from the refresh/login call itself, or a request we already retried
    // once, means the session is truly dead — stop and sign out.
    if (config._retry || url.includes('/auth/refresh') || url.includes('/auth/token')) {
      hardLogout();
      return Promise.reject(error);
    }
    try {
      const access = await refreshAccessToken();
      config._retry = true;
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${access}`;
      return client(config);
    } catch {
      hardLogout();
      return Promise.reject(error);
    }
  },
);

export function isNetworkError(error) {
  return Boolean(error) && !error.response;
}

export function extractError(error, fallback = i18n.t('apiClient.genericError')) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
  }
  return fallback;
}

export default client;
