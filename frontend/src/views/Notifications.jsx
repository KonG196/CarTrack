import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Bell, CalendarClock, Send } from 'lucide-react';

import { extractError } from '../api/client';
import * as telegramApi from '../api/telegram';
import BackLink from '../components/BackLink';
import NotificationHistoryList from '../components/NotificationHistoryList';
import Toast from '../components/Toast';
import { Card, ErrorMessage, Toggle } from '../components/UI';
import { useAuthStore } from '../store/authStore';

// The per-type smart pushes, each with its own on/off. reminders_enabled keeps
// its original meaning (ТО); the rest gate one push kind each.
const ALERTS = [
  { key: 'reminders_enabled', i18n: 'reminders' },
  { key: 'notify_fuel', i18n: 'fuel' },
  { key: 'notify_seasonal', i18n: 'seasonal' },
  { key: 'notify_rotation', i18n: 'rotation' },
];

function ToggleLabel({ title, desc }) {
  return (
    <span className="block">
      <span className="block text-sm font-medium text-fg">{title}</span>
      <span className="mt-0.5 block text-xs font-normal text-mist">{desc}</span>
    </span>
  );
}

export default function Notifications() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const updateSettings = useAuthStore((s) => s.updateSettings);

  const [telegramLinked, setTelegramLinked] = useState(null);
  const [saving, setSaving] = useState(null); // which toggle is in flight
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');

  // Reminders travel over Telegram, so the page has to say whether it is
  // connected — a toggle for messages that can never arrive is a lie.
  useEffect(() => {
    let cancelled = false;
    telegramApi
      .getStatus()
      .then((data) => !cancelled && setTelegramLinked(Boolean(data.linked)))
      .catch(() => !cancelled && setTelegramLinked(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const toggle = async (key, next, label) => {
    setError('');
    setSaving(key);
    try {
      await updateSettings({ [key]: next });
      setToast(
        next
          ? t('notifications.toastEnabled', { label })
          : t('notifications.toastDisabled', { label }),
      );
    } catch (err) {
      setError(extractError(err, t('notifications.saveFailed')));
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />
      <BackLink to="/garage">{t('notifications.title')}</BackLink>

      <NotificationHistoryList />

      {telegramLinked === false && (
        <Link to="/profile" className="block">
          <Card className="flex items-center gap-3 border-amber/40 transition active:scale-[0.99] motion-reduce:active:scale-100">
            <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-amber/15">
              <Send className="h-5 w-5 text-amber" />
            </span>
            <p className="flex-1 text-sm text-fg">
              {t('notifications.telegramHint')}
            </p>
          </Card>
        </Link>
      )}

      {error && <ErrorMessage>{error}</ErrorMessage>}

      <div data-tour="notif-reminders">
        <h2 className="mb-2 flex items-center gap-2 px-1 font-display text-sm font-semibold text-fg">
          <Bell className="h-4 w-4 text-mist" />
          {t('notifications.smartReminders')}
        </h2>
        <div className="space-y-2">
          {ALERTS.map((a) => {
            const title = t(`notifications.alerts.${a.i18n}.title`);
            return (
              <Toggle
                key={a.key}
                label={
                  <ToggleLabel
                    title={title}
                    desc={t(`notifications.alerts.${a.i18n}.desc`)}
                  />
                }
                checked={user?.[a.key] ?? true}
                onChange={(v) => saving || toggle(a.key, v, title)}
              />
            );
          })}
        </div>
      </div>

      <div>
        <h2 className="mb-2 flex items-center gap-2 px-1 font-display text-sm font-semibold text-fg">
          <CalendarClock className="h-4 w-4 text-mist" />
          {t('notifications.weeklyDigest')}
        </h2>
        <Toggle
          label={
            <ToggleLabel
              title={t('notifications.digest.title')}
              desc={t('notifications.digest.desc')}
            />
          }
          checked={user?.digest_enabled ?? true}
          onChange={(v) =>
            saving || toggle('digest_enabled', v, t('notifications.digest.label'))
          }
        />
      </div>
    </div>
  );
}
