import client from './client';

export const TIRE_SEASONS = [
  { value: 'summer', label: 'Літні' },
  { value: 'winter', label: 'Зимові' },
  { value: 'all_season', label: 'Всесезонні' },
];

export function tireSeasonLabel(season) {
  return TIRE_SEASONS.find((s) => s.value === season)?.label || season;
}

export async function getTireSets(carId) {
  const { data } = await client.get(`/cars/${carId}/tires`);
  return data;
}

export async function getTireSeasonStatus(carId) {
  const { data } = await client.get(`/cars/${carId}/tires/season-status`);
  return data; // { changeover_season: 'winter'|'summer'|null, washer_changeover_due: bool }
}

export async function createTireSet(carId, payload) {
  const { data } = await client.post(`/cars/${carId}/tires`, payload);
  return data;
}

export async function updateTireSet(tireSetId, payload) {
  const { data } = await client.patch(`/tires/${tireSetId}`, payload);
  return data;
}

export async function deleteTireSet(tireSetId) {
  await client.delete(`/tires/${tireSetId}`);
}

export async function installTireSet(tireSetId) {
  const { data } = await client.post(`/tires/${tireSetId}/install`);
  return data;
}

export async function rotateTireSet(tireSetId) {
  const { data } = await client.post(`/tires/${tireSetId}/rotate`);
  return data;
}
