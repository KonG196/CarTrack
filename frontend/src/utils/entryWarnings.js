// Warnings only, never blockers: backdated corrections and prepaid receipts are
// both legitimate, so the form always stays submittable.

import i18n from '../i18n';
import { formatKm, formatDate } from './format';
import { todayIso } from './entryForm';

export function entryWarnings({ type, odometer, date, context }, today = todayIso()) {
  const warnings = [];

  const odo = parseInt(odometer, 10);
  const lastOdometer = context?.last_entry_odometer;

  if (Number.isFinite(odo) && lastOdometer != null) {
    if (odo < lastOdometer) {
      warnings.push(i18n.t('entryWarnings.lowerThanLast', { km: formatKm(lastOdometer) }));
    } else if (type === 'refuel' && odo === lastOdometer) {
      // The prefill was left untouched: no distance, so no full-to-full segment.
      warnings.push(i18n.t('entryWarnings.odometerUnchanged'));
    }
  }

  if (date && String(date) > today) {
    warnings.push(i18n.t('entryWarnings.dateInFuture'));
  }

  return warnings;
}

export function lastEntryHint(context) {
  if (!context || context.last_entry_odometer == null) return '';
  const parts = [formatKm(context.last_entry_odometer)];
  if (context.last_entry_date) parts.push(formatDate(context.last_entry_date));
  return i18n.t('entryWarnings.lastEntry', { value: parts.join(' · ') });
}
