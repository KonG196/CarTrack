import { describe, expect, it } from 'vitest';

import { EXPENSE_CATEGORIES } from './entryForm';
import { RECOGNISABLE_CATEGORIES, expenseCategoryFrom } from './expenseCategory';

describe('expenseCategoryFrom', () => {
  it('reads the category a receipt names', () => {
    expect(expenseCategoryFrom('ТОВ АВТОМИЙКА "БЛИСК"\nДО СПЛАТИ 250,00')).toBe('Мийка');
    expect(expenseCategoryFrom('Паркування, 2 год\nСУМА 60,00')).toBe('Паркування');
    expect(expenseCategoryFrom('Шиномонтаж, балансування 4 колеса')).toBe('Шини');
    expect(expenseCategoryFrom('Поліс ОСЦПВ на рік')).toBe('Страхування');
    expect(expenseCategoryFrom('Постанова про накладення штрафу')).toBe('Штраф');
  });

  it('reads a till that prints in Russian', () => {
    expect(expenseCategoryFrom('АВТОМОЙКА, оплата картой')).toBe('Мийка');
  });

  it('says nothing when the receipt says nothing', () => {
    // A blank answer is honest: the user picks. A coin flip files the money
    // where they will never look for it, and nothing on screen says it guessed.
    expect(expenseCategoryFrom('ТОВ "РОГА І КОПИТА"\nСУМА 300,00')).toBeNull();
    expect(expenseCategoryFrom('')).toBeNull();
    expect(expenseCategoryFrom(null)).toBeNull();
    expect(expenseCategoryFrom('   ')).toBeNull();
  });

  it('only ever names a chip the form actually has', () => {
    for (const category of RECOGNISABLE_CATEGORIES) {
      expect(EXPENSE_CATEGORIES).toContain(category);
    }
    expect(RECOGNISABLE_CATEGORIES.length).toBe(6);
  });

  it('does not mistake a fuel receipt for a car wash', () => {
    // WOG sells coffee and car washes; a diesel receipt from one is still fuel.
    expect(expenseCategoryFrom('WOG\nДизель 30,00 л\nДО СПЛАТИ 1650,00')).toBeNull();
  });
});
