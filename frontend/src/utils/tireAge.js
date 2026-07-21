// Tyre-age helpers, mirrored from backend/app/services/tires.py so the card and
// the bot agree on when a set is «old».

// Warn to inspect tyres at this age; they harden and crack with time regardless
// of tread depth.
export const TIRE_AGE_WARN_YEARS = 4;
// Past this age replacement is usually overdue.
export const TIRE_AGE_CRIT_YEARS = 8;

// Age of a tyre set in whole years, or null when unknown. The DOT production
// year wins (rubber ages from manufacture); the purchase year is a fallback for
// a set entered without a DOT. Never negative.
export function tireAgeYears(tireSet, now = new Date()) {
  if (!tireSet) return null;
  let base = null;
  if (tireSet.dot_year != null) {
    base = Number(tireSet.dot_year);
  } else if (tireSet.purchased_at) {
    // Take the year straight from the ISO string (YYYY-…), not via new Date(),
    // whose UTC-midnight parse + local getFullYear() would roll a Jan-1 date
    // back a year in negative-UTC zones — diverging from the backend's .year.
    const y = parseInt(String(tireSet.purchased_at).slice(0, 4), 10);
    if (!Number.isNaN(y)) base = y;
  }
  if (base == null || Number.isNaN(base)) return null;
  return Math.max(0, now.getFullYear() - base);
}

// 'crit' | 'warn' | 'ok' | null(unknown) — the display severity for an age.
export function tireAgeLevel(age) {
  if (age == null) return null;
  if (age >= TIRE_AGE_CRIT_YEARS) return 'crit';
  if (age >= TIRE_AGE_WARN_YEARS) return 'warn';
  return 'ok';
}

// Whether the mounted set is the wrong season for what the calendar calls for.
// No changeover window → false. Nothing mounted → true (put the right set on).
// An all-season set covers both, so it never mismatches.
export function tireSeasonMismatch(changeoverSeason, installedSet) {
  if (!changeoverSeason) return false;
  if (!installedSet) return true;
  if (installedSet.season === 'all_season') return false;
  return installedSet.season !== changeoverSeason;
}
