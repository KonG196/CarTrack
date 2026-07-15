import client from './client';

/**
 * reportFilename(7) -> 'kapot-tracker-report-7.pdf'
 * Mirrors the Content-Disposition filename the backend sends.
 */
export function reportFilename(carId) {
  return `kapot-tracker-report-${carId}.pdf`;
}

/**
 * Triggers a browser download for a blob via a temporary object URL.
 */
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function downloadCarReport(carId) {
  const { data } = await client.get(`/cars/${carId}/report`, {
    responseType: 'blob',
  });
  saveBlob(data, reportFilename(carId));
}
