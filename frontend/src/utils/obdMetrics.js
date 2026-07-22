import i18n from '../i18n';

// Keys are OBD metric codes (never localized); values are the Ukrainian display
// labels used as the fallback. English labels live in EN_METRIC_LABELS and are
// picked live by metricLabel().
export const METRIC_LABELS = {
  dpf_soot_mass: 'Маса сажі DPF',
  dpf_distance_since_regen: 'Пробіг з останньої регенерації',
  injector_correction_1: 'Корекція форсунки 1',
  injector_correction_2: 'Корекція форсунки 2',
  injector_correction_3: 'Корекція форсунки 3',
  injector_correction_4: 'Корекція форсунки 4',
  battery_voltage: 'Напруга бортмережі',
  coolant_temp: 'Температура ОЖ',
  boost_pressure: 'Тиск наддуву',
  engine_rpm: 'Оберти двигуна',
  vehicle_speed: 'Швидкість',
  intake_temp: 'Температура впуску',
  fuel_rail_pressure: 'Тиск у паливній рампі',
};

const EN_METRIC_LABELS = {
  dpf_soot_mass: 'DPF soot mass',
  dpf_distance_since_regen: 'Distance since last regen',
  injector_correction_1: 'Injector 1 correction',
  injector_correction_2: 'Injector 2 correction',
  injector_correction_3: 'Injector 3 correction',
  injector_correction_4: 'Injector 4 correction',
  battery_voltage: 'Battery voltage',
  coolant_temp: 'Coolant temp',
  boost_pressure: 'Boost pressure',
  engine_rpm: 'Engine RPM',
  vehicle_speed: 'Speed',
  intake_temp: 'Intake temp',
  fuel_rail_pressure: 'Fuel rail pressure',
};

const METRIC_ORDER = [
  'dpf_soot_mass',
  'dpf_distance_since_regen',
  'injector_correction_1',
  'injector_correction_2',
  'injector_correction_3',
  'injector_correction_4',
  'battery_voltage',
  'coolant_temp',
  'boost_pressure',
  'fuel_rail_pressure',
  'intake_temp',
  'engine_rpm',
  'vehicle_speed',
];

export function metricLabel(key) {
  if (String(i18n.language || 'en').startsWith('en')) return EN_METRIC_LABELS[key] || METRIC_LABELS[key] || key;
  return METRIC_LABELS[key] || key;
}

export function sortMetrics(metrics) {
  const rank = (metric) => {
    const index = METRIC_ORDER.indexOf(metric.key);
    return index === -1 ? METRIC_ORDER.length : index;
  };
  return [...metrics].sort((a, b) => rank(a) - rank(b));
}

export function chartPoints(series) {
  return (series || []).map(([t, value]) => ({ t, value }));
}

export function formatDuration(seconds) {
  const en = String(i18n.language || 'en').startsWith('en');
  const s = en ? 's' : 'с';
  const m = en ? 'min' : 'хв';
  const total = Math.round(Number(seconds) || 0);
  if (total < 60) return `${total} ${s}`;
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes} ${m} ${String(rest).padStart(2, '0')} ${s}`;
}
