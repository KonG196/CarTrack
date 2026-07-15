import { describe, it, expect } from 'vitest';
import {
  emptyCompleteValues,
  sumCostTotal,
  validateCompleteValues,
  completeValuesToPayload,
} from './completeForm';
import { todayIso } from './entryForm';

const car = { id: 1, brand: 'Skoda', model: 'Octavia', current_odometer: 123456 };
const interval = { id: 9, title: 'Олива двигуна', interval_km: 10000 };

describe('emptyCompleteValues', () => {
  it('defaults the odometer to the car current odometer', () => {
    expect(emptyCompleteValues({ car, interval }).odometer).toBe('123456');
  });

  it('defaults the date to today', () => {
    expect(emptyCompleteValues({ car, interval }).date).toBe(todayIso());
  });

  it('defaults the cost to 0 and the optional fields to empty', () => {
    const values = emptyCompleteValues({ car, interval });
    expect(values.totalCost).toBe('0');
    expect(values.partsCost).toBe('');
    expect(values.laborCost).toBe('');
    expect(values.notes).toBe('');
  });

  it('seeds the logged items with the interval title', () => {
    expect(emptyCompleteValues({ car, interval }).items).toEqual(['Олива двигуна']);
  });

  it('tolerates a missing car and a missing interval', () => {
    const values = emptyCompleteValues({});
    expect(values.odometer).toBe('');
    expect(values.items).toEqual([]);
  });
});

describe('sumCostTotal', () => {
  it('sums parts and labor as an input string', () => {
    expect(sumCostTotal('1200', '800')).toBe('2000');
  });

  it('treats empty and invalid parts as zero', () => {
    expect(sumCostTotal('', '800')).toBe('800');
    expect(sumCostTotal('abc', '800')).toBe('800');
    expect(sumCostTotal('', '')).toBe('0');
  });

  it('tolerates a decimal comma', () => {
    expect(sumCostTotal('10,50', '1,25')).toBe('11.75');
  });

  it('rounds to kopiykas', () => {
    expect(sumCostTotal('0.105', '0.1')).toBe('0.21');
  });
});

describe('validateCompleteValues', () => {
  it('accepts a filled form', () => {
    expect(validateCompleteValues(emptyCompleteValues({ car, interval }))).toBe('');
  });

  it('rejects a missing or negative odometer', () => {
    const values = emptyCompleteValues({ car, interval });
    expect(validateCompleteValues({ ...values, odometer: '' })).toBe('Вкажіть коректний пробіг');
    expect(validateCompleteValues({ ...values, odometer: '-5' })).toBe('Вкажіть коректний пробіг');
    expect(validateCompleteValues({ ...values, odometer: 'abc' })).toBe('Вкажіть коректний пробіг');
  });

  it('rejects a missing date', () => {
    const values = emptyCompleteValues({ car, interval });
    expect(validateCompleteValues({ ...values, date: '' })).toBe('Вкажіть дату');
  });

  it('rejects a negative cost', () => {
    const values = emptyCompleteValues({ car, interval });
    expect(validateCompleteValues({ ...values, totalCost: '-1' })).toBe('Вкажіть коректну вартість');
  });

  it('accepts a zero cost', () => {
    const values = emptyCompleteValues({ car, interval });
    expect(validateCompleteValues({ ...values, totalCost: '0' })).toBe('');
  });
});

describe('completeValuesToPayload', () => {
  it('maps the form values onto the complete contract', () => {
    expect(
      completeValuesToPayload({
        odometer: '123456',
        date: '2026-07-15',
        totalCost: '2000',
        partsCost: '1200',
        laborCost: '800',
        items: ['Олива двигуна'],
        notes: '  на СТО  ',
      })
    ).toEqual({
      odometer: 123456,
      date: '2026-07-15',
      total_cost: 2000,
      parts_cost: 1200,
      labor_cost: 800,
      items: ['Олива двигуна'],
      notes: 'на СТО',
    });
  });

  it('sends empty optional costs as zero and empty notes as null', () => {
    expect(
      completeValuesToPayload({
        odometer: '10',
        date: '2026-07-15',
        totalCost: '',
        partsCost: '',
        laborCost: '',
        items: [],
        notes: '   ',
      })
    ).toEqual({
      odometer: 10,
      date: '2026-07-15',
      total_cost: 0,
      parts_cost: 0,
      labor_cost: 0,
      items: [],
      notes: null,
    });
  });

  it('tolerates a decimal comma in the costs', () => {
    const payload = completeValuesToPayload({
      odometer: '10',
      date: '2026-07-15',
      totalCost: '11,75',
      partsCost: '10,50',
      laborCost: '1,25',
      items: [],
      notes: '',
    });
    expect(payload.total_cost).toBe(11.75);
    expect(payload.parts_cost).toBe(10.5);
    expect(payload.labor_cost).toBe(1.25);
  });
});
