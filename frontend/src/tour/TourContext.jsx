import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { useAuthStore } from '../store/authStore';
import { markTourSeen as markTourSeenApi } from '../api/auth';
import { TOURS } from './tourSteps';

// Which tours a user has already been shown, kept per account so a second
// account on the same browser gets its own onboarding. Shape: { [userId]: [names] }.
const SEEN_KEY = 'kapot_tours_seen';

function readSeen() {
  try {
    return JSON.parse(localStorage.getItem(SEEN_KEY)) || {};
  } catch {
    return {};
  }
}

function writeSeen(map) {
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify(map));
  } catch {
    /* private mode — tours simply auto-show again next time */
  }
}

const TourContext = createContext(null);

export function TourProvider({ children }) {
  const userId = useAuthStore((s) => s.user?.id);
  const serverSeen = useAuthStore((s) => s.user?.tours_seen);
  const seenKey = userId != null ? String(userId) : 'anon';

  const [tour, setTour] = useState(null); // active tour name, or null
  const [index, setIndex] = useState(0);
  // A tour counts as seen if EITHER the account has recorded it (server, the
  // source of truth across devices) OR this browser has (localStorage, so an
  // older user who saw it here before the server-side move isn't shown it again).
  const [seen, setSeen] = useState(
    () => new Set([...(readSeen()[seenKey] || []), ...(serverSeen || [])]),
  );

  // Rebuild the seen set when the account (or its server-side tours) changes.
  useEffect(() => {
    setSeen(new Set([...(readSeen()[seenKey] || []), ...(serverSeen || [])]));
  }, [seenKey, serverSeen]);

  const markSeen = useCallback(
    (name) => {
      setSeen((prev) => {
        if (prev.has(name)) return prev;
        const nextSeen = new Set(prev);
        nextSeen.add(name);
        // localStorage: instant, offline-safe local cache.
        const map = readSeen();
        map[seenKey] = [...nextSeen];
        writeSeen(map);
        // Server: the durable, cross-device record. Best-effort — a failed sync
        // just means the browser cache carries it until the next successful one.
        if (userId != null) markTourSeenApi(name).catch(() => {});
        return nextSeen;
      });
    },
    [seenKey, userId],
  );

  const wasSeen = useCallback((name) => seen.has(name), [seen]);

  const start = useCallback(
    (name) => {
      if (!TOURS[name]) return;
      setTour(name);
      setIndex(0);
      // Starting a tour (manually or automatically) means it never auto-shows
      // again for this account.
      markSeen(name);
    },
    [markSeen],
  );

  const stop = useCallback(() => setTour(null), []);

  const steps = tour ? TOURS[tour].steps : [];

  const next = useCallback(() => {
    setIndex((i) => {
      if (i >= steps.length - 1) {
        stop();
        return 0;
      }
      return i + 1;
    });
  }, [steps.length, stop]);

  const prev = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);
  const goTo = useCallback((i) => setIndex(i), []);

  const value = useMemo(
    () => ({ tour, steps, index, active: tour !== null, start, stop, next, prev, goTo, wasSeen }),
    [tour, steps, index, start, stop, next, prev, goTo, wasSeen],
  );

  return <TourContext.Provider value={value}>{children}</TourContext.Provider>;
}

export function useTour() {
  const ctx = useContext(TourContext);
  if (!ctx) throw new Error('useTour must be used within TourProvider');
  return ctx;
}
