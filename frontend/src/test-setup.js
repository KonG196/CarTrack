// Vitest global setup.
//
// The unit tests for the formatters and label helpers (format, fuelKind,
// obdMetrics, permissions, entryWarnings, completeForm, workOrder, the domain
// labels, …) were written against Ukrainian output, and Ukrainian is exactly
// what they should keep pinning. English is the runtime default and is covered
// end-to-end by the headless render checks, so here we pin the i18n language to
// Ukrainian and let these tests assert the Ukrainian strings directly.
import i18n from './i18n';
import { useCurrencyStore } from './store/currencyStore';

i18n.changeLanguage('uk');
// The money tests assert the Ukrainian hryvnia format ("1 250,50 ₴"); the
// runtime default is USD, so pin the currency here the same way as the language.
useCurrencyStore.getState().setCurrency('UAH');
