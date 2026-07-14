import client from './client';

export async function getAnalytics(carId) {
  const { data } = await client.get(`/cars/${carId}/analytics`);
  return data;
}
