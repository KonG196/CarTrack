import { describe, it, expect } from 'vitest';
import { expenseCategoryRows, shouldShowStations } from './analyticsBreakdown';

describe('expenseCategoryRows', () => {
  it('sorts categories by spend descending', () => {
    expect(
      expenseCategoryRows({ Мийка: 300, Паркування: 1200, Штраф: 500 })
    ).toEqual([
      { name: 'Паркування', total: 1200 },
      { name: 'Штраф', total: 500 },
      { name: 'Мийка', total: 300 },
    ]);
  });

  it('breaks ties by name so the order never jitters between renders', () => {
    expect(expenseCategoryRows({ Бета: 100, Альфа: 100 })).toEqual([
      { name: 'Альфа', total: 100 },
      { name: 'Бета', total: 100 },
    ]);
  });

  it('returns an empty list for missing or empty input', () => {
    expect(expenseCategoryRows(undefined)).toEqual([]);
    expect(expenseCategoryRows(null)).toEqual([]);
    expect(expenseCategoryRows({})).toEqual([]);
  });
});

describe('shouldShowStations', () => {
  it('hides the list until there are at least two refuels', () => {
    expect(shouldShowStations([])).toBe(false);
    expect(shouldShowStations([{ name: 'OKKO', refuels: 1 }])).toBe(false);
  });

  it('shows the list once two refuels exist, even at one station', () => {
    expect(shouldShowStations([{ name: 'OKKO', refuels: 2 }])).toBe(true);
    expect(
      shouldShowStations([
        { name: 'OKKO', refuels: 1 },
        { name: 'WOG', refuels: 1 },
      ])
    ).toBe(true);
  });

  it('tolerates missing or malformed input', () => {
    expect(shouldShowStations(undefined)).toBe(false);
    expect(shouldShowStations(null)).toBe(false);
    expect(shouldShowStations([{ name: 'OKKO' }])).toBe(false);
  });
});
