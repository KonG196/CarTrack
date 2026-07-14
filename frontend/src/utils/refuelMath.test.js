import { describe, it, expect } from 'vitest';
import { num, computeRefuelUpdate } from './refuelMath';

describe('num', () => {
  it('parses plain decimals', () => {
    expect(num('45.5')).toBe(45.5);
    expect(num('40')).toBe(40);
  });

  it('normalizes decimal comma to dot', () => {
    expect(num('45,5')).toBe(45.5);
    expect(num('54,99')).toBe(54.99);
  });

  it('returns null for empty or invalid input', () => {
    expect(num('')).toBeNull();
    expect(num('abc')).toBeNull();
    expect(num(undefined)).toBeNull();
  });
});

describe('computeRefuelUpdate', () => {
  it('computes total from liters and price when liters change', () => {
    expect(
      computeRefuelUpdate('liters', { liters: '40', pricePerLiter: '50', totalCost: '' })
    ).toEqual({ totalCost: '2000.00' });
  });

  it('computes price from liters and total when liters change and price is empty', () => {
    expect(
      computeRefuelUpdate('liters', { liters: '40', pricePerLiter: '', totalCost: '2000' })
    ).toEqual({ pricePerLiter: '50.00' });
  });

  it('computes total from price and liters when price changes', () => {
    expect(
      computeRefuelUpdate('pricePerLiter', { liters: '40', pricePerLiter: '55.5', totalCost: '' })
    ).toEqual({ totalCost: '2220.00' });
  });

  it('computes liters from price and total when price changes and liters is empty', () => {
    expect(
      computeRefuelUpdate('pricePerLiter', { liters: '', pricePerLiter: '50', totalCost: '2000' })
    ).toEqual({ liters: '40.00' });
  });

  it('computes price from total and liters when total changes', () => {
    expect(
      computeRefuelUpdate('totalCost', { liters: '40', pricePerLiter: '', totalCost: '2000' })
    ).toEqual({ pricePerLiter: '50.00' });
  });

  it('computes liters from total and price when total changes and liters is empty', () => {
    expect(
      computeRefuelUpdate('totalCost', { liters: '', pricePerLiter: '50', totalCost: '2000' })
    ).toEqual({ liters: '40.00' });
  });

  // last-edited precedence: when all three fields are filled, the pair listed
  // first for the edited field wins (as originally implemented in AddEntry)
  it('editing liters with all fields filled recomputes total (price wins over total)', () => {
    expect(
      computeRefuelUpdate('liters', { liters: '30', pricePerLiter: '50', totalCost: '2000' })
    ).toEqual({ totalCost: '1500.00' });
  });

  it('editing price with all fields filled recomputes total', () => {
    expect(
      computeRefuelUpdate('pricePerLiter', { liters: '40', pricePerLiter: '60', totalCost: '2000' })
    ).toEqual({ totalCost: '2400.00' });
  });

  it('editing total with all fields filled recomputes price (liters win over price)', () => {
    expect(
      computeRefuelUpdate('totalCost', { liters: '40', pricePerLiter: '50', totalCost: '2400' })
    ).toEqual({ pricePerLiter: '60.00' });
  });

  it('accepts decimal comma input', () => {
    expect(
      computeRefuelUpdate('liters', { liters: '45,5', pricePerLiter: '54,99', totalCost: '' })
    ).toEqual({ totalCost: '2502.05' });
  });

  it('rounds the computed value to 2 decimals', () => {
    expect(
      computeRefuelUpdate('totalCost', { liters: '3', pricePerLiter: '', totalCost: '10' })
    ).toEqual({ pricePerLiter: '3.33' });
  });

  it('returns null when only one value is present', () => {
    expect(
      computeRefuelUpdate('liters', { liters: '40', pricePerLiter: '', totalCost: '' })
    ).toBeNull();
    expect(
      computeRefuelUpdate('totalCost', { liters: '', pricePerLiter: '', totalCost: '2000' })
    ).toBeNull();
  });

  it('treats zero values as missing (no computation)', () => {
    expect(
      computeRefuelUpdate('liters', { liters: '0', pricePerLiter: '50', totalCost: '' })
    ).toBeNull();
    expect(
      computeRefuelUpdate('pricePerLiter', { liters: '0', pricePerLiter: '50', totalCost: '' })
    ).toBeNull();
  });

  it('ignores invalid text in the other fields', () => {
    expect(
      computeRefuelUpdate('liters', { liters: '40', pricePerLiter: 'abc', totalCost: '' })
    ).toBeNull();
  });
});
