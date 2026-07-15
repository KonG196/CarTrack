import client from './client';

export async function getLogs(carId, { type, q, limit = 50, offset = 0 } = {}) {
  const params = { limit, offset };
  if (type) params.type = type;
  if (q) params.q = q;
  const { data } = await client.get(`/cars/${carId}/logs`, { params });
  return data; // {items, total}
}

export async function getLog(logId) {
  const { data } = await client.get(`/logs/${logId}`);
  return data;
}

export async function getRefuelContext(carId) {
  const { data } = await client.get(`/cars/${carId}/refuel-context`);
  return data;
}

export async function createLog(carId, payload) {
  const { data } = await client.post(`/cars/${carId}/logs`, payload);
  return data;
}

export async function updateLog(logId, payload) {
  const { data } = await client.patch(`/logs/${logId}`, payload);
  return data;
}

export async function deleteLog(logId) {
  await client.delete(`/logs/${logId}`);
}
