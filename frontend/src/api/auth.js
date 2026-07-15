import client from './client';

export async function register(email, password) {
  const { data } = await client.post('/auth/register', { email, password });
  return data;
}

export async function login(email, password) {
  const body = new URLSearchParams();
  body.append('username', email);
  body.append('password', password);
  const { data } = await client.post('/auth/token', body, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return data; // {access_token, token_type}
}

export async function getMe() {
  const { data } = await client.get('/auth/me');
  return data;
}

export async function updateMe(displayName) {
  const { data } = await client.patch('/auth/me', { display_name: displayName });
  return data;
}

export async function requestPasswordReset(email) {
  const { data } = await client.post('/auth/reset/request', { email });
  return data; // завжди 202 {detail} — без енумерації користувачів
}

export async function confirmPasswordReset(email, code, newPassword) {
  const { data } = await client.post('/auth/reset/confirm', {
    email,
    code,
    new_password: newPassword,
  });
  return data;
}
