// Warnings only, never blockers: backdated corrections and prepaid receipts are
// both legitimate, so the form always stays submittable.

import { formatKm, formatDate } from './format';
import { todayIso } from './entryForm';

export function entryWarnings({ type, odometer, date, context }, today = todayIso()) {
  const warnings = [];

  const odo = parseInt(odometer, 10);
  const lastOdometer = context?.last_entry_odometer;

  if (Number.isFinite(odo) && lastOdometer != null) {
    if (odo < lastOdometer) {
      warnings.push(`Менше за останній запис (${formatKm(lastOdometer)}) — це історичний запис?`);
    } else if (type === 'refuel' && odo === lastOdometer) {
      // The prefill was left untouched: no distance, so no full-to-full segment.
      warnings.push('Пробіг не змінився з останнього запису — розхід не порахується');
    }
  }

  if (date && String(date) > today) {
    warnings.push('Дата в майбутньому');
  }

  return warnings;
}

export function lastEntryHint(context) {
  if (!context || context.last_entry_odometer == null) return '';
  const parts = [formatKm(context.last_entry_odometer)];
  if (context.last_entry_date) parts.push(formatDate(context.last_entry_date));
  return `Останній запис: ${parts.join(' · ')}`;
}
