import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { AlertTriangle, Bell, Check } from 'lucide-react';
import { getNotificationHistory } from '../api/notifications';
import { Card, Spinner, ErrorMessage } from './UI';

const SEVERITY_COLOR = { crit: 'text-crit', warn: 'text-amber', info: 'text-mist' };

function fmtDate(iso) {
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return '';
  }
}

// The full stored notification history: active nudges first, then resolved ones
// (muted, with the date they cleared). Unlike the live panel, past items persist
// here even after their condition is gone.
export default function NotificationHistoryList() {
  const { t } = useTranslation();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getNotificationHistory()
      .then((data) => !cancelled && setRows(data.items || []))
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <ErrorMessage>{t('notificationCentre.loadError')}</ErrorMessage>;
  if (rows === null) return <Spinner className="py-6" />;
  if (rows.length === 0) {
    return <p className="py-6 text-center text-sm text-mist">{t('notificationCentre.historyEmpty')}</p>;
  }

  const active = rows.filter((r) => !r.resolved_at);
  const past = rows.filter((r) => r.resolved_at);

  const renderRow = (note) => {
    const resolved = Boolean(note.resolved_at);
    const Icon = resolved ? Check : note.severity === 'info' ? Bell : AlertTriangle;
    const iconColor = resolved ? 'text-ok' : SEVERITY_COLOR[note.severity] || 'text-mist';
    const body = (
      <Card className={`flex items-start gap-3 p-3 ${resolved ? 'opacity-60' : ''}`}>
        <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${iconColor}`} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-fg">{note.title}</p>
          <p className="mt-0.5 text-xs text-mist">{note.body}</p>
          <p className="mt-0.5 text-[11px] text-mist/70">
            {note.car_label}
            {resolved
              ? ` · ${t('notificationCentre.resolvedOn', { date: fmtDate(note.resolved_at) })}`
              : ''}
          </p>
        </div>
      </Card>
    );
    // Only active items link — a resolved nudge's action is stale.
    return note.action && !resolved ? (
      <Link key={note.id} to={note.action} className="block active:opacity-70">
        {body}
      </Link>
    ) : (
      <div key={note.id}>{body}</div>
    );
  };

  return (
    <div className="space-y-4">
      {active.length > 0 && (
        <div className="space-y-2">
          <h2 className="px-1 font-display text-sm font-semibold text-fg">
            {t('notificationCentre.activeHeader')}
          </h2>
          {active.map(renderRow)}
        </div>
      )}
      {past.length > 0 && (
        <div className="space-y-2">
          <h2 className="px-1 font-display text-sm font-semibold text-mist">
            {t('notificationCentre.pastHeader')}
          </h2>
          {past.map(renderRow)}
        </div>
      )}
    </div>
  );
}
