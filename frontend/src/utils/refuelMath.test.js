import { describe, it, expect } from 'vitest';
import { num, deriveRefuel } from './refuelMath';

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

describe('deriveRefuel — computes only the field the user did NOT provide', () => {
  it('user owns liters + price → total is computed', () => {
    expect(
      deriveRefuel({ liters: '40', pricePerLiter: '50', totalCost: '' }, ['liters', 'pricePerLiter']),
    ).toEqual({ totalCost: '2000.00' });
  });

  it('user owns liters + total → price is computed', () => {
    expect(
      deriveRefuel({ liters: '40', pricePerLiter: '', totalCost: '2000' }, ['liters', 'totalCost']),
    ).toEqual({ pricePerLiter: '50.00' });
  });

  it('user owns price + total → litres is computed (the reported case)', () => {
    expect(
      deriveRefuel({ liters: '', pricePerLiter: '50', totalCost: '2000' }, ['pricePerLiter', 'totalCost']),
    ).toEqual({ liters: '40.00' });
  });

  it('overwrites a stale value in the non-owned field (not the user’s own)', () => {
    // liters holds junk but the user only owns price+total → liters is recomputed
    expect(
      deriveRefuel({ liters: '999', pricePerLiter: '50', totalCost: '2000' }, ['pricePerLiter', 'totalCost']),
    ).toEqual({ liters: '40.00' });
  });

  it('never touches a field the user filled themselves (all three owned → null)', () => {
    expect(
      deriveRefuel({ liters: '40', pricePerLiter: '50', totalCost: '9999' }, ['liters', 'pricePerLiter', 'totalCost']),
    ).toBeNull();
  });

  it('does nothing with fewer than two owned inputs', () => {
    expect(deriveRefuel({ liters: '40', pricePerLiter: '', totalCost: '' }, ['liters'])).toBeNull();
    expect(deriveRefuel({ liters: '40', pricePerLiter: '50', totalCost: '' }, [])).toBeNull();
  });

  it('does nothing when an owned input is missing or zero', () => {
    expect(
      deriveRefuel({ liters: '0', pricePerLiter: '50', totalCost: '' }, ['liters', 'pricePerLiter']),
    ).toBeNull();
    expect(
      deriveRefuel({ liters: '', pricePerLiter: 'abc', totalCost: '2000' }, ['pricePerLiter', 'totalCost']),
    ).toBeNull();
  });

  it('accepts decimal comma and rounds to 2 decimals', () => {
    expect(
      deriveRefuel({ liters: '45,5', pricePerLiter: '54,99', totalCost: '' }, ['liters', 'pricePerLiter']),
    ).toEqual({ totalCost: '2502.05' });
    expect(
      deriveRefuel({ liters: '3', pricePerLiter: '', totalCost: '10' }, ['liters', 'totalCost']),
    ).toEqual({ pricePerLiter: '3.33' });
  });
});
