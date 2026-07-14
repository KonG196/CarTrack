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
