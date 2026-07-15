import client from './client';

export async function importObdCsv(carId, file) {
  const formData = new FormData();
  formData.append('file', file);
  // No explicit Content-Type: axios sets multipart/form-data with the boundary itself.
  const { data } = await client.post(`/cars/${carId}/obd`, formData);
  return data; // {session, metrics, verdicts, unmapped_columns}
}

export async function getObdSessions(carId) {
  const { data } = await client.get(`/cars/${carId}/obd`);
  return data; // [{id, filename, recorded_at, duration_s, sample_count, created_at}]
}

export async function getObdSession(sessionId) {
  const { data } = await client.get(`/obd/${sessionId}`);
  return data; // {session, metrics, verdicts, unmapped_columns: []}
}

export async function deleteObdSession(sessionId) {
  await client.delete(`/obd/${sessionId}`);
}
