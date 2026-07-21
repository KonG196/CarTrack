import { describe, it, expect } from 'vitest';
import { formatMoney, formatMoneyCompact, formatKm, formatDate, monthLabel } from './format';

const THIN = '\u202F'; // narrow no-break space used to group thousands
const UNIT = '\u00A0'; // no-break space between the number and its unit

describe('formatMoney', () => {
  it('groups thousands with a thin space and appends the hryvnia sign', () => {
    expect(formatMoney(1250)).toBe(`1${THIN}250${UNIT}₴`);
  });

  it('handles millions', () => {
    expect(formatMoney(1234567)).toBe(`1${THIN}234${THIN}567${UNIT}₴`);
  });

  it('keeps two decimals when the value is fractional', () => {
    expect(formatMoney(1250.5)).toBe(`1${THIN}250,50${UNIT}₴`);
  });

  it('drops decimals for whole numbers', () => {
    expect(formatMoney(40)).toBe(`40${UNIT}₴`);
  });

  it('handles zero and negatives', () => {
    expect(formatMoney(0)).toBe(`0${UNIT}₴`);
    expect(formatMoney(-500)).toBe(`-500${UNIT}₴`);
  });

  it('returns a dash for invalid input', () => {
    expect(formatMoney(null)).toBe('—');
    expect(formatMoney(undefined)).toBe('—');
    expect(formatMoney(NaN)).toBe('—');
  });
});

describe('formatMoneyCompact', () => {
  it('keeps small sums exact but drops kopecks', () => {
    expect(formatMoneyCompact(850)).toBe(`850${UNIT}₴`);
    expect(formatMoneyCompact(8350)).toBe(`8${THIN}350${UNIT}₴`);
    expect(formatMoneyCompact(27037.5)).toBe(`27${THIN}038${UNIT}₴`);
  });

  it('collapses hundreds of thousands to тис', () => {
    expect(formatMoneyCompact(156200)).toBe(`156${UNIT}тис${UNIT}₴`);
  });

  it('collapses millions to млн', () => {
    expect(formatMoneyCompact(1200000)).toBe(`1,2${UNIT}млн${UNIT}₴`);
    expect(formatMoneyCompact(12000000)).toBe(`12${UNIT}млн${UNIT}₴`);
  });

  it('returns a dash for invalid input', () => {
    expect(formatMoneyCompact(null)).toBe('—');
    expect(formatMoneyCompact(NaN)).toBe('—');
  });
});

describe('formatKm', () => {
  it('groups thousands and appends км', () => {
    expect(formatKm(123456)).toBe(`123${THIN}456${UNIT}км`);
  });

  it('rounds fractional values', () => {
    expect(formatKm(999.6)).toBe(`1${THIN}000${UNIT}км`);
  });

  it('handles small values and invalid input', () => {
    expect(formatKm(42)).toBe(`42${UNIT}км`);
    expect(formatKm(null)).toBe('—');
  });
});

describe('formatDate', () => {
  it('converts ISO date to DD.MM.YYYY', () => {
    expect(formatDate('2026-07-14')).toBe('14.07.2026');
  });

  it('accepts ISO datetime strings', () => {
    expect(formatDate('2026-01-05T12:30:00Z')).toBe('05.01.2026');
  });

  it('returns a dash for empty input', () => {
    expect(formatDate(null)).toBe('—');
    expect(formatDate('')).toBe('—');
  });
});

describe('monthLabel', () => {
  it('converts YYYY-MM to short Ukrainian month + year', () => {
    expect(monthLabel('2026-07')).toBe('лип 2026');
    expect(monthLabel('2025-01')).toBe('січ 2025');
    expect(monthLabel('2025-12')).toBe('гру 2025');
  });

  it('returns a dash for empty input', () => {
    expect(monthLabel(null)).toBe('—');
  });
});
