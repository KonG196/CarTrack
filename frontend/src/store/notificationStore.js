import { create } from 'zustand';
import { getNotifications, markNotificationsRead } from '../api/notifications';

// Drives the header bell: the live nudge list, the count, and the unread badge.
// One fetch feeds both the badge and the modal, so opening the centre needs no
// second round-trip. The fetch is best-effort — a failure just leaves the last
// good state (an empty badge is better than a broken header).
export const useNotificationStore = create((set, get) => ({
  items: [],
  unread: 0,
  loaded: false,

  async refresh() {
    try {
      const data = await getNotifications();
      set({ items: data.items || [], unread: data.unread || 0, loaded: true });
    } catch {
      // keep the previous state; the header must never break on this
    }
  },

  // Opening the centre marks everything read; clear the badge immediately for a
  // snappy feel, then confirm with the server.
  async markRead() {
    if (get().unread === 0) return;
    set({ unread: 0 });
    try {
      await markNotificationsRead();
    } catch {
      // if it fails, the next refresh restores the true count
    }
  },
}));
