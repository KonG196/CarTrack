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
  const total = Math.round(Number(seconds) || 0);
  if (total < 60) return `${total} с`;
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes} хв ${String(rest).padStart(2, '0')} с`;
}
