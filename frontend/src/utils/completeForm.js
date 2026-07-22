/**
 * Pure helpers for the compact «Виконано» form that closes a service
 * interval: defaults, validation and the mapping onto the
 * POST /intervals/{id}/complete payload.
 *
 * The logged items default to the interval title, so the maintenance entry
 * the backend creates says what was actually serviced.
 */

import i18n from '../i18n';
import { num } from './refuelMath';
import { todayIso } from './entryForm';

// A zero is a claim: it says this service was free. Nobody means that, so it
// gets typed over every time — which makes it the worst possible default. The
// estimate the interval carries is a better opening bid: right often enough to
// keep, wrong in a way that is obvious.
export function emptyCompleteValues({ car, interval } = {}) {
  return {
    odometer: car?.current_odometer != null ? String(car.current_odometer) : '',
    date: todayIso(),
    totalCost: interval?.estimated_cost != null ? String(interval.estimated_cost) : '0',
    partsCost: '',
    laborCost: '',
    items: interval?.title ? [interval.title] : [],
    notes: '',
  };
}

/** Where the prefilled cost came from: 'history' | 'baseline' | null. */
export function costEstimateSource(interval) {
  if (interval?.estimated_cost == null) return null;
  return interval.estimated_cost_source ?? null;
}

export function sumCostTotal(partsCost, laborCost) {
  const parts = num(partsCost) ?? 0;
  const labor = num(laborCost) ?? 0;
  return String(Math.round((parts + labor) * 100) / 100);
}

export function validateCompleteValues(values) {
  const odometer = parseInt(values.odometer, 10);
  if (!Number.isFinite(odometer) || odometer < 0) return i18n.t('completeForm.invalidOdometer');
  if (!values.date) return i18n.t('completeForm.dateRequired');
  const total = num(values.totalCost) ?? 0;
  if (total < 0) return i18n.t('completeForm.invalidCost');
  return '';
}

/**
 * completeValuesToPayload(values) -> the POST /intervals/{id}/complete body.
 * Assumes the values already passed validateCompleteValues.
 */
export function completeValuesToPayload(values) {
  return {
    odometer: parseInt(values.odometer, 10),
    date: values.date,
    total_cost: num(values.totalCost) ?? 0,
    parts_cost: num(values.partsCost) ?? 0,
    labor_cost: num(values.laborCost) ?? 0,
    items: values.items,
    notes: values.notes.trim() || null,
  };
}
