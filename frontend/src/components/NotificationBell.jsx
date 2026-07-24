import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Bell, X } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useNotificationStore } from '../store/notificationStore';
import NotificationModal from './NotificationModal';

// The persistent header bell: an unread-count badge, opening the recent-alerts
// modal. Refreshes on mount, on route change, and when the tab regains focus —
// reusing the one /notifications fetch (which also reconciles history server
// side), so there's no separate polling timer.
export default function NotificationBell() {
  const { t } = useTranslation();
  const token = useAuthStore((s) => s.token);
  const unread = useNotificationStore((s) => s.unread);
  const refresh = useNotificationStore((s) => s.refresh);
  const markRead = useNotificationStore((s) => s.markRead);
  const location = useLocation();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!token) return undefined;
    refresh();
    const onFocus = () => refresh();
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [token, location.pathname, refresh]);

  // The bell toggles the tray: tapping it while open closes it (the icon is an X
  // then), so it doubles as the close control the user expects.
  const toggle = () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    markRead(); // opening the centre clears the badge
  };

  const badge = unread > 9 ? '9+' : String(unread);

  return (
    <>
      <button
        type="button"
        onClick={toggle}
        aria-label={open ? t('common.close') : t('notificationCentre.open')}
        aria-expanded={open}
        className="relative flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl text-mist transition-colors hover:bg-panel hover:text-fg"
      >
        {open ? <X className="h-5 w-5" /> : <Bell className="h-5 w-5" />}
        {!open && unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-crit px-1 text-[10px] font-bold leading-none text-white">
            {badge}
          </span>
        )}
      </button>
      <NotificationModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
