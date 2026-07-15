import { describe, it, expect } from 'vitest';
import { entryWarnings, lastEntryHint } from './entryWarnings';

const TODAY = '2026-07-14';
// formatKm groups thousands with a narrow no-break space, not a plain one.
const NNBSP = ' ';

const context = {
  recent_stations: ['OKKO', 'WOG'],
  last_price_per_liter: 54.99,
  last_refuel_odometer: 123000,
  last_entry_odometer: 123456,
  last_entry_date: '2026-07-10',
};

describe('entryWarnings', () => {
  it('warns when the odometer is below the last entry', () => {
    const warnings = entryWarnings(
      { type: 'refuel', odometer: '120000', date: TODAY, context },
      TODAY
    );
    expect(warnings).toEqual([
      `Менше за останній запис (123${NNBSP}456${NNBSP}км) — це історичний запис?`,
    ]);
  });

  it('warns when a refuel keeps the prefilled odometer untouched', () => {
    const warnings = entryWarnings(
      { type: 'refuel', odometer: '123456', date: TODAY, context },
      TODAY
    );
    expect(warnings).toEqual([
      'Пробіг не змінився з останнього запису — розхід не порахується',
    ]);
  });

  it('does not warn about an unchanged odometer for other types', () => {
    // Only a refuel needs the distance — a car wash at the same odometer is fine.
    expect(
      entryWarnings({ type: 'expense', odometer: '123456', date: TODAY, context }, TODAY)
    ).toEqual([]);
  });

  it('warns about a future date', () => {
    expect(
      entryWarnings({ type: 'refuel', odometer: '123500', date: '2026-07-15', context }, TODAY)
    ).toEqual(['Дата в майбутньому']);
  });

  it('does not warn about today', () => {
    expect(
      entryWarnings({ type: 'refuel', odometer: '123500', date: TODAY, context }, TODAY)
    ).toEqual([]);
  });

  it('combines the odometer and date warnings', () => {
    expect(
      entryWarnings({ type: 'refuel', odometer: '100', date: '2027-01-01', context }, TODAY)
    ).toEqual([
      `Менше за останній запис (123${NNBSP}456${NNBSP}км) — це історичний запис?`,
      'Дата в майбутньому',
    ]);
  });

  it('stays silent while the context is missing (edit mode, first car)', () => {
    expect(entryWarnings({ type: 'refuel', odometer: '100', date: TODAY, context: null }, TODAY))
      .toEqual([]);
  });

  it('still checks the date without a context', () => {
    expect(
      entryWarnings({ type: 'refuel', odometer: '100', date: '2030-01-01', context: null }, TODAY)
    ).toEqual(['Дата в майбутньому']);
  });

  it('stays silent for a car whose very first entry this is', () => {
    const empty = { recent_stations: [], last_entry_odometer: null, last_entry_date: null };
    expect(
      entryWarnings({ type: 'refuel', odometer: '0', date: TODAY, context: empty }, TODAY)
    ).toEqual([]);
  });

  it('ignores an empty or invalid odometer', () => {
    expect(entryWarnings({ type: 'refuel', odometer: '', date: TODAY, context }, TODAY)).toEqual([]);
    expect(
      entryWarnings({ type: 'refuel', odometer: 'abc', date: TODAY, context }, TODAY)
    ).toEqual([]);
  });
});

describe('lastEntryHint', () => {
  it('shows the last entry odometer and date', () => {
    expect(lastEntryHint(context)).toBe(
      `Останній запис: 123${NNBSP}456${NNBSP}км · 10.07.2026`
    );
  });

  it('shows the odometer alone when the date is missing', () => {
    expect(lastEntryHint({ last_entry_odometer: 500, last_entry_date: null })).toBe(
      `Останній запис: 500${NNBSP}км`
    );
  });

  it('is empty without a context or for a car with no entries', () => {
    expect(lastEntryHint(null)).toBe('');
    expect(lastEntryHint({ last_entry_odometer: null, last_entry_date: null })).toBe('');
  });
});
