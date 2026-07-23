import { create } from 'zustand';
import * as authApi from '../api/auth';
import { TOKEN_KEY } from '../api/client';
import { UNITS_KEY, DEFAULT_UNIT_SYSTEM, normalizeUnitSystem } from '../units';

// The display unit system (metric / imperial), mirrored to localStorage and —
// once signed in — to the backend, exactly like the currency. A stored local
// choice always wins; otherwise a new account adopts metric and a returning one
// adopts its saved system.
function initialUnits() {
  try {
    const stored = localStorage.getItem(UNITS_KEY);
    if (stored) return normalizeUnitSystem(stored);
  } catch {
    /* private mode — fall through to default */
  }
  return DEFAULT_UNIT_SYSTEM;
}

export const useUnitStore = create((set, get) => ({
  units: initialUnits(),

  setUnits(code) {
    const next = normalizeUnitSystem(code);
    if (next === get().units) return;
    set({ units: next });
    try {
      localStorage.setItem(UNITS_KEY, next);
    } catch {
      /* ignore */
    }
    try {
      if (localStorage.getItem(TOKEN_KEY)) {
        authApi.updateProfile({ unit_system: next }).catch(() => {});
      }
    } catch {
      /* ignore */
    }
  },

  // On login/fetchMe: adopt the account's system only when the browser has no
  // explicit choice yet, so a preference follows the user to a new device.
  adoptAccountUnits(code) {
    try {
      if (!localStorage.getItem(UNITS_KEY) && code) {
        const next = normalizeUnitSystem(code);
        if (next !== get().units) set({ units: next });
      }
    } catch {
      /* ignore */
    }
  },
}));

// Read the current system outside React (format.js is a plain util).
export function currentUnits() {
  return useUnitStore.getState().units;
}
