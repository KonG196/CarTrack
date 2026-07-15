import { describe, it, expect } from 'vitest';
import {
  COMMON_MAINTENANCE_ITEMS,
  REPAIR_CATEGORIES,
  EXPENSE_CATEGORIES,
  DEFAULT_EXPENSE_CATEGORY,
  emptyFormValues,
  entryToFormValues,
  formValuesToPayload,
} from './entryForm';

const refuelLog = {
  id: 1,
  car_id: 1,
  type: 'refuel',
  odometer: 123456,
  date: '2026-07-10',
  total_cost: 2502.05,
  notes: 'по трасі',
  refuel: {
    liters: 45.5,
    price_per_liter: 54.99,
    is_full_tank: false,
    gas_station: 'OKKO',
  },
  maintenance: null,
  repair: null,
  created_at: '2026-07-10T12:00:00',
};

const maintenanceLog = {
  id: 2,
  car_id: 1,
  type: 'maintenance',
  odometer: 120000,
  date: '2026-06-01',
  total_cost: 4500,
  notes: null,
  refuel: null,
  maintenance: {
    parts_cost: 3000,
    labor_cost: 1500,
    items: ['Олива двигуна', 'Масляний фільтр', 'Свічки запалювання'],
  },
  repair: null,
  created_at: '2026-06-01T12:00:00',
};

const repairLog = {
  id: 3,
  car_id: 1,
  type: 'repair',
  odometer: 118000,
  date: '2026-05-15',
  total_cost: 7800,
  notes: 'СТО на Батуринській',
  refuel: null,
  maintenance: null,
  repair: {
    category: 'Підвіска',
    part_name: 'Амортизатор передній',
    warranty_months: 12,
    warranty_km: 20000,
  },
  created_at: '2026-05-15T12:00:00',
};

const expenseLog = {
  id: 4,
  car_id: 1,
  type: 'expense',
  odometer: 121000,
  date: '2026-06-20',
  total_cost: 950,
  notes: 'на Стуса',
  refuel: null,
  maintenance: null,
  repair: null,
  expense: { category: 'Мийка' },
  created_at: '2026-06-20T12:00:00',
};

describe('entryToFormValues', () => {
  it('maps a refuel entry to form values', () => {
    const values = entryToFormValues(refuelLog);
    expect(values.date).toBe('2026-07-10');
    expect(values.odometer).toBe('123456');
    expect(values.totalCost).toBe('2502.05');
    expect(values.notes).toBe('по трасі');
    expect(values.liters).toBe('45.5');
    expect(values.pricePerLiter).toBe('54.99');
    expect(values.isFullTank).toBe(false);
    expect(values.gasStation).toBe('OKKO');
  });

  it('maps a maintenance entry, splitting off custom items', () => {
    const values = entryToFormValues(maintenanceLog);
    expect(values.checkedItems).toEqual([
      'Олива двигуна',
      'Масляний фільтр',
      'Свічки запалювання',
    ]);
    expect(values.customItems).toEqual(['Свічки запалювання']);
    expect(values.partsCost).toBe('3000');
    expect(values.laborCost).toBe('1500');
    expect(values.notes).toBe('');
  });

  it('maps a repair entry including the warranty', () => {
    const values = entryToFormValues(repairLog);
    expect(values.category).toBe('Підвіска');
    expect(values.partName).toBe('Амортизатор передній');
    expect(values.warrantyMonths).toBe('12');
    expect(values.warrantyKm).toBe('20000');
  });

  it('prefills the edit form keeping the original date and odometer', () => {
    // Edit mode uses entryToFormValues as-is (duplication overrides date and
    // odometer separately in AddEntry), so both must survive the mapping.
    const values = entryToFormValues(refuelLog);
    expect(values.date).toBe(refuelLog.date);
    expect(values.odometer).toBe(String(refuelLog.odometer));
    const payload = formValuesToPayload(refuelLog.type, values);
    expect(payload.date).toBe(refuelLog.date);
    expect(payload.odometer).toBe(refuelLog.odometer);
  });

  it('maps an expense entry leaving detail fields at defaults', () => {
    const values = entryToFormValues(expenseLog);
    expect(values.odometer).toBe('121000');
    expect(values.totalCost).toBe('950');
    expect(values.notes).toBe('на Стуса');
    expect(values.liters).toBe('');
    expect(values.checkedItems).toEqual([]);
    expect(values.category).toBe(REPAIR_CATEGORIES[0]);
  });

  it('maps the expense category', () => {
    expect(entryToFormValues(expenseLog).expenseCategory).toBe('Мийка');
  });

  it('files a legacy expense without a category under the default one', () => {
    // Pre-0004 rows carry no expense details at all; the backend reports them
    // under DEFAULT_EXPENSE_CATEGORY, so the form must agree.
    const legacy = { ...expenseLog, expense: null };
    expect(entryToFormValues(legacy).expenseCategory).toBe(DEFAULT_EXPENSE_CATEGORY);
  });
});

