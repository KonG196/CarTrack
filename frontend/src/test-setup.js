// Vitest global setup.
//
// The unit tests for the formatters and label helpers (format, fuelKind,
// obdMetrics, permissions, entryWarnings, completeForm, workOrder, the domain
// labels, …) were written against Ukrainian output, and Ukrainian is exactly
// what they should keep pinning. English is the runtime default and is covered
// end-to-end by the headless render checks, so here we pin the i18n language to
// Ukrainian and let these tests assert the Ukrainian strings directly.
import i18n from './i18n';

i18n.changeLanguage('uk');
