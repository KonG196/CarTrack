import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell, ChevronRight } from 'lucide-react';
import { getNotifications } from '../api/notifications';
import { loadDismissed, activeNotifications } from '../utils/notificationsDismiss';
import { Card } from './UI';

// Dashboard entry point to the notification centre: a compact «N need attention»
// banner, hidden when there is nothing (or every nudge was dismissed locally).
export default function NotificationsBanner() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getNotifications()
      .then((data) => {
        if (!cancelled) setCount(activeNotifications(data.items, loadDismissed()).length);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  if (count === 0) return null;

  return (
    <Link to="/notifications" className="block">
      <Card className="flex items-center gap-3 border-amber/40 p-3 transition active:scale-[0.99] motion-reduce:active:scale-100">
        <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-amber/15">
          <Bell className="h-4 w-4 text-amber" />
        </span>
        <p className="flex-1 text-sm font-medium text-fg">Сповіщення потребують уваги</p>
        <span className="flex-shrink-0 rounded-full bg-amber px-2 py-0.5 font-mono text-xs font-semibold tabular-nums text-amber-ink">
          {count}
        </span>
        <ChevronRight className="h-4 w-4 flex-shrink-0 text-mist" />
      </Card>
    </Link>
  );
}
