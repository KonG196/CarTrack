import client from './client';

export const DOCUMENT_KINDS = [
  { value: 'tech_passport', label: 'Техпаспорт' },
  { value: 'insurance', label: 'Страховка' },
  { value: 'inspection', label: 'Техогляд' },
  { value: 'invoice', label: 'Рахунок' },
  { value: 'other', label: 'Інше' },
];

export const EXPIRING_KINDS = ['insurance', 'inspection'];

export function documentKindLabel(kind) {
  return DOCUMENT_KINDS.find((k) => k.value === kind)?.label || kind;
}

export async function getDocuments(carId) {
  const { data } = await client.get(`/cars/${carId}/documents`);
  return data;
}

export async function uploadDocument(carId, { file, kind, title, expiresAt }) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('kind', kind);
  formData.append('title', title);
  if (expiresAt) formData.append('expires_at', expiresAt);
  const { data } = await client.post(`/cars/${carId}/documents`, formData);
  return data;
}

export async function getDocumentBlob(documentId) {
  const { data } = await client.get(`/documents/${documentId}`, { responseType: 'blob' });
  return data; // Blob
}

export async function deleteDocument(documentId) {
  await client.delete(`/documents/${documentId}`);
}

export function expiresInDays(expiresAt, today = new Date()) {
  if (!expiresAt) return null;
  const match = String(expiresAt).slice(0, 10).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const [, year, month, day] = match;
  const target = new Date(Number(year), Number(month) - 1, Number(day));
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((target - start) / 86400000);
}
