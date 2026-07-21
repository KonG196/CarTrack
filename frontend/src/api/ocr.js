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
const PREPARE_TIMEOUT_MS = 8000;

// Load via a plain <img>, not createImageBitmap: iOS Safari decodes HEIC in an
// <img> natively, but createImageBitmap on a HEIC File could HANG (not reject) —
// which left the scan spinning before the upload ever started. A hard timeout
// guarantees we never wait on the decoder: if it doesn't come back, we send the
// original file as-is. Modern Safari applies EXIF orientation to <img>/canvas.
function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error('decode-timeout'));
    }, PREPARE_TIMEOUT_MS);
    function cleanup() {
      clearTimeout(timer);
      URL.revokeObjectURL(url);
    }
    img.onload = () => {
      cleanup();
      resolve(img);
    };
    img.onerror = () => {
      cleanup();
      reject(new Error('decode-error'));
    };
    img.decoding = 'async';
    img.src = url;
  });
}

async function prepareScanImage(file) {
  if (typeof document === 'undefined' || typeof Image === 'undefined') return file;
  try {
    const img = await loadImage(file);
    const w0 = img.naturalWidth || img.width;
    const h0 = img.naturalHeight || img.height;
    if (!w0 || !h0) return file;
    const scale = Math.min(1, MAX_SCAN_EDGE / Math.max(w0, h0));
    // Already small (a plain jpeg under ~1.5MB and within size): send as-is.
    if (scale >= 1 && file.size < 1_500_000 && /jpe?g/i.test(file.type)) return file;
    const w = Math.max(1, Math.round(w0 * scale));
    const h = Math.max(1, Math.round(h0 * scale));
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    canvas.getContext('2d').drawImage(img, 0, 0, w, h);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85));
    return blob ? new File([blob], 'scan.jpg', { type: 'image/jpeg' }) : file;
  } catch {
    return file; // decode unsupported/slow → let the server handle the original
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
