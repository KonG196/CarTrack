/**
 * Pure helpers for the shared entry form (create / edit / duplicate):
 * mapping a LogEntry API object into form values and form values back
 * into an API payload. The payload mapping is extracted from the original
 * AddEntry handleSubmit; cleared optional fields are sent as explicit null
 * so PATCH can erase them (identical create semantics — the backend treats
 * a missing optional field and null the same way on create).
 */

import { num } from './refuelMath';

export const COMMON_MAINTENANCE_ITEMS = [
  'Олива двигуна',
  'Масляний фільтр',
  'Повітряний фільтр',
  'Салонний фільтр',
  'Паливний фільтр',
  'Гальмівна рідина',
];

export const REPAIR_CATEGORIES = [
  'Підвіска',
  'Гальма',
  'Двигун',
  'Електрика',
  'Трансмісія',
  'Кузов',
  'Інше',
];

export const EXPENSE_CATEGORIES = [
  'Мийка',
  'Паркування',
  'Штраф',
  'Страхування',
  'Податок',
  'Шини',
  'Аксесуари',
  'Інше',
];

export const DEFAULT_EXPENSE_CATEGORY = 'Інше';

export const todayIso = () => new Date().toISOString().slice(0, 10);

export function emptyFormValues() {
  return {
    date: todayIso(),
    odometer: '',
    totalCost: '',
    notes: '',
    // refuel
    liters: '',
    pricePerLiter: '',
    isFullTank: true,
    gasStation: '',
    fuelKind: '',
    // maintenance
    checkedItems: [],
    customItems: [],
    partsCost: '',
    laborCost: '',
    // repair
    category: REPAIR_CATEGORIES[0],
    partName: '',
    warrantyMonths: '',
    warrantyKm: '',
    // expense
    expenseCategory: DEFAULT_EXPENSE_CATEGORY,
  };
}

export function entryToFormValues(log) {
  const values = emptyFormValues();
  values.date = String(log.date).slice(0, 10);
  values.odometer = String(log.odometer);
  values.totalCost = String(log.total_cost);
  values.notes = log.notes || '';

  if (log.refuel) {
    values.liters = String(log.refuel.liters);
    values.pricePerLiter = String(log.refuel.price_per_liter);
    values.isFullTank = Boolean(log.refuel.is_full_tank);
    values.gasStation = log.refuel.gas_station || '';
    values.fuelKind = log.refuel.fuel_kind || '';
  }

  if (log.maintenance) {
    const items = log.maintenance.items || [];
    values.checkedItems = [...items];
    values.customItems = items.filter((item) => !COMMON_MAINTENANCE_ITEMS.includes(item));
    values.partsCost = String(log.maintenance.parts_cost);
    values.laborCost = String(log.maintenance.labor_cost);
  }

  if (log.repair) {
    values.category = log.repair.category;
    values.partName = log.repair.part_name || '';
    values.warrantyMonths =
      log.repair.warranty_months != null ? String(log.repair.warranty_months) : '';
    values.warrantyKm = log.repair.warranty_km != null ? String(log.repair.warranty_km) : '';
  }

  // A pre-0004 expense has no details row; it already counts as the default
  // category everywhere else, so the form shows the same.
  if (log.type === 'expense') {
    values.expenseCategory = log.expense?.category || DEFAULT_EXPENSE_CATEGORY;
  }

  return values;
}

/**
 * formValuesToPayload(type, values) -> LogEntryCreate/LogEntryUpdate payload.
 * Assumes values already passed the form validation (see EntryForm).
 */
export function formValuesToPayload(type, values) {
  const payload = {
    type,
    odometer: parseInt(values.odometer, 10),
    date: values.date,
    total_cost: num(values.totalCost),
    notes: values.notes.trim() || null,
  };

  if (type === 'refuel') {
    payload.refuel = {
      liters: num(values.liters),
      price_per_liter: num(values.pricePerLiter),
      is_full_tank: values.isFullTank,
      gas_station: values.gasStation.trim() || null,
      fuel_kind: values.fuelKind || null,
    };
  }

  if (type === 'maintenance') {
    payload.maintenance = {
      parts_cost: num(values.partsCost) ?? 0,
      labor_cost: num(values.laborCost) ?? 0,
      items: values.checkedItems,
    };
  }

  if (type === 'repair') {
    const wm = parseInt(values.warrantyMonths, 10);
    const wk = parseInt(values.warrantyKm, 10);
    payload.repair = {
      category: values.category,
      part_name: values.partName.trim() || null,
      warranty_months: Number.isFinite(wm) && wm > 0 ? wm : null,
      warranty_km: Number.isFinite(wk) && wk > 0 ? wk : null,
    };
  }

  if (type === 'expense') {
    payload.expense = { category: values.expenseCategory || DEFAULT_EXPENSE_CATEGORY };
  }

  return payload;
}
