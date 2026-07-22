import client from './client';
import i18n from '../i18n';

// `value` is the stored season code (never localized); `label` is resolved live
// via i18n on access so a language switch relabels without a reload.
export const TIRE_SEASONS = [
  { value: 'summer', get label() { return i18n.t('apiTires.summer'); } },
  { value: 'winter', get label() { return i18n.t('apiTires.winter'); } },
  { value: 'all_season', get label() { return i18n.t('apiTires.allSeason'); } },
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
