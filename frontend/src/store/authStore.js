import { create } from 'zustand';
import * as authApi from '../api/auth';
import { TOKEN_KEY, extractError } from '../api/client';

export const useAuthStore = create((set, get) => ({
  token: localStorage.getItem(TOKEN_KEY),
  user: null,
  userLoading: false,

  async login(email, password) {
    const { access_token } = await authApi.login(email, password);
    localStorage.setItem(TOKEN_KEY, access_token);
    set({ token: access_token });
    const user = await authApi.getMe();
    set({ user });
    return user;
  },

  async register(email, password) {
    const account = await authApi.register(email, password);
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
      return user;
    } catch (error) {
      set({ userLoading: false });
      throw error;
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

  logout() {
    localStorage.removeItem(TOKEN_KEY);
    set({ token: null, user: null });
  },
}));

export { extractError };