describe('formValuesToPayload', () => {
  it('is symmetric with entryToFormValues for refuel', () => {
    const payload = formValuesToPayload('refuel', entryToFormValues(refuelLog));
    expect(payload).toEqual({
      type: 'refuel',
      odometer: 123456,
      date: '2026-07-10',
      total_cost: 2502.05,
      notes: 'по трасі',
      refuel: {
        liters: 45.5,
        price_per_liter: 54.99,
        is_full_tank: false,
        gas_station: 'OKKO',
        fuel_kind: null,
      },
    });
  });

  it('sends the chosen fuel kind and round-trips it back into the form', () => {
    const gasFill = { ...refuelLog, refuel: { ...refuelLog.refuel, fuel_kind: 'lpg' } };
    const values = entryToFormValues(gasFill);
    expect(values.fuelKind).toBe('lpg');
    expect(formValuesToPayload('refuel', values).refuel.fuel_kind).toBe('lpg');
  });

  it('sends null for «як у авто» so PATCH can clear a kind back to the default', () => {
    // Empty is a real answer here — «whatever the car runs on» — not a missing
    // one, so it has to reach the API as an explicit null.
    const gasFill = { ...refuelLog, refuel: { ...refuelLog.refuel, fuel_kind: 'lpg' } };
    const values = { ...entryToFormValues(gasFill), fuelKind: '' };
    expect(formValuesToPayload('refuel', values).refuel.fuel_kind).toBeNull();
  });

  it('leaves the fuel kind empty for a refuel that never had one', () => {
    expect(entryToFormValues(refuelLog).fuelKind).toBe('');
    expect(emptyFormValues().fuelKind).toBe('');
  });

  it('is symmetric with entryToFormValues for maintenance', () => {
    const payload = formValuesToPayload('maintenance', entryToFormValues(maintenanceLog));
    expect(payload).toEqual({
      type: 'maintenance',
      odometer: 120000,
      date: '2026-06-01',
      total_cost: 4500,
      notes: null,
      maintenance: {
        parts_cost: 3000,
        labor_cost: 1500,
        items: ['Олива двигуна', 'Масляний фільтр', 'Свічки запалювання'],
      },
    });
  });

  it('is symmetric with entryToFormValues for repair', () => {
    const payload = formValuesToPayload('repair', entryToFormValues(repairLog));
    expect(payload).toEqual({
      type: 'repair',
      odometer: 118000,
      date: '2026-05-15',
      total_cost: 7800,
      notes: 'СТО на Батуринській',
      repair: {
        category: 'Підвіска',
        part_name: 'Амортизатор передній',
        warranty_months: 12,
        warranty_km: 20000,
      },
    });
  });

  it('is symmetric with entryToFormValues for expense', () => {
    const payload = formValuesToPayload('expense', entryToFormValues(expenseLog));
    expect(payload).toEqual({
      type: 'expense',
      odometer: 121000,
      date: '2026-06-20',
      total_cost: 950,
      notes: 'на Стуса',
      expense: { category: 'Мийка' },
    });
  });

  it('sends the default expense category when none was picked', () => {
    const values = emptyFormValues();
    values.date = '2026-07-14';
    values.odometer = '100000';
    values.totalCost = '300';
    expect(formValuesToPayload('expense', values).expense).toEqual({
      category: DEFAULT_EXPENSE_CATEGORY,
    });
  });

  it('attaches no expense details to other types', () => {
    const payload = formValuesToPayload('refuel', entryToFormValues(refuelLog));
    expect(payload.expense).toBeUndefined();
  });

  it('nulls cleared optional fields so PATCH can erase them', () => {
    const values = emptyFormValues();
    values.date = '2026-07-14';
    values.odometer = '100000';
    values.totalCost = '500';
    values.notes = '   ';
    values.warrantyMonths = '0';
    const payload = formValuesToPayload('repair', values);
    expect(payload.notes).toBeNull();
    expect(payload.repair).toEqual({
      category: REPAIR_CATEGORIES[0],
      part_name: null,
      warranty_months: null,
      warranty_km: null,
    });
  });

  it('parses decimal commas in numeric inputs', () => {
    const values = emptyFormValues();
    values.date = '2026-07-14';
    values.odometer = '100000';
    values.totalCost = '2502,05';
    values.liters = '45,5';
    values.pricePerLiter = '54,99';
    const payload = formValuesToPayload('refuel', values);
    expect(payload.total_cost).toBe(2502.05);
    expect(payload.refuel.liters).toBe(45.5);
    expect(payload.refuel.price_per_liter).toBe(54.99);
  });

  it('parses decimal commas in maintenance costs', () => {
    const values = emptyFormValues();
    values.date = '2026-07-14';
    values.odometer = '100000';
    values.totalCost = '4500,5';
    values.partsCost = '3000,25';
    values.laborCost = '1500,25';
    const payload = formValuesToPayload('maintenance', values);
    expect(payload.total_cost).toBe(4500.5);
    expect(payload.maintenance.parts_cost).toBe(3000.25);
    expect(payload.maintenance.labor_cost).toBe(1500.25);
  });

  it('parses a decimal comma in the expense cost', () => {
    const values = emptyFormValues();
    values.date = '2026-07-14';
    values.odometer = '100000';
    values.totalCost = '349,90';
    values.expenseCategory = 'Мийка';
    const payload = formValuesToPayload('expense', values);
    expect(payload.total_cost).toBe(349.9);
    expect(payload.expense).toEqual({ category: 'Мийка' });
  });

  it('defaults maintenance costs to 0 when left empty', () => {
    const values = emptyFormValues();
    values.date = '2026-07-14';
    values.odometer = '100000';
    values.totalCost = '0';
    values.checkedItems = ['Олива двигуна'];
    const payload = formValuesToPayload('maintenance', values);
    expect(payload.maintenance).toEqual({
      parts_cost: 0,
      labor_cost: 0,
      items: ['Олива двигуна'],
    });
  });
});

describe('COMMON_MAINTENANCE_ITEMS', () => {
  it('keeps the original checklist order', () => {
    expect(COMMON_MAINTENANCE_ITEMS[0]).toBe('Олива двигуна');
    expect(COMMON_MAINTENANCE_ITEMS).toHaveLength(6);
  });
});

describe('EXPENSE_CATEGORIES', () => {
  // Must stay in step with schemas.EXPENSE_CATEGORIES on the backend: a value
  // outside that Literal is a 422.
  it('matches the backend category list', () => {
    expect(EXPENSE_CATEGORIES).toEqual([
      'Мийка',
      'Паркування',
      'Штраф',
      'Страхування',
      'Податок',
      'Шини',
      'Аксесуари',
      'Інше',
    ]);
  });

  it('defaults to «Інше», which is part of the list', () => {
    expect(DEFAULT_EXPENSE_CATEGORY).toBe('Інше');
    expect(EXPENSE_CATEGORIES).toContain(DEFAULT_EXPENSE_CATEGORY);
    expect(emptyFormValues().expenseCategory).toBe(DEFAULT_EXPENSE_CATEGORY);
  });
});
