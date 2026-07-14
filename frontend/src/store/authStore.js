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
    await authApi.register(email, password);
    return get().login(email, password);
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

  logout() {
    localStorage.removeItem(TOKEN_KEY);
    set({ token: null, user: null });
  },
}));

export { extractError };
