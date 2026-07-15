import client from './client';

export async function decodeVin(vin) {
  const { data } = await client.post('/vin/decode', { vin });
  return data;
}
