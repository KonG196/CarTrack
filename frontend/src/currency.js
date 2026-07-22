// Per-user display currency. Amounts are never converted — the choice only
// decides which symbol is shown. Ordered by popularity, UAH second (this app's
// home currency). Keep in sync with backend `app/currency.py`.
//
// `prefix: true` puts the symbol before the number ($1,250); otherwise after
// it (1 250 ₴).
export const CURRENCIES = [
  { code: 'USD', symbol: '$', prefix: true, name: 'US Dollar' },
  { code: 'UAH', symbol: '₴', prefix: false, name: 'Ukrainian Hryvnia' },
  { code: 'EUR', symbol: '€', prefix: true, name: 'Euro' },
  { code: 'GBP', symbol: '£', prefix: true, name: 'British Pound' },
  { code: 'PLN', symbol: 'zł', prefix: false, name: 'Polish Złoty' },
  { code: 'CZK', symbol: 'Kč', prefix: false, name: 'Czech Koruna' },
  { code: 'CAD', symbol: 'C$', prefix: true, name: 'Canadian Dollar' },
  { code: 'AUD', symbol: 'A$', prefix: true, name: 'Australian Dollar' },
  { code: 'CHF', symbol: 'Fr', prefix: false, name: 'Swiss Franc' },
  { code: 'JPY', symbol: '¥', prefix: true, name: 'Japanese Yen' },
];

export const DEFAULT_CURRENCY = 'USD';
export const CURRENCY_KEY = 'kapot_currency';

const BY_CODE = Object.fromEntries(CURRENCIES.map((c) => [c.code, c]));

export function normalizeCurrency(value, fallback = DEFAULT_CURRENCY) {
  const code = String(value || '').trim().toUpperCase();
  return BY_CODE[code] ? code : fallback;
}

export function currencyInfo(code) {
  return BY_CODE[normalizeCurrency(code)];
}
