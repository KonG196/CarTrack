import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { useAuthStore } from '../store/authStore';
import { useCarStore } from '../store/carStore';
import { useTour } from './TourContext';

// The section tour that auto-shows the first time the account lands on a page.
const PAGE_TOURS = {
  '/': 'home',
  '/logbook': 'logbook',
  '/add': 'add',
  '/analytics': 'analytics',
  '/garage': 'settings',
};

const PAD = 8;
// Room the callout needs on one side of the spotlight. If the target sits too
// low to leave this much below it, the callout moves to the top instead — the
// two must never overlap.
const CALLOUT_SPACE = 250;
// Fixed chrome the target must clear when centred: the sticky header and the
// bottom nav bar.
const SAFE_TOP = 56;
const SAFE_BOTTOM = 72;

function pickCalloutSide(r) {
  const vh = window.innerHeight;
  const below = vh - (r.top + r.height);
  const above = r.top;
  if (below >= CALLOUT_SPACE) return 'bottom';
  if (above >= CALLOUT_SPACE) return 'top';
  return below >= above ? 'bottom' : 'top';
}

// Four fixed panels frame the spotlight — a single element cannot dim around a
// cutout, but four around the rectangle can. No backdrop-blur and no geometry
// transition on purpose: animating either is what stuttered on iOS, and an
// instant reposition also lets the spotlight track scrolling exactly.
function DimPanels({ hole }) {
  const cls = 'fixed z-[60] bg-black/60';
  return (
    <>
      <div className={cls} style={{ top: 0, left: 0, right: 0, height: Math.max(0, hole.top) }} />
      <div className={cls} style={{ top: hole.top + hole.height, left: 0, right: 0, bottom: 0 }} />
      <div
        className={cls}
        style={{ top: hole.top, left: 0, width: Math.max(0, hole.left), height: hole.height }}
      />
      <div
        className={cls}
        style={{ top: hole.top, left: hole.left + hole.width, right: 0, height: hole.height }}
      />
    </>
  );
}

