// Which category a receipt is for, read off the receipt itself.
//
// The rule this keeps: recognise, never guess. A till slip that says
// «АВТОМИЙКА» has named its category — reading it is not a guess, it is
// reading. A slip that says nothing gets nothing, and the user picks: a wrong
// category is silent, it just files the money where they will not find it.

import { EXPENSE_CATEGORIES, DEFAULT_EXPENSE_CATEGORY } from './entryForm';

// Ukrainian and Russian both, because a till in Ukraine prints either. Stems,
// not words: «мийка» / «мийки» / «мийці» all start the same.
const CATEGORY_SIGNS = [
  ['Мийка', [/мийк/, /мийн/, /мойк/, /автомий/, /car\s?wash/, /детейл/]],
  ['Паркування', [/парк/, /стоянк/, /parking/]],
  ['Штраф', [/штраф/, /постанов/, /адмінправопоруш/, /патрульн/]],
  ['Страхування', [/страхув/, /страхов/, /осцпв/, /каско/, /зелена карта/, /поліс/]],
  ['Податок', [/податок/, /податк/, /транспортний збір/]],
  ['Шини', [/шиномонтаж/, /\bшин/, /покришк/, /балансув/, /перевзут/]],
];

/**
 * expenseCategoryFrom(text) -> a category from EXPENSE_CATEGORIES, or null.
 *
 * null means the receipt did not say. That is an answer, not a gap: the caller
 * leaves the user's choice alone rather than filling it with a coin flip.
 */
export function expenseCategoryFrom(text) {
  const lowered = String(text || '').toLowerCase();
  if (!lowered.trim()) return null;
  for (const [category, signs] of CATEGORY_SIGNS) {
    if (signs.some((sign) => sign.test(lowered))) return category;
  }
  return null;
}

// Every category this can name must be one the form actually offers, or the
// chip would silently fail to light up.
export const RECOGNISABLE_CATEGORIES = CATEGORY_SIGNS.map(([category]) => category).filter(
  (category) => EXPENSE_CATEGORIES.includes(category)
);

export { DEFAULT_EXPENSE_CATEGORY };
