import client from './client';

// OCR can legitimately take a while (tesseract passes + a remote fallback), but
// it must never spin forever: without a timeout a stalled response left the
// scan loader running for minutes. 90s is well past a real scan; past it we
// fail gracefully so the user can retry.
const SCAN_TIMEOUT_MS = 90_000;

export async function scanReceipt(file) {
  const formData = new FormData();
  formData.append('file', file);
  // No explicit Content-Type: axios sets multipart/form-data with the boundary itself.
  const { data } = await client.post('/ocr/scan', formData, { timeout: SCAN_TIMEOUT_MS });
  return data; // {liters, price_per_liter, total_cost, date, gas_station, raw_text}
}

export async function scanWorkOrder(file) {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await client.post('/ocr/scan-order', formData, { timeout: SCAN_TIMEOUT_MS });
  return data; // {items, parts_cost, labor_cost, total_cost, date, confident, raw_text}
}
