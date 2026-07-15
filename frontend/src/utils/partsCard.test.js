import { describe, expect, it } from 'vitest';

import { buildSpecsMessage, carTitle, hasSomethingToShare } from './partsCard';

const GOLF = {
  brand: 'Volkswagen',
  model: 'Golf VII Variant',
  generation: '7 (BA5)',
  year: 2016,
  engine: '1.6 TDI CXXB',
  vin: 'WVWZZZAUZHP541983',
  plate: 'AA1234BB',
  current_odometer: 240054,
};

const SPECS = [
  { category: 'Допуски', name: 'Допуск оливи', value: 'VW 507.00' },
  { category: 'Рідини та обʼєми', name: 'Антифриз', value: 'G13' },
  { category: 'Рідини та обʼєми', name: 'Олива двигуна', value: '~4.6 л' },
  { category: 'Моменти затяжки', name: 'Колісні болти', value: '120 Нм' },
];

describe('buildSpecsMessage', () => {
  it('reads as one message a parts shop can answer', () => {
    const message = buildSpecsMessage(GOLF, SPECS);
    expect(message).toContain('Volkswagen Golf VII Variant');
    expect(message).toContain('двигун 1.6 TDI CXXB');
    expect(message).toContain('VIN: WVWZZZAUZHP541983');
    expect(message).toContain('Олива: VW 507.00');
    expect(message).toContain('Антифриз: G13');
    expect(message).toContain('Пробіг: 240054 км');
  });

  it('leaves out what the shop never asks about', () => {
    // Wheel torque decides nothing about which part fits, and every extra line
    // is one the reader has to skip.
    expect(buildSpecsMessage(GOLF, SPECS)).not.toContain('120 Нм');
  });

  it('omits what is unknown rather than printing a dash', () => {
    const bare = { brand: 'Volkswagen', model: 'Golf', year: 2016 };
    const message = buildSpecsMessage(bare, []);
    expect(message).toBe('Volkswagen Golf 2016 р.');
    expect(message).not.toContain('VIN');
    expect(message).not.toContain('—');
  });

  it('is empty without a car', () => {
    expect(buildSpecsMessage(null, SPECS)).toBe('');
  });
});

describe('carTitle', () => {
  it('joins what is known', () => {
    expect(carTitle(GOLF)).toBe('Volkswagen Golf VII Variant 7 (BA5) 2016 р.');
  });
});

describe('hasSomethingToShare', () => {
  it('needs at least one identifier worth sending', () => {
    expect(hasSomethingToShare(GOLF)).toBe(true);
    expect(hasSomethingToShare({ brand: 'VW', model: 'Golf' })).toBe(false);
    expect(hasSomethingToShare({ vin: 'X' })).toBe(true);
    expect(hasSomethingToShare(null)).toBe(false);
  });
});
