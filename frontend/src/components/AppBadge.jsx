import { useEffect } from 'react';
import { getNotifications } from '../api/notifications';
import { loadDismissed, activeNotifications } from '../utils/notificationsDismiss';

// Mirror the active-notification count onto the installed-app icon badge
// (Badging API, progressively enhanced — a no-op where unsupported). Refreshes
// on mount and whenever the app returns to the foreground.
export default function AppBadge() {
  useEffect(() => {
    if (!('setAppBadge' in navigator)) return undefined;
    let cancelled = false;
    const refresh = () => {
      getNotifications()
        .then((data) => {
          if (cancelled) return;
          const count = activeNotifications(data.items, loadDismissed()).length;
          if (count > 0) navigator.setAppBadge(count).catch(() => {});
          else if (navigator.clearAppBadge) navigator.clearAppBadge().catch(() => {});
        })
        .catch(() => {});
    };
    refresh();
    const onVisible = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  return null;
}
