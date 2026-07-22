import i18n from './index';

// Display labels for canonical, persisted domain values.
//
// The values themselves (maintenance items, repair/expense categories, fuel
// codes) are stored in the database and matched with `.includes()` / equality
// across the app and the backend, so they MUST stay exactly as written in
// entryForm.js — Ukrainian for the item/category enums, English codes for fuel.
// Only what the user *sees* is localized here: given a canonical value, return
// the label for the active UI language. Ukrainian is the identity (the value is
// already its own Ukrainian label); English is looked up, falling back to the
// raw value so free-text custom items pass through untouched.

const EN = {
  maintenanceItems: {
    'Олива двигуна': 'Engine oil',
    'Масляний фільтр': 'Oil filter',
    'Повітряний фільтр': 'Air filter',
    'Салонний фільтр': 'Cabin filter',
    'Паливний фільтр': 'Fuel filter',
    'Гальмівна рідина': 'Brake fluid',
  },
  repairCategories: {
    'Підвіска': 'Suspension',
    'Гальма': 'Brakes',
    'Двигун': 'Engine',
    'Електрика': 'Electrical',
    'Трансмісія': 'Transmission',
    'Кузов': 'Body',
    'Інше': 'Other',
  },
  expenseCategories: {
    'Мийка': 'Car wash',
    'Паркування': 'Parking',
    'Штраф': 'Fine',
    'Страхування': 'Insurance',
    'Податок': 'Tax',
    'Шини': 'Tires',
    'Аксесуари': 'Accessories',
    'Інше': 'Other',
  },
  specCategories: {
    'Моменти затяжки': 'Torque specs',
    'Рідини та обʼєми': 'Fluids & capacities',
    'Допуски': 'Approvals',
    'Інше': 'Other',
  },
};

function isEn() {
  return String(i18n.language || 'en').startsWith('en');
}

function labelFrom(group, value) {
  if (value == null || value === '') return value;
  if (!isEn()) return value; // Ukrainian value is already the Ukrainian label
  return EN[group][value] || value; // unknown / custom → passthrough
}

export function maintenanceItemLabel(value) {
  return labelFrom('maintenanceItems', value);
}

export function repairCategoryLabel(value) {
  return labelFrom('repairCategories', value);
}

export function expenseCategoryLabel(value) {
  return labelFrom('expenseCategories', value);
}

export function specCategoryLabel(value) {
  return labelFrom('specCategories', value);
}
