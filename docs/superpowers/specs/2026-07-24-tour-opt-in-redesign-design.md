# Tour: opt-in + polish redesign

Make the onboarding tour non-mandatory and noticeably better. Users found the
auto-launching spotlight (5 separate per-page tours firing on first visit)
annoying.

## Decisions

- **No auto-launch.** Remove the per-page auto-show entirely. A dismissible
  welcome block on the dashboard (first authenticated visit) offers the tour:
  "Новий у Kapot? Показати головне за ~30 сек" + [Показати] / [Пропустити].
  The tour runs only on click.
- **Goal: feature overview** — one guided walk covering logbook, analytics,
  service intervals, receipt scan (the "what's here" tour).
- **One tour, not five.** Collapse into a single `overview` tour that walks the
  key surfaces. The Settings launcher keeps letting users replay it.

## The four polish fixes (from user feedback)

1. **Lock page scroll during the tour.** The page currently scrolls freely while
   the tour runs. Lock body scroll for the tour's lifetime; the tour itself
   auto-scrolls each target into the safe-area centre (smooth), and manual scroll
   is disabled so the spotlight can't be knocked off target.
2. **Animate the spotlight between steps.** Today `place()` writes top/left every
   frame with no transition, so the highlight vanishes and snaps to the next
   target. Add a CSS transition on the ring + mask panels so the spotlight glides
   to the next target. Only tween when the target *changes* (a new step), not
   during per-frame tracking of a moving/scrolling target (which must stay exact).
3. **Visual tap on page changes.** When a step lives on another route, play an
   animated finger-tap on the nav tab/element being "pressed" before navigating,
   so the jump reads as a deliberate action, not a teleport.
4. **Make Skip obvious.** The skip control is a tiny top-right text link nobody
   notices. Give it real presence (a clearly labelled button), and keep the X /
   Escape / backdrop affordances.

## Implementation

- `tourSteps.js`: replace the 5 tours with one `overview` tour (keep the getter/
  i18n pattern, `tap`/`demo`/`path` data). Keep `TOUR_ORDER` = `['overview']`.
- `TourOverlay.jsx`:
  - Delete `PAGE_TOURS` + the auto-show effect.
  - Body scroll lock while `active` (shared with Modal's approach, restored on
    stop).
  - Spotlight transition: add a `transitioning` flag set on step change; apply a
    CSS transition to ring + panels during it, clear it once settled so live
    tracking stays snap-exact.
  - Cross-route tap: when the next step's `stepPath` differs from the current
    URL, show the tap gesture over the destination nav item briefly, then
    navigate.
  - Redesign the callout footer: prominent Skip button; keep progress dots +
    n/total + Back/Next.
- `WelcomeTourCard.jsx` (new): the dashboard opt-in block. Dismiss (Пропустити)
  or Показати (starts the `overview` tour). Remembers dismissal per account
  (reuse the tours_seen mechanism or a dedicated flag), so it shows once.
- Dashboard: render the card at top on first visit only.
- i18n: rework `tour.*` keys for the single tour + welcome card, EN + UK.

## Out of scope

No new tour targets/features, no backend changes. Pure frontend.
