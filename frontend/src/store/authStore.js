import { create } from 'zustand';
import i18n, { LANG_KEY } from '../i18n';
import * as authApi from '../api/auth';
import { useCurrencyStore } from './currencyStore';
import { TOKEN_KEY, clearTokens, extractError, setTokens } from '../api/client';

// When an account arrives with a saved language and the browser has no explicit
// choice yet, adopt the account's language so a preference follows the user to a
// new device. Once they toggle, the local choice is stored and wins from then on.
function adoptAccountLanguage(user) {
  try {
    if (user?.language && !localStorage.getItem(LANG_KEY)) {
      if (i18n.language !== user.language) i18n.changeLanguage(user.language);
    }
  } catch {
    /* localStorage unavailable — keep the current UI language */
  }
}

export const useAuthStore = create((set, get) => ({
  token: localStorage.getItem(TOKEN_KEY),
  user: null,
  userLoading: false,

  async login(email, password) {
    const data = await authApi.login(email, password);
    setTokens(data);
    set({ token: data.access_token });
    const user = await authApi.getMe();
    set({ user });
    adoptAccountLanguage(user);
    useCurrencyStore.getState().adoptAccountCurrency(user?.currency);
    return user;
  },

  async register(email, password) {
    const account = await authApi.register(
      email,
      password,
      i18n.language,
      useCurrencyStore.getState().currency,
    );
    // Logging straight in would 403 while the address is unconfirmed; the
    // caller sends the user to /verify instead.
    if (account?.verification_sent) return { pendingVerification: true };
    await get().login(email, password);
    return { pendingVerification: false };
  },

  async fetchMe() {
    if (!get().token) return null;
    set({ userLoading: true });
    try {
      const user = await authApi.getMe();
      set({ user, userLoading: false });
      adoptAccountLanguage(user);
    useCurrencyStore.getState().adoptAccountCurrency(user?.currency);
      return user;
    } catch (error) {
      set({ userLoading: false });
      throw error;
    }
  },

  // Push a UI language change to the backend so emails, the Telegram bot and API
  // error details follow it. No-op when signed out or already in sync.
  async syncLanguage(lng) {
    const { token, user } = get();
    if (!token || !user || user.language === lng) return;
    try {
      const updated = await authApi.updateProfile({ language: lng });
      set({ user: updated });
    } catch {
      /* best-effort: the UI language still changed locally */
    }
  },

  async saveDisplayName(displayName) {
    const user = await authApi.updateMe(displayName);
    set({ user });
    return user;
  },

  async updateSettings(payload) {
    const user = await authApi.updateProfile(payload);
    set({ user });
    return user;
  },

  // Changing the password revokes every OTHER session; the server hands back a
  // fresh pair for THIS one, so we swap the stored tokens and stay signed in.
  async changePassword(currentPassword, newPassword) {
    const data = await authApi.changePassword(currentPassword, newPassword);
    setTokens(data);
    set({ token: data.access_token });
  },

  async deleteAccount(password) {
    await authApi.deleteAccount(password);
    // The account is gone; drop the now-dead tokens and user like a logout.
    clearTokens();
    await purgeApiCache();
    set({ token: null, user: null });
  },

  logout() {
    clearTokens();
    // Purge the service-worker api-cache too: without this, the next person to
    // sign in on a shared device could be served this user's cached cars/logs
    // (NetworkFirst falls back to cache when offline/slow).
    purgeApiCache();
    set({ token: null, user: null });
  },
}));

// Keep the backend in step with the UI language once signed in, so emails, the
// Telegram bot and API errors follow the toggle. Registered once at module load.
i18n.on('languageChanged', (lng) => {
  useAuthStore.getState().syncLanguage(lng);
});

async function purgeApiCache() {
  if (typeof caches === 'undefined') return;
  try {
    await caches.delete('api-cache');
  } catch {
    /* best-effort: a failed purge must not block sign-out */
  }
}

export { extractError };
