import { describe, it, expect } from 'vitest';
import {
  tireAgeYears,
  tireAgeLevel,
  tireSeasonMismatch,
  TIRE_AGE_WARN_YEARS,
  TIRE_AGE_CRIT_YEARS,
} from './tireAge';

const NOW = new Date('2026-07-21T00:00:00Z');

describe('tireAgeYears', () => {
  it('uses the DOT production year', () => {
    expect(tireAgeYears({ dot_year: 2019 }, NOW)).toBe(7);
  });

  it('falls back to the purchase year when no DOT', () => {
    expect(tireAgeYears({ dot_year: null, purchased_at: '2018-03-01' }, NOW)).toBe(8);
  });

  it('prefers DOT over purchase date', () => {
    expect(tireAgeYears({ dot_year: 2024, purchased_at: '2015-01-01' }, NOW)).toBe(2);
  });

  it('reads the purchase year timezone-independently (Jan 1 matches the backend)', () => {
    // new Date('2020-01-01').getFullYear() would roll back a year in negative-UTC
    // zones; slicing the ISO string keeps it aligned with backend purchased_at.year.
    expect(tireAgeYears({ dot_year: null, purchased_at: '2020-01-01' }, NOW)).toBe(6);
  });

  it('is null when neither is known', () => {
    expect(tireAgeYears({ dot_year: null, purchased_at: null }, NOW)).toBeNull();
    expect(tireAgeYears(null, NOW)).toBeNull();
  });

  it('never goes negative for a future year', () => {
    expect(tireAgeYears({ dot_year: 2030 }, NOW)).toBe(0);
  });
});

describe('tireAgeLevel', () => {
  it('classifies by the warn/crit thresholds', () => {
    expect(tireAgeLevel(null)).toBeNull();
    expect(tireAgeLevel(TIRE_AGE_WARN_YEARS - 1)).toBe('ok');
    expect(tireAgeLevel(TIRE_AGE_WARN_YEARS)).toBe('warn');
    expect(tireAgeLevel(TIRE_AGE_CRIT_YEARS - 1)).toBe('warn');
    expect(tireAgeLevel(TIRE_AGE_CRIT_YEARS)).toBe('crit');
  });
});

describe('tireSeasonMismatch', () => {
  it('is false outside any changeover window', () => {
    expect(tireSeasonMismatch(null, { season: 'summer', is_installed: true })).toBe(false);
  });

  it('flags a summer set when winter is due', () => {
    expect(tireSeasonMismatch('winter', { season: 'summer' })).toBe(true);
  });

  it('is fine when the mounted set already matches', () => {
    expect(tireSeasonMismatch('winter', { season: 'winter' })).toBe(false);
  });

  it('treats all-season as always fine', () => {
    expect(tireSeasonMismatch('winter', { season: 'all_season' })).toBe(false);
  });

  it('flags when nothing is mounted', () => {
    expect(tireSeasonMismatch('summer', undefined)).toBe(true);
  });
});
