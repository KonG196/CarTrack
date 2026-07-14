import client from './client';

export async function getStatus() {
  const { data } = await client.get('/telegram/status');
  return data; // {linked}
}

export async function createLinkCode() {
  const { data } = await client.post('/telegram/link-code');
  return data; // {code, deep_link, expires_in_minutes}
}

export async function unlink() {
  await client.delete('/telegram/link');
}
