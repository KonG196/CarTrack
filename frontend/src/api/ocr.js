import client from './client';

// OCR can legitimately take a while (tesseract passes + a remote fallback), but
// it must never spin forever: without a timeout a stalled response left the
// scan loader running for minutes. 90s is well past a real scan; past it we
// fail gracefully so the user can retry.
const SCAN_TIMEOUT_MS = 90_000;

// The server downscales to 1600px anyway, so uploading a full-resolution phone
// photo (an iPhone HEIC/JPEG can be 3–12 MB) only stalls the request on mobile
// data — which read as «scanning forever». Shrink to 1600px JPEG in the browser
// first: a ~200–500 KB upload, and HEIC becomes JPEG so the server reads it too.
// EXIF orientation is baked in so a sideways photo is scanned upright. Anything
// the browser can't decode falls back to the original file untouched.
const MAX_SCAN_EDGE = 1600;

async function prepareScanImage(file) {
  if (typeof createImageBitmap !== 'function' || typeof document === 'undefined') return file;
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
    const scale = Math.min(1, MAX_SCAN_EDGE / Math.max(bitmap.width, bitmap.height));
    const w = Math.round(bitmap.width * scale);
    const h = Math.round(bitmap.height * scale);
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    canvas.getContext('2d').drawImage(bitmap, 0, 0, w, h);
    bitmap.close?.();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85));
    return blob ? new File([blob], 'scan.jpg', { type: 'image/jpeg' }) : file;
  } catch {
    return file;
  }
}

export async function scanReceipt(file) {
  const formData = new FormData();
  formData.append('file', await prepareScanImage(file));
  // No explicit Content-Type: axios sets multipart/form-data with the boundary itself.
  const { data } = await client.post('/ocr/scan', formData, { timeout: SCAN_TIMEOUT_MS });
  return data; // {liters, price_per_liter, total_cost, date, gas_station, raw_text}
}

export async function scanWorkOrder(file) {
  const formData = new FormData();
  formData.append('file', await prepareScanImage(file));
  const { data } = await client.post('/ocr/scan-order', formData, { timeout: SCAN_TIMEOUT_MS });
  return data; // {items, parts_cost, labor_cost, total_cost, date, confident, raw_text}
}
