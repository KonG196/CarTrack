import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { AlertTriangle, Bell, ArrowRight } from 'lucide-react';
import { Card } from './UI';
import useAnimatedPresence from '../hooks/useAnimatedPresence';
import { useNotificationStore } from '../store/notificationStore';

const SEVERITY_COLOR = { crit: 'text-crit', warn: 'text-amber', info: 'text-mist' };
const CLOSE_MS = 160;

// The recent-notifications popover behind the header bell. Not a centred modal:
// it drops down from under the header (no backdrop blur), like a real
// notifications tray. A transparent full-screen layer catches an outside tap to
// close. Reads the store the bell already filled — no second fetch.
export default function NotificationModal({ open, onClose }) {
  const { t } = useTranslation();
  const items = useNotificationStore((s) => s.items);
  const { mounted, closing, requestClose } = useAnimatedPresence(open, onClose, CLOSE_MS);
  const panelRef = useRef(null);

  useEffect(() => {
    if (!mounted) return undefined;
    const onKey = (e) => e.key === 'Escape' && requestClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [mounted, requestClose]);

  if (!mounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-[45]" data-closing={closing ? 'true' : undefined}>
      {/* Catch outside taps to close — no blur, no dark veil. */}
      <button
        type="button"
        aria-hidden="true"
        tabIndex={-1}
        onClick={requestClose}
        className="absolute inset-0 h-full w-full cursor-default bg-transparent"
      />
      {/* The tray, pinned under the sticky header and centred to the app column. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 px-3 pt-[calc(env(safe-area-inset-top)+3.5rem)]">
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="false"
          aria-label={t('notificationCentre.title')}
          className={`notif-tray pointer-events-auto mx-auto max-w-md rounded-2xl border border-edge bg-panel p-3 shadow-2xl shadow-black/60 ${
            closing ? 'is-closing' : ''
          }`}
        >
          <div className="mb-2 flex items-center justify-between px-1">
            <h2 className="font-display text-sm font-semibold text-fg">
              {t('notificationCentre.title')}
            </h2>
          </div>

          <div className="max-h-[60dvh] space-y-2 overflow-y-auto overscroll-contain">
            {items.length === 0 ? (
              <p className="py-6 text-center text-sm text-mist">
                {t('notificationCentre.empty')}
              </p>
            ) : (
              items.map((note) => {
                const Icon = note.severity === 'info' ? Bell : AlertTriangle;
                const row = (
                  <Card className="flex items-start gap-3 p-3">
                    <Icon
                      className={`mt-0.5 h-4 w-4 flex-shrink-0 ${
                        SEVERITY_COLOR[note.severity] || 'text-mist'
                      }`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-fg">{note.title}</p>
                      <p className="mt-0.5 text-xs text-mist">{note.body}</p>
                      <p className="mt-0.5 text-[11px] text-mist/70">{note.car_label}</p>
                    </div>
                  </Card>
                );
                return note.action ? (
                  <Link
                    key={note.id}
                    to={note.action}
                    onClick={requestClose}
                    className="block active:opacity-70"
                  >
                    {row}
                  </Link>
                ) : (
                  <div key={note.id}>{row}</div>
                );
              })
            )}
          </div>

          <Link
            to="/notifications"
            onClick={requestClose}
            className="mt-2 flex items-center justify-center gap-1.5 rounded-xl border border-edge py-2.5 text-sm font-medium text-mist transition-colors hover:border-edge-soft hover:text-fg"
          >
            {t('notificationCentre.seeAll')}
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </div>,
    document.body,
  );
}
