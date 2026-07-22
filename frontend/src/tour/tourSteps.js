// Several small tours, one per section, instead of one long walk. Each step
// spotlights the element carrying `data-tour="<target>"`. `path` moves the tour
// to another route first (the engine navigates and waits for the element to
// mount); a step whose element never appears is skipped, so an empty logbook or
// a car with no analytics does not dead-end the tour.
//
// `path` may be a function of a small context ({ firstLogId }) for routes that
// need a real id — the logbook detail. Returning null skips the step.
//
// `tap: true` plays a looping «finger tap» gesture over the spotlight — use it
// on steps whose element is meant to be pressed. `demo` is a CSS selector,
// queried inside the target, that the overlay actually clicks once per step so
// the real in-place result plays (e.g. the copy icon turning into a checkmark).
// Only give `demo` to interactions that change state in place — never ones that
// navigate away or open a modal, which would break the tour.
//
// Copy (label / title / body) is localized: each of those is a live getter that
// reads i18n at access time, so a language switch relabels an open tour without
// a reload. Only the copy is translated — target/tap/demo/path are data.

import i18n from '../i18n';

const DEMO_COPY = '[data-tour-demo="copy"]';
const t = (key) => i18n.t(key);

// Attach live-translated title/body getters to a step's data.
function withText(base, def) {
  return {
    ...def,
    get title() {
      return t(`${base}.title`);
    },
    get body() {
      return t(`${base}.body`);
    },
  };
}

function makeTour(base, steps) {
  return {
    get label() {
      return t(`${base}.label`);
    },
    steps: steps.map((def, i) => withText(`${base}.s${i + 1}`, def)),
  };
}

export const TOURS = {
  home: makeTour('tour.home', [
    { target: 'car-switcher', tap: true },
    { target: 'car-name', tap: true, demo: DEMO_COPY },
    { target: 'odometer', tap: true },
    { target: 'stats' },
    { target: 'interval-row', tap: true },
  ]),

  logbook: makeTour('tour.logbook', [
    { path: '/logbook', target: 'logbook-search' },
    { path: '/logbook', target: 'logbook-filters', tap: true },
    { path: '/logbook', target: 'log-row', tap: true },
    { path: (ctx) => (ctx.firstLogId ? `/logbook/${ctx.firstLogId}` : null), target: 'log-detail' },
  ]),

  add: makeTour('tour.add', [
    { path: '/add', target: 'add-type', tap: true },
    { path: '/add', target: 'add-scan', tap: true },
    { path: '/add', target: 'add-form' },
  ]),

  analytics: makeTour('tour.analytics', [
    { path: '/analytics?tab=costs', target: 'analytics-forecast' },
    { path: '/analytics?tab=costs', target: 'analytics-charts' },
    { path: '/analytics?tab=fuel', target: 'analytics-trip' },
    { path: '/analytics?tab=fuel', target: 'analytics-report', tap: true },
  ]),

  settings: makeTour('tour.settings', [
    { path: '/garage', target: 'settings-cars', tap: true, demo: DEMO_COPY },
    { path: '/garage', target: 'settings-profile', tap: true },
    { path: '/profile', target: 'profile-telegram', tap: true },
    { path: '/notifications', target: 'notif-reminders', tap: true },
    { path: '/garage', target: 'settings-more' },
  ]),
};

// The order tours appear in the Settings launcher.
export const TOUR_ORDER = ['home', 'logbook', 'add', 'analytics', 'settings'];
