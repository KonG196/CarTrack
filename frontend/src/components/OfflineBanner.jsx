import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CloudOff, RefreshCw } from 'lucide-react';

const RECONNECTED_MS = 3000;

export default function OfflineBanner() {
  const { t } = useTranslation();
  const [online, setOnline] = useState(() =>
    typeof navigator === 'undefined' ? true : navigator.onLine,
  );
  const [reconnected, setReconnected] = useState(false);

  useEffect(() => {
    const goOffline = () => {
      setOnline(false);
      setReconnected(false);
    };
    const goOnline = () => {
      setOnline(true);
      setReconnected(true);
    };
    window.addEventListener('offline', goOffline);
    window.addEventListener('online', goOnline);
    return () => {
      window.removeEventListener('offline', goOffline);
      window.removeEventListener('online', goOnline);
    };
  }, []);

  useEffect(() => {
    if (!reconnected) return undefined;
    const timer = setTimeout(() => setReconnected(false), RECONNECTED_MS);
    return () => clearTimeout(timer);
  }, [reconnected]);

  if (online && !reconnected) return null;

  const Icon = online ? RefreshCw : CloudOff;

  return (
    <div
      role="status"
      aria-live="polite"
      className={`banner-drop flex items-center justify-center gap-1.5 px-4 py-1.5 text-center text-xs font-medium ${
        online ? 'bg-ok text-garage' : 'bg-amber text-amber-ink'
      }`}
    >
      <Icon className={`h-3.5 w-3.5 flex-shrink-0 ${online ? 'animate-spin' : ''}`} />
      {online ? t('offlineBanner.reconnected') : t('offlineBanner.offline')}
    </div>
  );
}
