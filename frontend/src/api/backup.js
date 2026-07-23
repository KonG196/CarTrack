import client from './client';
import i18n from '../i18n';
import { saveBlob } from './reports';

/**
 * exportFilename(new Date(2026, 6, 15)) -> 'kapot-tracker-export-20260715.json'
 * Mirrors the Content-Disposition filename the backend sends.
 */
export function exportFilename(date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `kapot-tracker-export-${y}${m}${d}.json`;
}

export function csvFilename(carId) {
  return `kapot-tracker-logs-${carId}.csv`;
}

/**
 * summarizeImport(parsed) -> {cars, logs, intervals}
 * Client-side preview of what POST /import would create, computed from the
 * parsed JSON of a v1 export. Throws an Error with a user-facing Ukrainian
 * message when the shape is wrong (shown as-is in the UI).
 */
// Kept in sync with the backend's SUPPORTED_SCHEMA_VERSIONS (app/services/export.py).
const SUPPORTED_SCHEMA_VERSIONS = [1, 2];

export function summarizeImport(data) {
  const invalid = () => new Error(i18n.t('apiBackup.notAnExport'));
  if (data == null || typeof data !== 'object' || Array.isArray(data)) throw invalid();
  if (!SUPPORTED_SCHEMA_VERSIONS.includes(data.schema_version)) {
    throw new Error(i18n.t('apiBackup.unsupportedVersion'));
  }
  if (!Array.isArray(data.cars)) throw invalid();
  let logs = 0;
  let intervals = 0;
  for (const car of data.cars) {
    if (car == null || typeof car !== 'object' || Array.isArray(car)) throw invalid();
    if (car.logs != null && !Array.isArray(car.logs)) throw invalid();
    if (car.intervals != null && !Array.isArray(car.intervals)) throw invalid();
    logs += car.logs ? car.logs.length : 0;
    intervals += car.intervals ? car.intervals.length : 0;
  }
  return { cars: data.cars.length, logs, intervals };
}

/**
 * Downloads the full JSON export (all cars, logs, intervals of the current
 * user; photos as metadata only) through the shared axios client and saves
 * it as kapot-tracker-export-YYYYMMDD.json.
 */
export async function downloadExport() {
  const { data } = await client.get('/export', { responseType: 'blob' });
  saveBlob(data, exportFilename());
}

export async function downloadCarCsv(carId) {
  const { data } = await client.get(`/cars/${carId}/export.csv`, { responseType: 'blob' });
  saveBlob(data, csvFilename(carId));
}

/**
 * Imports a parsed v1 export. Append-only on the backend: everything is
 * created as new records for the current user, existing data stays intact.
 */
export async function importBackup(payload) {
  const { data } = await client.post('/import', payload);
  return data; // {cars_created, logs_created, intervals_created}
}
