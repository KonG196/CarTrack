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

// A wider no-break space sits between the number and its unit (₴ / км). Reusing
// the thin thousands-space for the unit too glued it onto the number ("4 650₴")
// at large/bold sizes; a normal no-break space cleanly separates number + unit.
const UNIT_GAP = '\u00A0';

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
  return `${sign}${grouped}${frac}${UNIT_GAP}₴`;
}

// Short money for tight spots (dashboard stat tiles) where the full grouped
// value with kopecks overflows a one-third-width card. Kopecks are dropped, and
// large sums collapse to тис/млн so the string stays a few characters wide.
export function formatMoneyCompact(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
  const value = Number(n);
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  if (abs >= 1_000_000) {
    const m = abs / 1_000_000;
    const s = m >= 10 ? String(Math.round(m)) : m.toFixed(1).replace('.', ',');
    return `${sign}${s}${UNIT_GAP}млн${UNIT_GAP}₴`;
  }
  if (abs >= 100_000) {
    return `${sign}${groupThousands(String(Math.round(abs / 1000)))}${UNIT_GAP}тис${UNIT_GAP}₴`;
  }
  return `${sign}${groupThousands(String(Math.round(abs)))}${UNIT_GAP}₴`;
}

export function formatKm(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
  const value = Math.round(Number(n));
  const sign = value < 0 ? '-' : '';
  return `${sign}${groupThousands(String(Math.abs(value)))}${UNIT_GAP}км`;
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
