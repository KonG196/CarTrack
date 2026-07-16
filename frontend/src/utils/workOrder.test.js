import { describe, expect, it } from 'vitest';

import { COMMON_MAINTENANCE_ITEMS } from './entryForm';
import { describeWorkOrder, matchCanonicalItem, workOrderToFormValues } from './workOrder';

// The real order from the Golf's service passport, as the backend returns it.
const ALEX_SO_SCAN = {
  items: [
    'Олива моторна 5W-30 5л',
    'Фільтр масляний ЦБ012317',
    'Фільтр паливний ЦБ002028',
    'Фільтр повітряний Ц5002028',
    'Фільтр салонний ЦБ115092',
    'Рідина гальмівна 1л',
    'Гвинт різьбовий М14',
  ],
  parts_cost: 7542.0,
  labor_cost: 681.38,
  total_cost: 8223.38,
  date: '2022-12-03',
  confident: true,
  raw_text: '...',
};

describe('matchCanonicalItem', () => {
  it('reads what the shop wrote as what the form calls it', () => {
    expect(matchCanonicalItem('Олива моторна 5W-30 5л')).toBe('Олива двигуна');
    expect(matchCanonicalItem('Фільтр масляний ЦБ012317')).toBe('Масляний фільтр');
    expect(matchCanonicalItem('Фільтр паливний ЦБ002028')).toBe('Паливний фільтр');
    expect(matchCanonicalItem('Фільтр повітряний Ц5002028')).toBe('Повітряний фільтр');
    expect(matchCanonicalItem('Фільтр салонний ЦБ115092')).toBe('Салонний фільтр');
    expect(matchCanonicalItem('Рідина гальмівна 1л')).toBe('Гальмівна рідина');
  });

  it('does not mistake an oil filter for oil', () => {
    // Both lines say «масл». One is a filter, one is four litres of oil, and
    // ticking the wrong box moves the wrong service interval.
    expect(matchCanonicalItem('Фільтр масляний')).toBe('Масляний фільтр');
    expect(matchCanonicalItem('Мастило моторне Castrol 5W-30')).toBe('Олива двигуна');
  });

  it('reads a shop that writes in Russian', () => {
    expect(matchCanonicalItem('Фильтр воздушный')).toBe('Повітряний фільтр');
    expect(matchCanonicalItem('Жидкость тормозная DOT-4')).toBe('Гальмівна рідина');
  });

  it('leaves alone what the form has no box for', () => {
    expect(matchCanonicalItem('Гвинт різьбовий М14')).toBeNull();
    expect(matchCanonicalItem('Заміна комплекту ГРМ')).toBeNull();
    expect(matchCanonicalItem('')).toBeNull();
    expect(matchCanonicalItem(null)).toBeNull();
  });

  it('only ever names a box the form actually has', () => {
    for (const raw of ALEX_SO_SCAN.items) {
      const hit = matchCanonicalItem(raw);
      if (hit) expect(COMMON_MAINTENANCE_ITEMS).toContain(hit);
    }
  });
});

describe('workOrderToFormValues', () => {
  it('fills the card from the order', () => {
    const values = workOrderToFormValues(ALEX_SO_SCAN);
    expect(values.partsCost).toBe('7542.00');
    expect(values.laborCost).toBe('681.38');
    expect(values.totalCost).toBe('8223.38');
    expect(values.date).toBe('2022-12-03');
  });

  it('ticks the six known boxes and keeps the screw as a chip', () => {
    const values = workOrderToFormValues(ALEX_SO_SCAN);
    expect(values.checkedItems).toEqual([
      'Олива двигуна',
      'Масляний фільтр',
      'Паливний фільтр',
      'Повітряний фільтр',
      'Салонний фільтр',
      'Гальмівна рідина',
      'Гвинт різьбовий М14',
    ]);
    expect(values.customItems).toEqual(['Гвинт різьбовий М14']);
  });

  it('never ticks the same box twice', () => {
    // A shop that bills oil on two lines (5 l + 1 l top-up) still serviced the
    // oil once.
    const values = workOrderToFormValues({
      items: ['Олива моторна 5W-30 5л', 'Олива моторна 5W-30 1л'],
    });
    expect(values.checkedItems).toEqual(['Олива двигуна']);
  });

  it('says nothing rather than blanking what the user typed', () => {
    const values = workOrderToFormValues({ items: [], total_cost: null, date: null });
    expect(values.totalCost).toBeNull();
    expect(values.partsCost).toBeNull();
    expect(values.laborCost).toBeNull();
    expect(values.date).toBeNull();
    expect(values.checkedItems).toEqual([]);
  });

  it('survives an empty response', () => {
    expect(workOrderToFormValues(undefined).checkedItems).toEqual([]);
    expect(workOrderToFormValues({}).customItems).toEqual([]);
  });
});

describe('describeWorkOrder', () => {
  it('reports what was read so a wrong scan is caught before saving', () => {
    expect(describeWorkOrder(ALEX_SO_SCAN)).toBe('7 позицій, 8223.38 грн');
  });

  it('is empty when nothing was read', () => {
    expect(describeWorkOrder({ items: [] })).toBe('');
  });
});
