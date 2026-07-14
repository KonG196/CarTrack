import { describe, it, expect } from 'vitest';
import { formatMoney, formatKm, formatDate, monthLabel } from './format';

const NBSP = ' ';

describe('formatMoney', () => {
  it('groups thousands with a thin space and appends the hryvnia sign', () => {
    expect(formatMoney(1250)).toBe(`1${NBSP}250${NBSP}₴`);
  });

  it('handles millions', () => {
    expect(formatMoney(1234567)).toBe(`1${NBSP}234${NBSP}567${NBSP}₴`);
  });

  it('keeps two decimals when the value is fractional', () => {
    expect(formatMoney(1250.5)).toBe(`1${NBSP}250,50${NBSP}₴`);
  });

  it('drops decimals for whole numbers', () => {
    expect(formatMoney(40)).toBe(`40${NBSP}₴`);
  });

  it('handles zero and negatives', () => {
    expect(formatMoney(0)).toBe(`0${NBSP}₴`);
    expect(formatMoney(-500)).toBe(`-500${NBSP}₴`);
  });

  it('returns a dash for invalid input', () => {
    expect(formatMoney(null)).toBe('—');
    expect(formatMoney(undefined)).toBe('—');
    expect(formatMoney(NaN)).toBe('—');
  });
});

describe('formatKm', () => {
  it('groups thousands and appends км', () => {
    expect(formatKm(123456)).toBe(`123${NBSP}456${NBSP}км`);
  });

  it('rounds fractional values', () => {
    expect(formatKm(999.6)).toBe(`1${NBSP}000${NBSP}км`);
  });

  it('handles small values and invalid input', () => {
    expect(formatKm(42)).toBe(`42${NBSP}км`);
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
