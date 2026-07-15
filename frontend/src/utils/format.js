const THIN_SPACE = ' '; // narrow no-break space for thousands grouping

const UK_MONTHS_SHORT = [
  'січ',
  'лют',
  'бер',
  'кві',
  'тра',
  'чер',
  'лип',
  'сер',
  'вер',
  'жов',
  'лис',
  'гру',
];

function groupThousands(digits) {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, THIN_SPACE);
}

export function formatMoney(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
  const value = Number(n);
  const sign = value < 0 ? '-' : '';
  const fixed = Math.abs(value).toFixed(2);
  const [intPart, fracPart] = fixed.split('.');
  const grouped = groupThousands(intPart);
  const frac = fracPart === '00' ? '' : `,${fracPart}`;
  return `${sign}${grouped}${frac}${THIN_SPACE}₴`;
}

export function formatKm(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
  const value = Math.round(Number(n));
  const sign = value < 0 ? '-' : '';
  return `${sign}${groupThousands(String(Math.abs(value)))}${THIN_SPACE}км`;
}

export function formatDate(iso) {
  if (!iso) return '—';
  const datePart = String(iso).slice(0, 10);
  const match = datePart.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return String(iso);
  const [, year, month, day] = match;
  return `${day}.${month}.${year}`;
}

export function monthLabel(yyyyMm) {
  if (!yyyyMm) return '—';
  const match = String(yyyyMm).match(/^(\d{4})-(\d{2})$/);
  if (!match) return String(yyyyMm);
  const [, year, month] = match;
  const idx = Number(month) - 1;
  if (idx < 0 || idx > 11) return String(yyyyMm);
  return `${UK_MONTHS_SHORT[idx]} ${year}`;
}
