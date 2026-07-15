import client from './client';

export async function uploadPhoto(logId, file) {
  const formData = new FormData();
  formData.append('file', file);
  // No explicit Content-Type: axios sets multipart/form-data with the boundary itself.
  const { data } = await client.post(`/logs/${logId}/photos`, formData);
  return data; // {id, filename, content_type, size, created_at}
}

// An <img src> cannot send the Bearer header, so photos are fetched as blobs
// through the axios client and rendered via object URLs. The caller owns the
// object URL lifecycle (createObjectURL / revokeObjectURL).
export async function getPhotoBlob(photoId) {
  const { data } = await client.get(`/photos/${photoId}`, { responseType: 'blob' });
  return data; // Blob
}

export async function deletePhoto(photoId) {
  await client.delete(`/photos/${photoId}`);
}
