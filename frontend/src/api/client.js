import axios from 'axios';

export const TOKEN_KEY = 'kapot_tracker_token';

const client = axios.create({
  baseURL: '/api',
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

const PUBLIC_PATHS = ['/login', '/register', '/reset', '/join'];

const isPublicPath = (pathname) =>
  PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      if (!isPublicPath(window.location.pathname)) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export function isNetworkError(error) {
  return Boolean(error) && !error.response;
}

export function extractError(error, fallback = 'Сталася помилка. Спробуйте ще раз.') {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
  }
  return fallback;
}

export default client;
