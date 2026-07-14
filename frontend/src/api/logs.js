import client from './client';

export async function getLogs(carId, { type, limit = 50, offset = 0 } = {}) {
  const params = { limit, offset };
  if (type) params.type = type;
  const { data } = await client.get(`/cars/${carId}/logs`, { params });
  return data; // {items, total}
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
