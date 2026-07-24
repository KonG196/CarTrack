import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { AlertTriangle, Bell, ArrowRight } from 'lucide-react';
import Modal from './UI/Modal';
import { Card } from './UI';
import { useNotificationStore } from '../store/notificationStore';

const SEVERITY_COLOR = { crit: 'text-crit', warn: 'text-amber', info: 'text-mist' };

// The recent-notifications popover behind the header bell. Reads the store the
// bell already filled (no second fetch), lists the live nudges, and links to the
// full history page. Opening it is what marks everything read (see the bell).
export default function NotificationModal({ open, onClose }) {
  const { t } = useTranslation();
  const items = useNotificationStore((s) => s.items);

  return (
    <Modal open={open} onClose={onClose} title={t('notificationCentre.title')} size="sm">
      <div className="space-y-2">
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
                onClick={onClose}
                className="block active:opacity-70"
              >
                {row}
              </Link>
            ) : (
              <div key={note.id}>{row}</div>
            );
          })
        )}

        <Link
          to="/notifications"
          onClick={onClose}
          className="mt-1 flex items-center justify-center gap-1.5 rounded-xl border border-edge py-2.5 text-sm font-medium text-mist transition-colors hover:border-edge-soft hover:text-fg"
        >
          {t('notificationCentre.seeAll')}
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </Modal>
  );
}
