import i18n from '../i18n';

// `value` is the stored fuel code (never localized); `label` is the Ukrainian
// display used as the fallback. English labels live in EN_LABELS and are chosen
// live by fuelKindLabel(), so a language switch relabels without a reload. Use
// fuelKindLabel(opt.value) for display rather than opt.label directly.
export const FUEL_KIND_OPTIONS = [
  { value: 'petrol', label: 'Бензин' },
  { value: 'diesel', label: 'Дизель' },
  { value: 'lpg', label: 'Газ (ГБО)' },
  { value: 'electric', label: 'Електро' },
];

const LABELS = Object.fromEntries(FUEL_KIND_OPTIONS.map((o) => [o.value, o.label]));

const EN_LABELS = {
  petrol: 'Petrol',
  diesel: 'Diesel',
  lpg: 'LPG',
  electric: 'Electric',
};

export function fuelKindLabel(kind) {
  if (String(i18n.language || 'en').startsWith('en')) return EN_LABELS[kind] || LABELS[kind] || kind;
  return LABELS[kind] || kind;
}

export function shouldShowFuelKind(car) {
  if (!car) return false;
  if (car.fuel_type === 'lpg') return true;
  return (car.fuel_kinds_used?.length ?? 0) > 1;
}

export const PRICE_CHART_MIN_POINTS = 3;

export function shouldShowPriceChart(priceHistory) {
  return (priceHistory?.length ?? 0) >= PRICE_CHART_MIN_POINTS;
}

export function priceChartKinds(priceHistory) {
  const kinds = [];
  for (const item of priceHistory || []) {
    if (item.fuel_kind && !kinds.includes(item.fuel_kind)) kinds.push(item.fuel_kind);
  }
  return kinds;
}

export function priceChartRows(priceHistory) {
  return (priceHistory || []).map((item, index) => ({
    key: index,
    date: item.date,
    [item.fuel_kind]: item.price_per_liter,
    [`${item.fuel_kind}__station`]: item.gas_station,
  }));
}

export function hasMixedKinds(byKind) {
  return Object.keys(byKind || {}).length > 1;
}

export function consumptionKinds(byKind) {
  return Object.entries(byKind || {})
    .sort(([, a], [, b]) => (b.total_liters ?? 0) - (a.total_liters ?? 0))
    .map(([kind]) => kind);
}

export function consumptionChartRows(byKind) {
  const rows = [];
  for (const [kind, stats] of Object.entries(byKind || {})) {
    for (const segment of stats.history || []) {
      rows.push({ date: segment.date, [kind]: segment.consumption_l_100km });
    }
  }
  return rows.sort((a, b) => String(a.date).localeCompare(String(b.date)));
}
