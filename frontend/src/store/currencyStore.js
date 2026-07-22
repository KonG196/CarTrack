import { create } from 'zustand';
import * as authApi from '../api/auth';
import { TOKEN_KEY } from '../api/client';
import { CURRENCY_KEY, DEFAULT_CURRENCY, currencyInfo, normalizeCurrency } from '../currency';

// The display currency, mirrored to localStorage and (once signed in) to the
// backend, exactly like the language. A stored local choice always wins;
// otherwise a new account adopts USD and a returning one adopts its saved code.
function initialCurrency() {
  try {
    const stored = localStorage.getItem(CURRENCY_KEY);
    if (stored) return normalizeCurrency(stored);
  } catch {
    /* private mode — fall through to the default */
  }
  return DEFAULT_CURRENCY;
}

export const useCurrencyStore = create((set, get) => ({
  currency: initialCurrency(),

  setCurrency(code) {
    const next = normalizeCurrency(code);
    if (next === get().currency) return;
    set({ currency: next });
    try {
      localStorage.setItem(CURRENCY_KEY, next);
    } catch {
      /* ignore */
    }
    // Push to the backend so the report PDF, bot and notifications use the same
    // symbol. Best-effort: a failed sync never blocks the UI change.
    try {
      if (localStorage.getItem(TOKEN_KEY)) {
        authApi.updateProfile({ currency: next }).catch(() => {});
      }
    } catch {
      /* ignore */
    }
  },

  // On login/fetchMe: adopt the account's currency only when the browser has no
  // explicit choice yet, so a preference follows the user to a new device.
  adoptAccountCurrency(code) {
    try {
      if (!localStorage.getItem(CURRENCY_KEY) && code) {
        const next = normalizeCurrency(code);
        if (next !== get().currency) set({ currency: next });
      }
    } catch {
      /* ignore */
    }
  },
}));

// Read the current currency outside React (format.js is a plain util).
export function currentCurrency() {
  return useCurrencyStore.getState().currency;
}

// The active currency symbol, for interpolating into labels/chart titles that
// aren't full money values (e.g. "Monthly spending, {{currency}}"). Components
// re-render on a switch via the App-level currency subscription.
export function currentCurrencySymbol() {
  return currencyInfo(useCurrencyStore.getState().currency).symbol;
}
