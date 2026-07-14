import client from './client';

export async function scanReceipt(file) {
  const formData = new FormData();
  formData.append('file', file);
  // No explicit Content-Type: axios sets multipart/form-data with the boundary itself.
  const { data } = await client.post('/ocr/scan', formData);
  return data; // {liters, price_per_liter, total_cost, date, gas_station, raw_text}
}
