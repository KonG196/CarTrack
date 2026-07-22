import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { AlertTriangle, Bell, X } from 'lucide-react';
import { getNotifications } from '../api/notifications';
import {
  loadDismissed,
  saveDismissed,
  pruneDismissed,
  activeNotifications,
} from '../utils/notificationsDismiss';
import { Card, Spinner, ErrorMessage } from './UI';

const SEVERITY_COLOR = { crit: 'text-crit', warn: 'text-amber', info: 'text-mist' };

function NoteBody({ note }) {
  return (
    <>
      <p className="text-sm font-medium text-fg">{note.title}</p>
      <p className="mt-0.5 text-xs text-mist">{note.body}</p>
      <p className="mt-0.5 text-[11px] text-mist/70">{note.car_label}</p>
    </>
  );
}

export default function NotificationsPanel() {
  const { t } = useTranslation();
  const [items, setItems] = useState(null); // null = still loading
  const [error, setError] = useState(false);
  const [dismissed, setDismissed] = useState(() => loadDismissed());

  useEffect(() => {
    let cancelled = false;
    getNotifications()
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setDismissed((prev) => pruneDismissed(prev, data.items.map((n) => n.id)));
      })
      .catch(() => {
        // A failed load must NOT read as «all clear» — an overdue policy or ТО
        // hides behind a dropped request, so show an error, never the empty state.
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <ErrorMessage>{t('notificationsPanel.loadError')}</ErrorMessage>;
  if (items === null) return <Spinner className="py-4" />;

  const active = activeNotifications(items, dismissed);
  if (active.length === 0) {
    return <p className="py-2 text-sm text-mist">{t('notificationsPanel.empty')}</p>;
  }

  const dismiss = (id) => {
    const next = new Set(dismissed);
    next.add(id);
    saveDismissed(next);
    setDismissed(next);
  };

  return (
    <div className="space-y-2">
      {active.map((note) => {
        const Icon = note.severity === 'info' ? Bell : AlertTriangle;
        return (
          <Card key={note.id} className="flex items-start gap-3 p-3">
            <Icon
              className={`mt-0.5 h-4 w-4 flex-shrink-0 ${SEVERITY_COLOR[note.severity] || 'text-mist'}`}
            />
            <div className="min-w-0 flex-1">
              {note.action ? (
                <Link to={note.action} className="block active:opacity-70">
                  <NoteBody note={note} />
                </Link>
              ) : (
                <NoteBody note={note} />
              )}
            </div>
            <button
              type="button"
              onClick={() => dismiss(note.id)}
              aria-label={t('notificationsPanel.dismiss')}
              className="-mr-1 -mt-1 flex-shrink-0 rounded-lg p-1.5 text-mist/60 transition-colors hover:bg-raised hover:text-fg"
            >
              <X className="h-4 w-4" />
            </button>
          </Card>
        );
      })}
    </div>
  );
}
