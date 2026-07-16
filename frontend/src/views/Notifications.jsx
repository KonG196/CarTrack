import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell, CalendarClock, Send } from 'lucide-react';

import { extractError } from '../api/client';
import * as telegramApi from '../api/telegram';
import BackLink from '../components/BackLink';
import Toast from '../components/Toast';
import { Card, ErrorMessage, Toggle } from '../components/UI';
import { useAuthStore } from '../store/authStore';

// The per-type smart pushes, each with its own on/off. reminders_enabled keeps
// its original meaning (ТО); the rest gate one push kind each.
const ALERTS = [
  {
    key: 'reminders_enabled',
    title: 'Нагадування про ТО',
    desc: 'Коли інтервал наближається або вже прострочений',
  },
  {
    key: 'notify_fuel',
    title: 'Стрибок розходу пального',
    desc: 'Якщо розхід зріс понад 15% від вашої норми',
  },
  {
    key: 'notify_seasonal',
    title: 'Сезонні: шини та омивайка',
    desc: 'Зимова гума й незамерзайка — за регіоном держномера',
  },
  {
    key: 'notify_rotation',
    title: 'Ротація шин',
    desc: 'Переставити вісі кожні 10 000 км',
  },
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
      setToast(next ? `${label}: увімкнено` : `${label}: вимкнено`);
    } catch (err) {
      setError(extractError(err, 'Не вдалося зберегти'));
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />
      <BackLink to="/garage">Сповіщення</BackLink>

      {telegramLinked === false && (
        <Link to="/profile" className="block">
          <Card className="flex items-center gap-3 border-amber/40 transition active:scale-[0.99] motion-reduce:active:scale-100">
            <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-amber/15">
              <Send className="h-5 w-5 text-amber" />
            </span>
            <p className="flex-1 text-sm text-fg">
              Сповіщення приходять у Telegram. Прив'яжіть бота у Профілі, щоб їх
              отримувати.
            </p>
          </Card>
        </Link>
      )}

      {error && <ErrorMessage>{error}</ErrorMessage>}

      <div data-tour="notif-reminders">
        <h2 className="mb-2 flex items-center gap-2 px-1 font-display text-sm font-semibold text-fg">
          <Bell className="h-4 w-4 text-mist" />
          Розумні нагадування
        </h2>
        <div className="space-y-2">
          {ALERTS.map((a) => (
            <Toggle
              key={a.key}
              label={<ToggleLabel title={a.title} desc={a.desc} />}
              checked={user?.[a.key] ?? true}
              onChange={(v) => saving || toggle(a.key, v, a.title)}
            />
          ))}
        </div>
      </div>

      <div>
        <h2 className="mb-2 flex items-center gap-2 px-1 font-display text-sm font-semibold text-fg">
          <CalendarClock className="h-4 w-4 text-mist" />
          Щотижневий підсумок
        </h2>
        <Toggle
          label={
            <ToggleLabel
              title="Надсилати підсумок"
              desc="Щонеділі — витрати, пробіг і що наближається. Порожній тиждень не турбуємо."
            />
          }
          checked={user?.digest_enabled ?? true}
          onChange={(v) => saving || toggle('digest_enabled', v, 'Підсумок')}
        />
      </div>
    </div>
  );
}
