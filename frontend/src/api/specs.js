import client from './client';

export const SPEC_CATEGORIES = [
  'Моменти затяжки',
  'Рідини та обʼєми',
  'Допуски',
  'Інше',
];

export async function getSpecs(carId) {
  const { data } = await client.get(`/cars/${carId}/specs`);
  return data;
}

export async function createSpec(carId, payload) {
  const { data } = await client.post(`/cars/${carId}/specs`, payload);
  return data;
}

export async function updateSpec(specId, payload) {
  const { data } = await client.patch(`/specs/${specId}`, payload);
  return data;
}

export async function deleteSpec(specId) {
  await client.delete(`/specs/${specId}`);
}

export async function applySpecPreset(carId, key) {
  const { data } = await client.post(`/cars/${carId}/specs/preset`, null, { params: { key } });
  return data;
}

export function groupSpecsByCategory(specs) {
  const groups = new Map(SPEC_CATEGORIES.map((category) => [category, []]));
  specs.forEach((spec) => {
    if (!groups.has(spec.category)) groups.set(spec.category, []);
    groups.get(spec.category).push(spec);
  });
  return [...groups.entries()]
    .filter(([, rows]) => rows.length > 0)
    .map(([category, rows]) => ({ category, specs: rows }));
}
