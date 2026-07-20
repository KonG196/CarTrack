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

describe('deriveRefuel — fills the one empty field from the other two', () => {
  it('total from liters + price', () => {
    expect(deriveRefuel({ liters: '40', pricePerLiter: '50', totalCost: '' })).toEqual({
      totalCost: '2000.00',
    });
  });

  it('price from liters + total', () => {
    expect(deriveRefuel({ liters: '40', pricePerLiter: '', totalCost: '2000' })).toEqual({
      pricePerLiter: '50.00',
    });
  });

  it('liters from price + total (the reported case: total + price/l → litres)', () => {
    expect(deriveRefuel({ liters: '', pricePerLiter: '50', totalCost: '2000' })).toEqual({
      liters: '40.00',
    });
  });

  it('accepts decimal comma input', () => {
    expect(deriveRefuel({ liters: '45,5', pricePerLiter: '54,99', totalCost: '' })).toEqual({
      totalCost: '2502.05',
    });
  });

  it('rounds to 2 decimals', () => {
    expect(deriveRefuel({ liters: '3', pricePerLiter: '', totalCost: '10' })).toEqual({
      pricePerLiter: '3.33',
    });
  });

  it('returns null with fewer than two values', () => {
    expect(deriveRefuel({ liters: '40', pricePerLiter: '', totalCost: '' })).toBeNull();
    expect(deriveRefuel({ liters: '', pricePerLiter: '', totalCost: '2000' })).toBeNull();
  });

  it('treats zero as missing', () => {
    expect(deriveRefuel({ liters: '0', pricePerLiter: '50', totalCost: '' })).toBeNull();
    expect(deriveRefuel({ liters: '0', pricePerLiter: '', totalCost: '2000' })).toBeNull();
  });

  it('ignores invalid text', () => {
    expect(deriveRefuel({ liters: '40', pricePerLiter: 'abc', totalCost: '' })).toBeNull();
  });
});

describe('deriveRefuel — all three present recomputes the least-recently edited', () => {
  it('with order [total, price] present, recomputes liters', () => {
    // user last typed total then price; litres is the stale one → t/p
    expect(
      deriveRefuel(
        { liters: '99', pricePerLiter: '50', totalCost: '2000' },
        ['totalCost', 'pricePerLiter'],
      ),
    ).toEqual({ liters: '40.00' });
  });

  it('with order [liters, price] present, recomputes total', () => {
    expect(
      deriveRefuel(
        { liters: '40', pricePerLiter: '60', totalCost: '999' },
        ['liters', 'pricePerLiter'],
      ),
    ).toEqual({ totalCost: '2400.00' });
  });

  it('with order [liters, total] present, recomputes price', () => {
    expect(
      deriveRefuel(
        { liters: '40', pricePerLiter: '999', totalCost: '2400' },
        ['totalCost', 'liters'],
      ),
    ).toEqual({ pricePerLiter: '60.00' });
  });
});
