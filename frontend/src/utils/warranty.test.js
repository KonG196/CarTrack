import { describe, it, expect } from 'vitest';
import { warrantyStatus } from './warranty';

const NOW = new Date('2026-07-21T12:00:00Z');

describe('warrantyStatus', () => {
  it('is null without any warranty', () => {
    expect(warrantyStatus({ warranty_months: null, warranty_km: null })).toBeNull();
    expect(warrantyStatus(null)).toBeNull();
  });

  it('is active within the months window', () => {
    const w = warrantyStatus({ warranty_months: 12, warranty_km: null }, { repairDate: '2026-03-01' }, NOW);
    expect(w.active).toBe(true);
    expect(w.expiry.getFullYear()).toBe(2027);
  });

  it('is expired past the months window', () => {
    const w = warrantyStatus({ warranty_months: 6, warranty_km: null }, { repairDate: '2025-01-01' }, NOW);
    expect(w.active).toBe(false);
  });

  it('is active within km and reports km left', () => {
    const w = warrantyStatus(
      { warranty_months: null, warranty_km: 20000 },
      { repairOdometer: 100000, currentOdometer: 105000 },
      NOW,
    );
    expect(w.active).toBe(true);
    expect(w.kmLeft).toBe(15000);
  });

  it('is expired when the km are used up', () => {
    const w = warrantyStatus(
      { warranty_months: null, warranty_km: 10000 },
      { repairOdometer: 100000, currentOdometer: 115000 },
      NOW,
    );
    expect(w.active).toBe(false);
    expect(w.kmLeft).toBe(-5000);
  });

  it('needs BOTH months and km to remain when both are set', () => {
    // time still ok (until 2028) but the km are exhausted -> not covered
    const w = warrantyStatus(
      { warranty_months: 24, warranty_km: 10000 },
      { repairDate: '2026-01-01', repairOdometer: 100000, currentOdometer: 120000 },
      NOW,
    );
    expect(w.active).toBe(false);
  });
});
