import { describe, expect, it } from 'vitest';

import { buildSpecsMessage, carTitle, hasSomethingToShare } from './partsCard';

const GOLF = {
  brand: 'Volkswagen',
  model: 'Golf VII Variant',
  // As the owner actually typed it: a generation and a colour in one free-text
  // field, with no reliable seam between them.
  generation: '7 (BA5), Urano Gray',
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
    expect(message).toContain('1.6 TDI CXXB');
    expect(message).toContain('VIN: WVWZZZAUZHP541983');
    expect(message).toContain('Олива: VW 507.00');
    expect(message).toContain('Антифриз: G13');
  });

  it('includes the generation but strips the colour after the comma', () => {
    // «7 (BA5), Urano Gray» -> «7 (BA5)»: a shop needs the generation to pick a
    // part, never the paint.
    const message = buildSpecsMessage(GOLF, SPECS);
    expect(message).toContain('Volkswagen Golf VII Variant 7 (BA5)');
    expect(message).not.toContain('Urano Gray');
  });

  it('does not paste the odometer or the paint', () => {
    // Neither decides which part fits. The odometer also changes every week, so
    // pasting it only dates the message; the colour rides along inside the
    // free-text `generation` («7 (BA5), Urano Gray»), which is why the whole
    // field stays out.
    const message = buildSpecsMessage(GOLF, SPECS);
    expect(message).not.toContain('240054');
    expect(message).not.toContain('Urano Gray');
  });

  it('leaves out what the shop never asks about', () => {
    // Wheel torque decides nothing about which part fits, and every extra line
    // is one the reader has to skip.
    expect(buildSpecsMessage(GOLF, SPECS)).not.toContain('120 Нм');
  });

  it('omits what is unknown rather than printing a dash', () => {
    const bare = { brand: 'Volkswagen', model: 'Golf', year: 2016 };
    const message = buildSpecsMessage(bare, []);
    expect(message).toBe('Volkswagen Golf');
    expect(message).not.toContain('VIN');
    expect(message).not.toContain('—');
  });

  it('is empty without a car', () => {
    expect(buildSpecsMessage(null, SPECS)).toBe('');
  });
});

describe('carTitle', () => {
  it('joins what is known', () => {
    expect(carTitle(GOLF)).toBe('Volkswagen Golf VII Variant 7 (BA5)');
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
