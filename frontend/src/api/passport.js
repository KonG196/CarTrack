import client from './client';

// Owner-side: mint (or regenerate) the passport link and get a printable QR.
export async function mintPassportToken(carId, { regenerate = false } = {}) {
  const { data } = await client.post(`/cars/${carId}/passport-token`, null, {
    params: regenerate ? { regenerate: true } : undefined,
  });
  return data;
}

export async function revokePassportToken(carId) {
  await client.delete(`/cars/${carId}/passport-token`);
}

// Public-side: no auth, no app state — a plain fetch so a stranger's missing
// token never trips the auth interceptor. Returns null for a revoked/wrong link.
export async function getPublicPassport(token) {
  const base = import.meta.env.VITE_API_URL || '/api';
  const response = await fetch(`${base}/public/cars/${encodeURIComponent(token)}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`passport request failed: ${response.status}`);
  return response.json();
}
