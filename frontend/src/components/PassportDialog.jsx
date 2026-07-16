import { useEffect, useState } from 'react';
import { Check, Copy, ExternalLink, RefreshCw } from 'lucide-react';

import { extractError } from '../api/client';
import { mintPassportToken, revokePassportToken } from '../api/passport';
import { Modal, Button, ErrorMessage, Spinner } from './UI';

// The owner's QR-passport dialog: mints (idempotently) the public link on open,
// shows a scannable QR of it, and offers to copy / open / regenerate / revoke.
export default function PassportDialog({ car, open, onClose, onToast }) {
  const [data, setData] = useState(null); // { token, url, qr_svg }
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !car) return undefined;
    let cancelled = false;
    setError('');
    setData(null);
    setLoading(true);
    mintPassportToken(car.id)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(extractError(e, 'Не вдалося створити паспорт')))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [open, car]);

  const copy = async () => {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard blocked — the link is visible to copy by hand */
    }
  };

  const regenerate = async () => {
    setBusy(true);
    setError('');
    try {
      setData(await mintPassportToken(car.id, { regenerate: true }));
      onToast?.('Посилання оновлено — старий QR більше не працює');
    } catch (e) {
      setError(extractError(e, 'Не вдалося оновити посилання'));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    setBusy(true);
    setError('');
    try {
      await revokePassportToken(car.id);
      onToast?.('QR-паспорт відкликано');
      onClose();
    } catch (e) {
      setError(extractError(e, 'Не вдалося відкликати'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="QR-паспорт авто" size="sm">
      {loading || !data ? (
        <Spinner className="py-10" />
      ) : (
        <div className="space-y-4">
          {error && <ErrorMessage>{error}</ErrorMessage>}
          <div
            className="mx-auto h-44 w-44 rounded-xl bg-white p-3"
            aria-label="QR-код паспорта"
            dangerouslySetInnerHTML={{ __html: data.qr_svg }}
          />
          <p className="text-center text-xs leading-snug text-mist">
            Наведіть камеру — відкриється сторінка з телефоном, ОСЦПВ, тиском і допуском
            пального. Роздрукуйте й покладіть у бардачок.
          </p>
          <div className="flex items-center gap-2 rounded-xl border border-edge bg-panel px-3 py-2">
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-mist">{data.url}</span>
            <button
              type="button"
              onClick={copy}
              aria-label="Скопіювати посилання"
              className="flex-shrink-0 rounded-lg p-1.5 text-mist transition-colors hover:text-fg active:opacity-60"
            >
              {copied ? <Check className="h-4 w-4 text-ok" /> : <Copy className="h-4 w-4" />}
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <a
              href={data.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 rounded-xl border border-edge bg-panel py-2.5 text-sm font-medium text-fg transition active:scale-[0.98] hover:bg-raised"
            >
              <ExternalLink className="h-4 w-4" />
              Відкрити
            </a>
            <Button variant="secondary" onClick={regenerate} disabled={busy}>
              <RefreshCw className="h-4 w-4" />
              Оновити
            </Button>
          </div>
          <Button variant="ghost" onClick={revoke} disabled={busy} className="w-full text-crit">
            Відкликати посилання
          </Button>
        </div>
      )}
    </Modal>
  );
}
