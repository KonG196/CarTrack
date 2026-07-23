import i18n from '../i18n';
import { currencyInfo } from '../currency';
import { currentCurrency } from '../store/currencyStore';
import { currentUnits } from '../store/unitStore';
import {
  isImperial,
  distanceFromKm,
  volumeFromLitres,
  consumptionFromL100,
  costPerDistanceFromPerKm,
} from '../units';

const THIN_SPACE = ' '; // narrow no-break space for thousands grouping (uk)

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

const EN_MONTHS_SHORT = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

// A wider no-break space sits between the number and its unit (₴ / км). Reusing
// the thin thousands-space for the unit too glued it onto the number ("4 650₴")
// at large/bold sizes; a normal no-break space cleanly separates number + unit.
const UNIT_GAP = ' ';

// Locale is read live so a language switch reformats numbers without a reload.
// English groups with commas and a dot decimal ("1,250.50"); Ukrainian groups
// with a thin space and a comma decimal ("1 250,50").
function isEn() {
  return String(i18n.language || 'en').startsWith('en');
}

const units = () =>
  isEn()
    ? { km: 'km', thousand: 'k', million: 'M' }
    : { km: 'км', thousand: 'тис', million: 'млн' };

// Unit labels follow the LANGUAGE (km/км) and the SYSTEM (km→mi). Imperial has
// no localized mile/gallon/mpg abbreviations here — «mi/gal/mpg» read the same.
function distanceUnit() {
  if (isImperial(currentUnits())) return 'mi';
  return isEn() ? 'km' : 'км';
}
function volumeUnit() {
  if (isImperial(currentUnits())) return 'gal';
  return isEn() ? 'L' : 'л';
}
function consumptionUnit() {
  if (isImperial(currentUnits())) return 'mpg';
  return isEn() ? 'L/100 km' : 'л/100 км';
}

function groupThousands(digits) {
  const sep = isEn() ? ',' : THIN_SPACE;
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, sep);
}

// The user's display currency decides the symbol AND its side: prefix ("$1,250")
// or suffix ("1 250 ₴"). The value is never converted — this is symbol only.
function withCurrency(sign, body) {
  const { symbol, prefix } = currencyInfo(currentCurrency());
  return prefix ? `${sign}${symbol}${body}` : `${sign}${body}${UNIT_GAP}${symbol}`;
}

export function formatMoney(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
  const value = Number(n);
  const sign = value < 0 ? '-' : '';
  const fixed = Math.abs(value).toFixed(2);
  const [intPart, fracPart] = fixed.split('.');
  const grouped = groupThousands(intPart);
  const decimal = isEn() ? '.' : ',';
  const frac = fracPart === '00' ? '' : `${decimal}${fracPart}`;
  return withCurrency(sign, `${grouped}${frac}`);
}

// Short money for tight spots (dashboard stat tiles) where the full grouped
// value with kopecks overflows a one-third-width card. Kopecks are dropped, and
// large sums collapse to тис/млн (k/M) so the string stays a few characters wide.
export function formatMoneyCompact(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
  const value = Number(n);
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  const u = units();
  const decimal = isEn() ? '.' : ',';
  if (abs >= 1_000_000) {
    const m = abs / 1_000_000;
    const s = m >= 10 ? String(Math.round(m)) : m.toFixed(1).replace('.', decimal);
    return withCurrency(sign, `${s}${UNIT_GAP}${u.million}`);
  }
  if (abs >= 100_000) {
    return withCurrency(sign, `${groupThousands(String(Math.round(abs / 1000)))}${UNIT_GAP}${u.thousand}`);
  }
  return withCurrency(sign, groupThousands(String(Math.round(abs))));
}

// Distance is STORED in km; display converts to the user's system (mi/km) and
// labels it. Named formatKm for historical call sites — it is distance-aware.
export function formatKm(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
  const converted = distanceFromKm(Number(n), currentUnits());
  const value = Math.round(converted);
  const sign = value < 0 ? '-' : '';
  return `${sign}${groupThousands(String(Math.abs(value)))}${UNIT_GAP}${distanceUnit()}`;
}

// Consumption is STORED as l/100km; imperial shows mpg (an inverse, higher =
// better), metric shows l/100km. `n` is the stored l/100km value.
export function formatConsumption(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
  const converted = consumptionFromL100(Number(n), currentUnits());
  if (converted === null) return '—';
  const decimal = isEn() ? '.' : ',';
  const shown = converted.toFixed(1).replace('.', decimal);
  return `${shown}${UNIT_GAP}${consumptionUnit()}`;
}

// Just the converted consumption number (no unit label), for tiles whose label
// already carries the unit. `n` is stored l/100km.
export function formatConsumptionValue(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
  const converted = consumptionFromL100(Number(n), currentUnits());
  if (converted === null) return '—';
  const decimal = isEn() ? '.' : ',';
  return converted.toFixed(1).replace('.', decimal);
}

// Volume is STORED in litres; imperial shows US gallons. `n` is stored litres.
export function formatVolume(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
  const converted = volumeFromLitres(Number(n), currentUnits());
  if (converted === null) return '—';
  const decimal = isEn() ? '.' : ',';
  const shown = converted.toFixed(isImperial(currentUnits()) ? 2 : 1).replace('.', decimal);
  return `${shown}${UNIT_GAP}${volumeUnit()}`;
}

// The distance-unit label alone, for interpolating into chart titles / hints
// ("Spending per {{unit}}"). Follows language + system.
export function distanceUnitLabel() {
  return distanceUnit();
}
export function consumptionUnitLabel() {
  return consumptionUnit();
}
export function volumeUnitLabel() {
  return volumeUnit();
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
  const months = isEn() ? EN_MONTHS_SHORT : UK_MONTHS_SHORT;
  return `${months[idx]} ${year}`;
}
