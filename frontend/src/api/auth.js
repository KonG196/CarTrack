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

export async function requestPasswordReset(email, channel) {
  const { data } = await client.post('/auth/reset/request', { email, channel });
  return data;
}

export async function confirmPasswordReset(email, code, newPassword) {
  const { data } = await client.post('/auth/reset/confirm', {
    email,
    code,
    new_password: newPassword,
  });
  return data;
}

export async function confirmEmail(email, code) {
  const { data } = await client.post('/auth/verify/confirm', { email, code });
  return data;
}

export async function resendVerification(email) {
  const { data } = await client.post('/auth/verify/resend', { email });
  return data;
}
