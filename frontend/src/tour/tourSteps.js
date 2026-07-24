// One guided overview walk. Each step spotlights the element carrying
// `data-tour="<target>"`. `path` moves the tour to another route first (the
// engine plays a tap on the `nav` item, navigates, and waits for the element to
// mount); a step whose element never appears is skipped, so an empty logbook or
// a car with no analytics does not dead-end the tour.
//
// `path` may also be a function of a small context ({ firstLogId }) for routes
// that need a real id. Returning null skips the step.
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

// One guided walk of the whole app instead of five per-page tours. It is never
// auto-shown — a welcome card on the dashboard offers it, and the Settings
// launcher replays it. `path` steps carry a `nav` target: the data-tour name of
// the bottom-nav item the engine "taps" (animated finger) before navigating, so
// a route change reads as a deliberate press, not a teleport.
export const TOURS = {
  overview: makeTour('tour.overview', [
    // Home — where you are and what it tells you.
    { target: 'car-switcher', tap: true },
    { target: 'car-name', tap: true, demo: DEMO_COPY },
    { target: 'stats' },
    { target: 'interval-row', tap: true },
    // Logbook — your history.
    { path: '/logbook', nav: 'nav-logbook', target: 'logbook-filters', tap: true },
    { path: '/logbook', nav: 'nav-logbook', target: 'log-row', tap: true },
    // Add — the one big action, including receipt scan.
    { path: '/add', nav: 'nav-add', target: 'add-type', tap: true },
    { path: '/add', nav: 'nav-add', target: 'add-scan', tap: true },
    // Analytics — the payoff.
    { path: '/analytics?tab=costs', nav: 'nav-analytics', target: 'analytics-forecast' },
    { path: '/analytics?tab=fuel', nav: 'nav-analytics', target: 'analytics-report', tap: true },
  ]),
};

// The order tours appear in the Settings launcher.
export const TOUR_ORDER = ['overview'];
