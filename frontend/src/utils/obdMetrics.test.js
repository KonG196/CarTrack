import { describe, it, expect } from 'vitest';
import { metricLabel, sortMetrics, chartPoints, formatDuration } from './obdMetrics';

describe('metricLabel', () => {
  it('names the canonical metrics in Ukrainian', () => {
    expect(metricLabel('dpf_soot_mass')).toBe('Маса сажі DPF');
    expect(metricLabel('injector_correction_3')).toBe('Корекція форсунки 3');
    expect(metricLabel('battery_voltage')).toBe('Напруга бортмережі');
  });

  it('shows an unknown key as it is instead of hiding it', () => {
    expect(metricLabel('vendor_pid_42')).toBe('vendor_pid_42');
  });
});

describe('sortMetrics', () => {
  it('puts what the owner came for first', () => {
    const sorted = sortMetrics([
      { key: 'vehicle_speed' },
      { key: 'battery_voltage' },
      { key: 'dpf_soot_mass' },
    ]);
    expect(sorted.map((m) => m.key)).toEqual([
      'dpf_soot_mass',
      'battery_voltage',
      'vehicle_speed',
    ]);
  });

  it('keeps unknown metrics, at the end', () => {
    const sorted = sortMetrics([{ key: 'vendor_pid' }, { key: 'dpf_soot_mass' }]);
    expect(sorted.map((m) => m.key)).toEqual(['dpf_soot_mass', 'vendor_pid']);
  });

  it('does not mutate the input', () => {
    const metrics = [{ key: 'vehicle_speed' }, { key: 'dpf_soot_mass' }];
    sortMetrics(metrics);
    expect(metrics[0].key).toBe('vehicle_speed');
  });
});

describe('chartPoints', () => {
  it('maps the stored pairs onto recharts points', () => {
    expect(chartPoints([[0, 18.4], [1.5, 18.6]])).toEqual([
      { t: 0, value: 18.4 },
      { t: 1.5, value: 18.6 },
    ]);
  });

  it('survives a missing series', () => {
    expect(chartPoints(undefined)).toEqual([]);
  });
});

describe('formatDuration', () => {
  it('reads seconds under a minute as seconds', () => {
    expect(formatDuration(42)).toBe('42 с');
  });

  it('reads longer logs as minutes and seconds', () => {
    expect(formatDuration(125)).toBe('2 хв 05 с');
    expect(formatDuration(600)).toBe('10 хв 00 с');
  });

  it('survives a missing duration', () => {
    expect(formatDuration(null)).toBe('0 с');
  });
});
