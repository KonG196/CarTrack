import client from './client';

// Superadmin panel — user management. Every call here is gated server-side by
// the is_superadmin flag; a non-admin gets 403 and never sees the /admin route.

export async function listUsers({ q = '', limit = 50, offset = 0 } = {}) {
  const { data } = await client.get('/admin/users', {
    params: { q: q || undefined, limit, offset },
  });
  return data; // { users: [...], total }
}

export async function getUser(id) {
  const { data } = await client.get(`/admin/users/${id}`);
  return data; // { user, cars, audit }
}

export async function updateUser(id, payload) {
  const { data } = await client.patch(`/admin/users/${id}`, payload);
  return data; // { user, cars, audit }
}

export async function setStatus(id, payload) {
  // payload: any subset of { email_verified, is_superadmin, blocked, blocked_reason }
  const { data } = await client.post(`/admin/users/${id}/status`, payload);
  return data; // { user, cars, audit }
}

export async function resetLink(id) {
  const { data } = await client.post(`/admin/users/${id}/reset-link`);
  return data; // { link, emailed }
}

export async function verifyLink(id) {
  const { data } = await client.post(`/admin/users/${id}/verify-link`);
  return data;
}

export async function sendReset(id) {
  const { data } = await client.post(`/admin/users/${id}/send-reset`);
  return data; // { link, emailed }
}

export async function sendVerify(id) {
  const { data } = await client.post(`/admin/users/${id}/send-verify`);
  return data;
}

export async function deleteUser(id) {
  await client.delete(`/admin/users/${id}`);
}

export async function auditFeed({ limit = 100, offset = 0 } = {}) {
  const { data } = await client.get('/admin/audit', { params: { limit, offset } });
  return data; // [ ...rows ]
}
