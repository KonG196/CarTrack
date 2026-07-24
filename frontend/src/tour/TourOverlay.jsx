import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';

import { useCarStore } from '../store/carStore';
import { useTour } from './TourContext';

const PAD = 8;
// Room the callout needs on one side of the spotlight. If the target sits too
// low to leave this much below it, the callout moves to the top instead.
const CALLOUT_SPACE = 250;
// Fixed chrome the target must clear when centred: sticky header, bottom nav.
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

function place(el, top, left, width, height) {
  if (!el) return;
  el.style.top = `${top}px`;
  el.style.left = `${left}px`;
  el.style.width = `${Math.max(0, width)}px`;
  el.style.height = `${Math.max(0, height)}px`;
}

export default function TourOverlay() {
  const { t } = useTranslation();
  const { active, tour, index, steps, next, prev, stop } = useTour();
  const step = active ? steps[index] : null;
  const navigate = useNavigate();
  const location = useLocation();
  const firstLogId = useCarStore((s) => s.logs?.items?.[0]?.id);
  const [ready, setReady] = useState(false);
  const [calloutPos, setCalloutPos] = useState('bottom');

  const panelTop = useRef(null);
  const panelBottom = useRef(null);
  const panelLeft = useRef(null);
  const panelRight = useRef(null);
  const blocker = useRef(null);
  const ring = useRef(null);
  const tap = useRef(null);

  // A step's page: a string, or a function of context. null means «skip». May
  // carry a query (?tab=), so compare against the full URL.
  const stepPath = useMemo(() => {
    if (!step?.path) return undefined;
    return typeof step.path === 'function' ? step.path({ firstLogId }) : step.path;
  }, [step, firstLogId]);
  const currentUrl = location.pathname + location.search;

  useEffect(() => {
    if (step?.path && stepPath === null) next();
  }, [step, stepPath, next]);

  // A route change is staged as a visible tap on the bottom-nav item, THEN the
  // navigation — so moving between pages reads as a deliberate press, not a
  // teleport. navTap holds the {x, y} the finger animates over; it clears once
  // we navigate. A step with no `nav` (or a missing element) just navigates.
  const [navTap, setNavTap] = useState(null);
  useEffect(() => {
    if (!stepPath || stepPath === currentUrl) {
      setNavTap(null);
      return undefined;
    }
    const navEl = step?.nav
      ? document.querySelector(`[data-tour="${step.nav}"]`)
      : null;
    if (!navEl) {
      navigate(stepPath);
      return undefined;
    }
    const r = navEl.getBoundingClientRect();
    setNavTap({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
    // Let the tap animation play before the route swaps.
    const id = setTimeout(() => {
      setNavTap(null);
      navigate(stepPath);
    }, 620);
    return () => clearTimeout(id);
  }, [stepPath, currentUrl, step, navigate]);

  // Position and TRACK the spotlight imperatively, once per frame, straight off
  // the element's live rect. This is what keeps the highlight exactly on target
  // on iOS — where a programmatic scroll applies a frame late, so a one-shot
  // measure lands in the wrong place. Change-detected, so a stationary target is
  // a no-op (no layout writes, no React re-renders) — smooth, not stuttery.
  // The loop below reads the current target from here, so a step change just
  // updates this ref — no rAF teardown/restart, which is what stranded the
  // spotlight on the previous step. null = navigating (nothing to show yet).
  const targetRef = useRef(null);
  useEffect(() => {
    targetRef.current =
      !step || (stepPath && stepPath !== currentUrl)
        ? null
        : { target: step.target, tap: step.tap, demo: step.demo, key: `${tour}-${index}` };
  }, [step, stepPath, currentUrl, tour, index]);

  // ONE rAF loop for the life of the tour. Every frame it reads the live rect of
  // the current target and positions the spotlight to match — always exact on
  // iOS (where a programmatic scroll lands a frame late). Change-detected, so a
  // stationary target is a no-op: no layout writes, no React re-renders, smooth.
  useEffect(() => {
    if (!active) {
      setReady(false);
      return undefined;
    }
    let raf;
    let scrolledKey = null;
    let pollKey = null;
    let pollStart = 0;
    let lastKey = '';
    let lastTapKey = '';
    let lastPos = null;
    let shown = false;
    // Step-change animation: when the spotlight moves to a NEW target it should
    // glide there; while tracking the SAME (possibly scrolling) target it must
    // stay frame-exact. So transitions are switched on only for the ~360ms after
    // a step key changes, then off. `stepKey` is the current step, `moveTimer`
    // the handle that turns the glide back off.
    let stepKey = null;
    let moveTimer = null;
    const movers = () =>
      [panelTop, panelBottom, panelLeft, panelRight, blocker, ring]
        .map((r) => r.current)
        .filter(Boolean);
    const setMoving = (on) =>
      movers().forEach((el) => el.classList.toggle('tour-move', on));

    const tick = (now) => {
      raf = requestAnimationFrame(tick);
      const cur = targetRef.current;
      if (!cur) {
        if (shown) {
          shown = false;
          setReady(false);
        }
        return;
      }
      const el = document.querySelector(`[data-tour="${cur.target}"]`);
      if (!el) {
        // Poll ~2.5s for a mounting element, then skip the step.
        if (pollKey !== cur.key) {
          pollKey = cur.key;
          pollStart = now;
        }
        if (now - pollStart > 2500) next();
        return;
      }
      // On a new step, glide the spotlight to it — but only if one was already
      // showing (so the very first target appears instantly, not sliding in from
      // the corner). Turn the transition back off after it settles so per-frame
      // tracking of the target stays exact.
      if (stepKey !== cur.key) {
        stepKey = cur.key;
        if (shown) {
          setMoving(true);
          if (moveTimer) clearTimeout(moveTimer);
          moveTimer = setTimeout(() => setMoving(false), 380);
        }
      }
      let r = el.getBoundingClientRect();
      // Scroll into the safe-area centre once per step, and only if meaningfully
      // off — an in-view target is left alone (no jumping). Smooth so it reads as
      // guided movement, matching the spotlight glide.
      if (scrolledKey !== cur.key) {
        scrolledKey = cur.key;
        const safeCentre = (SAFE_TOP + (window.innerHeight - SAFE_BOTTOM)) / 2;
        const delta = r.top + r.height / 2 - safeCentre;
        if (Math.abs(delta) > 40) {
          window.scrollBy({ top: delta, behavior: 'smooth' });
          r = el.getBoundingClientRect();
        }
      }
      const top = r.top - PAD;
      const left = r.left - PAD;
      const w = r.width + PAD * 2;
      const h = r.height + PAD * 2;
      // The step key is part of the change key, so a new step always repositions
      // even if the coordinates happen to match.
      const key = `${cur.key}|${Math.round(top)},${Math.round(left)},${Math.round(w)},${Math.round(h)}`;
      if (key !== lastKey) {
        lastKey = key;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        place(panelTop.current, 0, 0, vw, top);
        place(panelBottom.current, top + h, 0, vw, vh - (top + h));
        place(panelLeft.current, top, 0, left, h);
        place(panelRight.current, top, left + w, vw - (left + w), h);
        place(blocker.current, top, left, w, h);
        place(ring.current, top, left, w, h);
        const p = pickCalloutSide(r);
        if (p !== lastPos) {
          lastPos = p;
          setCalloutPos(p);
        }
      }
      if (cur.tap && tap.current) {
        const de = cur.demo ? el.querySelector(cur.demo) : null;
        const tb = (de || el).getBoundingClientRect();
        const tapKey = `${cur.key}|${Math.round(tb.left + tb.width / 2)},${Math.round(tb.top + tb.height / 2)}`;
        if (tapKey !== lastTapKey) {
          lastTapKey = tapKey;
          tap.current.style.left = `${tb.left + tb.width / 2}px`;
          tap.current.style.top = `${tb.top + tb.height / 2}px`;
        }
      }
      if (!shown) {
        shown = true;
        setReady(true);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, next]);

  // Loop the in-place demo (copy icon → checkmark) while a demo step is open.
  useEffect(() => {
    if (!step?.demo || (stepPath && stepPath !== currentUrl)) return undefined;
    let interval;
    const fire = () =>
      document
        .querySelector(`[data-tour="${step.target}"]`)
        ?.querySelector(step.demo)
        ?.dispatchEvent(new CustomEvent('kapot:tour-demo'));
    const timer = setTimeout(() => {
      fire();
      interval = setInterval(fire, 2600);
    }, 1050);
    return () => {
      clearTimeout(timer);
      clearInterval(interval);
    };
  }, [step, stepPath, currentUrl]);

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

  // Block MANUAL scroll while the tour runs — a stray swipe would knock the
  // spotlight off its target — while still letting the tour's own scrollBy move
  // the page. So this cancels user gestures (wheel / touchmove) rather than
  // setting overflow:hidden, which would also freeze the programmatic scroll.
  useEffect(() => {
    if (!active) return undefined;
    const block = (e) => e.preventDefault();
    // passive:false is required for preventDefault to take on these listeners.
    window.addEventListener('wheel', block, { passive: false });
    window.addEventListener('touchmove', block, { passive: false });
    return () => {
      window.removeEventListener('wheel', block, { passive: false });
      window.removeEventListener('touchmove', block, { passive: false });
    };
  }, [active]);

  if (!step) return null;

  const isLast = index === steps.length - 1;

  // The spotlight elements carry NO position from React — the rAF loop above owns
  // their top/left/width/height. Visibility is gated on `ready` (inherited by the
  // fixed children) so nothing flashes before the first positioning frame.
  return (
    <div style={{ visibility: ready ? 'visible' : 'hidden' }}>
      <div ref={panelTop} className="fixed z-[60] bg-black/60" />
      <div ref={panelBottom} className="fixed z-[60] bg-black/60" />
      <div ref={panelLeft} className="fixed z-[60] bg-black/60" />
      <div ref={panelRight} className="fixed z-[60] bg-black/60" />
      {/* Transparent blocker over the target: a stray tap advances rather than
          firing the real control. */}
      <div ref={blocker} className="fixed z-[61]" onClick={next} aria-hidden="true" />
      <div
        ref={ring}
        className="pointer-events-none fixed z-[62] rounded-xl ring-2 ring-amber"
      />
      {step.tap && (
        <div
          ref={tap}
          className="pointer-events-none fixed z-[62] h-6 w-6"
          style={{ transform: 'translate(-50%, -50%)' }}
          aria-hidden="true"
        >
          <span className="tour-tap-ripple absolute inset-0 rounded-full border-2 border-amber/80" />
          <span className="tour-tap-dot absolute inset-[5px] rounded-full bg-amber shadow-lg shadow-amber/50" />
        </div>
      )}

      {/* One-shot tap over the bottom-nav item being opened, just before the
          route changes — so a page jump reads as a deliberate press. `key` on
          the coords restarts the animation for each navigation. */}
      {navTap && (
        <div
          key={`${navTap.x},${navTap.y}`}
          className="tour-nav-tap pointer-events-none fixed z-[64] h-9 w-9"
          style={{ left: navTap.x, top: navTap.y, transform: 'translate(-50%, -50%)' }}
          aria-hidden="true"
        >
          <span className="absolute inset-0 rounded-full border-2 border-amber" />
          <span className="absolute inset-[7px] rounded-full bg-amber shadow-lg shadow-amber/60" />
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
          <div className="mb-2 flex items-center justify-between gap-2">
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
            {/* An obvious close: the tiny text «Skip» went unnoticed. */}
            <button
              type="button"
              onClick={stop}
              aria-label={t('tour.skip')}
              className="-mr-1 -mt-1 flex h-9 w-9 items-center justify-center rounded-lg text-mist transition-colors hover:bg-raised hover:text-fg"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <h3 className="font-display text-base font-semibold text-fg">{step.title}</h3>
          <p className="mt-1 text-sm leading-snug text-mist">{step.body}</p>
          <div className="mt-3 flex items-center justify-between gap-2">
            {/* A clearly-labelled way out, next to the step counter, since the
                spotlight leaves no doubt the tour is running. */}
            <button
              type="button"
              onClick={stop}
              className="text-xs font-medium text-mist underline decoration-mist/40 underline-offset-2 transition-colors hover:text-fg"
            >
              {t('tour.skipTour')}
            </button>
            <span className="ml-auto mr-2 font-mono text-[11px] tabular-nums text-mist/70">
              {index + 1} / {steps.length}
            </span>
            <div className="flex items-center gap-2">
              {index > 0 && (
                <button
                  type="button"
                  onClick={prev}
                  className="rounded-lg px-3 py-1.5 text-sm text-mist transition-colors hover:text-fg"
                >
                  {t('tour.back')}
                </button>
              )}
              <button
                type="button"
                onClick={next}
                className="rounded-lg bg-amber px-4 py-1.5 text-sm font-semibold text-amber-ink transition active:scale-95 motion-reduce:active:scale-100"
              >
                {isLast ? t('tour.done') : t('tour.next')}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
