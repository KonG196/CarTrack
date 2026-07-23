/**
 * Pure helpers for the shared entry form (create / edit / duplicate):
 * mapping a LogEntry API object into form values and form values back
 * into an API payload. The payload mapping is extracted from the original
 * AddEntry handleSubmit; cleared optional fields are sent as explicit null
 * so PATCH can erase them (identical create semantics — the backend treats
 * a missing optional field and null the same way on create).
 */

import { num } from './refuelMath';
import { currentUnits } from '../store/unitStore';
import {
  isImperial,
  kmFromDistance,
  litresFromVolume,
  LITRES_PER_US_GALLON,
  KM_PER_MILE,
} from '../units';

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

// Local calendar date, not UTC: toISOString() rolls over at 00:00 UTC, so in
// UA (UTC+2/+3) it returns the wrong day for a couple of hours before midnight —
// giving the entry a wrong default date and a spurious "future date" warning.
export const todayIso = () => {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
};

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
  // The DB is metric; when the user works in imperial, the form must show the
  // reading in their units (and formValuesToPayload converts back on save).
  const system = currentUnits();
  const imperial = isImperial(system);
  const toDisplayDistance = (km) => (imperial ? Math.round(km / KM_PER_MILE) : km);
  const toDisplayVolume = (l) => (imperial ? +(l / LITRES_PER_US_GALLON).toFixed(3) : l);
  const toDisplayPricePerVol = (perL) =>
    imperial ? +(perL * LITRES_PER_US_GALLON).toFixed(3) : perL;

  const values = emptyFormValues();
  values.date = String(log.date).slice(0, 10);
  values.odometer = String(toDisplayDistance(log.odometer));
  values.totalCost = String(log.total_cost);
  values.notes = log.notes || '';

  if (log.refuel) {
    values.liters = String(toDisplayVolume(Number(log.refuel.liters)));
    values.pricePerLiter = String(toDisplayPricePerVol(Number(log.refuel.price_per_liter)));
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
    values.warrantyKm =
      log.repair.warranty_km != null ? String(toDisplayDistance(log.repair.warranty_km)) : '';
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
  // Inputs are entered in the user's display units; the DB is metric, so convert
  // here at the single write boundary. total_cost/parts/labor are money — never
  // converted (currency is symbol-only). Distances (mi→km) and volumes (gal→l)
  // are; price-per-volume flips the other way (a $/gallon becomes $/litre).
  const system = currentUnits();
  const imperial = isImperial(system);
  const odoRaw = parseInt(values.odometer, 10);

  const payload = {
    type,
    odometer: Number.isFinite(odoRaw) ? Math.round(kmFromDistance(odoRaw, system)) : odoRaw,
    date: values.date,
    total_cost: num(values.totalCost),
    notes: values.notes.trim() || null,
  };

  if (type === 'refuel') {
    const litersInput = num(values.liters);
    const pricePerInput = num(values.pricePerLiter);
    payload.refuel = {
      liters: litersInput == null ? null : litresFromVolume(litersInput, system),
      // Entered per gallon in imperial → store per litre.
      price_per_liter:
        pricePerInput == null ? null : imperial ? pricePerInput / LITRES_PER_US_GALLON : pricePerInput,
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
      // Entered in the display distance unit; store km.
      warranty_km:
        Number.isFinite(wk) && wk > 0 ? Math.round(kmFromDistance(wk, system)) : null,
    };
  }

  if (type === 'expense') {
    payload.expense = { category: values.expenseCategory || DEFAULT_EXPENSE_CATEGORY };
  }

  return payload;
}