export default function TourOverlay() {
  const { active, tour, index, steps, next, prev, stop, start, wasSeen } = useTour();
  const step = active ? steps[index] : null;
  const navigate = useNavigate();
  const location = useLocation();
  const firstLogId = useCarStore((s) => s.logs?.items?.[0]?.id);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const userReady = useAuthStore((s) => !!s.user);
  const [rect, setRect] = useState(null);
  const [tapPoint, setTapPoint] = useState(null);
  const [calloutPos, setCalloutPos] = useState('bottom');

  // Auto-show a section's tour the first time this account opens its page. Wait
  // for the account and a car (the tours point at car data), and give the page a
  // beat to settle before starting.
  useEffect(() => {
    const name = PAGE_TOURS[location.pathname];
    if (!name || active || !userReady || !activeCarId || wasSeen(name)) return undefined;
    const id = setTimeout(() => start(name), 800);
    return () => clearTimeout(id);
  }, [location.pathname, active, userReady, activeCarId, wasSeen, start]);

  // A step's page: a string, or a function of context (the logbook detail needs
  // a real id). null means «skip this step» — e.g. an empty journal. A path may
  // carry a query (?tab=) — the analytics tabs — so compare against the full URL.
  const stepPath = useMemo(() => {
    if (!step?.path) return undefined;
    return typeof step.path === 'function' ? step.path({ firstLogId }) : step.path;
  }, [step, firstLogId]);
  const currentUrl = location.pathname + location.search;

  useEffect(() => {
    if (step?.path && stepPath === null) next();
  }, [step, stepPath, next]);

  useEffect(() => {
    if (stepPath && stepPath !== currentUrl) navigate(stepPath);
  }, [stepPath, currentUrl, navigate]);

  // Find the target, scroll it toward the middle so a callout fits on either
  // side, and measure. Poll while the page mounts; skip the step if the element
  // never appears. `rect` stays null until the target is measured, so the page
  // is never dimmed with no spotlight to show.
  useEffect(() => {
    if (!step) return undefined;
    if (stepPath && stepPath !== currentUrl) {
      setRect(null);
      setTapPoint(null);
      return undefined;
    }
    let tries = 0;
    let retry;
    let raf;
    let demoTimer;
    let demoInterval;
    let cleanup = () => {};

    // The «tap here» gesture sits on the sub-control the user should press: the
    // demo element (e.g. the copy button) when there is one, otherwise the
    // spotlight's centre.
    const measureTap = (el) => {
      if (!step.tap) {
        setTapPoint(null);
        return;
      }
      const de = step.demo ? el.querySelector(step.demo) : null;
      const box = (de || el).getBoundingClientRect();
      setTapPoint({ x: box.left + box.width / 2, y: box.top + box.height / 2 });
    };

    const attach = () => {
      const el = document.querySelector(`[data-tour="${step.target}"]`);
      if (!el) {
        if (tries++ < 15) retry = setTimeout(attach, 150);
        else next();
        return;
      }
      const measure = () => {
        const rr = el.getBoundingClientRect();
        setRect(rr);
        setCalloutPos(pickCalloutSide(rr));
        measureTap(el);
      };
      // Centre the target in the safe area (below the sticky header, above the
      // bottom nav) so a callout fits on whichever side has room. Instant, and
      // idempotent — recomputed from the live position, so re-running converges.
      const align = () => {
        const b = el.getBoundingClientRect();
        const safeCentre = (SAFE_TOP + (window.innerHeight - SAFE_BOTTOM)) / 2;
        window.scrollBy({ top: b.top + b.height / 2 - safeCentre });
        measure();
      };
      measure();
      // Re-align across the opening seconds of the step: a frame later (to outlast
      // the route's scroll-to-top reset, which fires in this same commit), then at
      // a spread of delays so late-loading content — charts fetch their data and
      // reflow the page, moving elements without any scroll event — still ends up
      // centred with the spotlight on it.
      raf = requestAnimationFrame(align);
      const timers = [260, 620, 1100, 1700, 2400].map((d) => setTimeout(align, d));
      window.addEventListener('resize', measure);
      window.addEventListener('scroll', measure, true);
      // Play the real in-place result while the step is open: dispatch a demo
      // event the control listens for (the copy icon flips to a checkmark, holds,
      // reverts) and loop it so the demonstration keeps repeating.
      if (step.demo) {
        const fire = () =>
          el.querySelector(step.demo)?.dispatchEvent(new CustomEvent('kapot:tour-demo'));
        demoTimer = setTimeout(() => {
          fire();
          demoInterval = setInterval(fire, 2600);
        }, 1050);
      }
      cleanup = () => {
        timers.forEach(clearTimeout);
        window.removeEventListener('resize', measure);
        window.removeEventListener('scroll', measure, true);
      };
    };
    attach();
    return () => {
      clearTimeout(retry);
      cancelAnimationFrame(raf);
      clearTimeout(demoTimer);
      clearInterval(demoInterval);
      cleanup();
    };
  }, [step, stepPath, currentUrl, next]);

  useEffect(() => {
    if (!active) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') stop();
      if (e.key === 'ArrowRight') next();
      if (e.key === 'ArrowLeft') prev();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [active, next, prev, stop]);

  if (!step) return null;

  const isLast = index === steps.length - 1;
  const hole = rect
    ? {
        top: rect.top - PAD,
        left: rect.left - PAD,
        width: rect.width + PAD * 2,
        height: rect.height + PAD * 2,
      }
    : null;

  // Never dim the screen without a spotlight to show — that reads as broken.
  // Hold the overlay back until the target is measured.
  if (!hole) return null;

  return (
    <>
      <DimPanels hole={hole} />
      {/* A transparent blocker over the target so a stray tap does not fire
          the real control mid-tour. Tapping it, like the callout, advances. */}
      <div
        className="fixed z-[61]"
        style={{ top: hole.top, left: hole.left, width: hole.width, height: hole.height }}
        onClick={next}
        aria-hidden="true"
      />
      <div
        className="pointer-events-none fixed z-[62] rounded-xl ring-2 ring-amber"
        style={{ top: hole.top, left: hole.left, width: hole.width, height: hole.height }}
      />
      {step.tap && tapPoint && (
        <div
          className="pointer-events-none fixed z-[62] h-6 w-6"
          style={{ left: tapPoint.x, top: tapPoint.y, transform: 'translate(-50%, -50%)' }}
          aria-hidden="true"
        >
          <span className="tour-tap-ripple absolute inset-0 rounded-full border-2 border-amber/80" />
          <span className="tour-tap-dot absolute inset-[5px] rounded-full bg-amber shadow-lg shadow-amber/50" />
        </div>
      )}

      {/* The callout sits opposite the spotlight — bottom by default, top when
          the highlighted element is low — so it never covers the target. */}
      <div
        className={`fixed inset-x-0 z-[63] px-4 ${
          calloutPos === 'top'
            ? 'top-0 pt-[max(env(safe-area-inset-top),1rem)]'
            : 'bottom-0 pb-[max(env(safe-area-inset-bottom),1rem)]'
        }`}
      >
        <div
          key={`${tour}-${index}`}
          className="tour-callout mx-auto max-w-md rounded-2xl border border-amber/60 bg-panel p-4 shadow-xl shadow-black/60"
        >
          <div className="mb-1 flex items-center justify-between gap-2">
            <div className="flex gap-1" aria-hidden="true">
              {steps.map((_, i) => (
                <span
                  key={i}
                  className={`h-1 w-4 rounded-full transition-colors ${
                    i === index ? 'bg-amber' : 'bg-edge-soft'
                  }`}
                />
              ))}
            </div>
            <button
              type="button"
              onClick={stop}
              className="text-xs text-mist transition-colors hover:text-fg"
            >
              Пропустити
            </button>
          </div>
          <h3 className="font-display text-base font-semibold text-fg">{step.title}</h3>
          <p className="mt-1 text-sm leading-snug text-mist">{step.body}</p>
          <div className="mt-3 flex items-center justify-between gap-2">
            <span className="font-mono text-[11px] tabular-nums text-mist/70">
              {index + 1} / {steps.length}
            </span>
            <div className="flex items-center gap-2">
              {index > 0 && (
                <button
                  type="button"
                  onClick={prev}
                  className="rounded-lg px-3 py-1.5 text-sm text-mist transition-colors hover:text-fg"
                >
                  Назад
                </button>
              )}
              <button
                type="button"
                onClick={next}
                className="rounded-lg bg-amber px-4 py-1.5 text-sm font-semibold text-amber-ink transition active:scale-95 motion-reduce:active:scale-100"
              >
                {isLast ? 'Готово' : 'Далі'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
