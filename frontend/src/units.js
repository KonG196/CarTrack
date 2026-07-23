// Display unit system. Like the display currency, this is a presentation choice:
// every value is STORED in metric (km, litres, l/100km) and only converted for
// display / parsed back to metric on input. Keep in sync with backend
// `app/units.py`.

export const UNIT_SYSTEMS = [
  { code: 'metric', name: 'Metric', distance: 'km', volume: 'L', consumption: 'L/100 km' },
  { code: 'imperial', name: 'Imperial', distance: 'mi', volume: 'gal', consumption: 'mpg' },
];

export const DEFAULT_UNIT_SYSTEM = 'metric';
export const UNITS_KEY = 'kapot_units';

const BY_CODE = Object.fromEntries(UNIT_SYSTEMS.map((u) => [u.code, u]));

export function normalizeUnitSystem(value, fallback = DEFAULT_UNIT_SYSTEM) {
  const code = String(value || '').trim().toLowerCase();
  return BY_CODE[code] ? code : fallback;
}

export function unitInfo(code) {
  return BY_CODE[normalizeUnitSystem(code)];
}

// --- Conversion factors (exact where it matters). US gallon. ---
export const KM_PER_MILE = 1.609344;
export const LITRES_PER_US_GALLON = 3.785411784;
// mpg = miles per US gallon; l/100km and mpg are reciprocals scaled by this.
const MPG_FROM_L100 = 235.214583; // 100 * KM_PER_MILE / LITRES_PER_US_GALLON, ×... ≈ 235.2146

export const isImperial = (code) => normalizeUnitSystem(code) === 'imperial';

// Stored metric → displayed value in the chosen system.
export function distanceFromKm(km, system) {
  const n = Number(km);
  if (!Number.isFinite(n)) return null;
  return isImperial(system) ? n / KM_PER_MILE : n;
}
export function volumeFromLitres(litres, system) {
  const n = Number(litres);
  if (!Number.isFinite(n)) return null;
  return isImperial(system) ? n / LITRES_PER_US_GALLON : n;
}
// l/100km → mpg (imperial) or unchanged (metric). Higher mpg = better, so it's
// an inverse relationship, not a linear scale.
export function consumptionFromL100(l100, system) {
  const n = Number(l100);
  if (!Number.isFinite(n) || n <= 0) return null;
  return isImperial(system) ? MPG_FROM_L100 / n : n;
}
// Cost per stored-km → cost per displayed-distance.
export function costPerDistanceFromPerKm(perKm, system) {
  const n = Number(perKm);
  if (!Number.isFinite(n)) return null;
  return isImperial(system) ? n * KM_PER_MILE : n;
}

// Displayed input (the chosen system) → stored metric.
export function kmFromDistance(value, system) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return isImperial(system) ? n * KM_PER_MILE : n;
}
export function litresFromVolume(value, system) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return isImperial(system) ? n * LITRES_PER_US_GALLON : n;
}
