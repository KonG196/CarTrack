import { describe, it, expect } from 'vitest';
import { logTitle, authorLabel } from './LogTimelineItem';

describe('logTitle', () => {
  it('names a refuel by its station', () => {
    expect(logTitle({ type: 'refuel', refuel: { gas_station: 'OKKO' } })).toBe('Заправка · OKKO');
    expect(logTitle({ type: 'refuel', refuel: { gas_station: null } })).toBe('Заправка');
  });

  it('names maintenance by its first items', () => {
    expect(logTitle({ type: 'maintenance', maintenance: { items: ['Олива двигуна'] } })).toBe(
      'ТО · Олива двигуна'
    );
  });

  it('names a repair by category and part', () => {
    expect(
      logTitle({ type: 'repair', repair: { category: 'Гальма', part_name: 'Колодки' } })
    ).toBe('Ремонт · Гальма · Колодки');
  });

  it('names an expense by its category', () => {
    expect(logTitle({ type: 'expense', expense: { category: 'Мийка' }, notes: null })).toBe(
      'Витрата · Мийка'
    );
  });

  it('prefers the category over the notes', () => {
    // The notes still render on their own line under the title, so repeating
    // them in the title would only cost the category its place.
    expect(
      logTitle({ type: 'expense', expense: { category: 'Паркування' }, notes: 'на Стуса' })
    ).toBe('Витрата · Паркування');
  });

  it('falls back to the notes for a legacy expense with no category', () => {
    // Pre-0004 rows carry no expense details at all.
    expect(logTitle({ type: 'expense', expense: null, notes: 'на Стуса' })).toBe(
      'Витрата · на Стуса'
    );
  });

  it('names a bare expense with no category and no notes', () => {
    expect(logTitle({ type: 'expense', expense: null, notes: null })).toBe('Витрата');
  });
});

describe('authorLabel', () => {
  it('names the author of an entry', () => {
    expect(authorLabel({ author: { id: 2, label: 'olha' } })).toBe('olha');
  });

  it('has no name for a legacy entry', () => {
    expect(authorLabel({ author: null })).toBe(null);
    expect(authorLabel({})).toBe(null);
    expect(authorLabel(null)).toBe(null);
  });

  it('has no name when the author carries an empty label', () => {
    expect(authorLabel({ author: { id: 2, label: '' } })).toBe(null);
  });
});
