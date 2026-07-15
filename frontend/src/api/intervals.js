import client from './client';

export async function getIntervals(carId) {
  const { data } = await client.get(`/cars/${carId}/intervals`);
  return data;
}

export async function createInterval(carId, payload) {
  const { data } = await client.post(`/cars/${carId}/intervals`, payload);
  return data;
}

export async function updateInterval(intervalId, payload) {
  const { data } = await client.patch(`/intervals/${intervalId}`, payload);
  return data;
}

export async function deleteInterval(intervalId) {
  await client.delete(`/intervals/${intervalId}`);
}

export async function completeInterval(intervalId, payload) {
  const { data } = await client.post(`/intervals/${intervalId}/complete`, payload);
  return data;
}

export async function getIntervalPresets() {
  const { data } = await client.get('/interval-presets');
  return data;
}
