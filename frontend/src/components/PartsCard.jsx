import { useEffect, useState } from 'react';
import { ClipboardCheck, Copy, Share2, Wrench } from 'lucide-react';

import { getSpecs } from '../api/specs';
import { buildSpecsMessage, hasSomethingToShare } from '../utils/partsCard';
import { Button, Card } from './UI';

export default function PartsCard({ car, onToast }) {
  const [specs, setSpecs] = useState([]);
  const [copied, setCopied] = useState('');

  useEffect(() => {
    let alive = true;
    if (!car?.id) return undefined;
    getSpecs(car.id)
      .then((data) => alive && setSpecs(data))
      // The card is worth showing on the VIN alone; a spec sheet that failed to
      // load just means fewer lines in the message.
      .catch(() => alive && setSpecs([]));
    return () => {
      alive = false;
    };
  }, [car?.id]);

  const flash = (what) => {
    setCopied(what);
    setTimeout(() => setCopied(''), 1600);
  };

  const copy = async (text, what) => {
    try {
      await navigator.clipboard.writeText(text);
      flash(what);
    } catch {
      onToast?.('Не вдалося скопіювати');
    }
  };

  const message = buildSpecsMessage(car, specs);

  const share = async () => {
    // Share on a phone hands the text straight to Viber or Telegram, which is
    // where it is going anyway. On a desktop there is no share sheet, so the
    // clipboard is the honest equivalent.
    if (navigator.share) {
      try {
        await navigator.share({ text: message });
        return;
      } catch {
        // A dismissed share sheet is not a failure worth reporting.
        return;
      }
    }
    copy(message, 'specs');
  };

  if (!hasSomethingToShare(car)) return null;

  return (
    <Card>
      <div className="mb-3 flex items-center gap-2">
        <Wrench className="h-5 w-5 text-amber" />
        <h2 className="font-display text-base font-semibold text-fg">Для замовлення запчастин</h2>
      </div>
      <p className="mb-3 text-sm text-mist">
        Те, що питає магазин, — без пошуку по техпаспорту.
      </p>

      {car.vin && (
        <button
          type="button"
          onClick={() => copy(car.vin, 'vin')}
          className="mb-2 flex w-full items-center justify-between rounded-xl border border-edge px-3 py-2.5 text-left transition-colors hover:border-amber/50"
        >
          <span>
            <span className="block text-[11px] text-mist">VIN</span>
            <span className="font-mono text-sm text-fg">{car.vin}</span>
          </span>
          {copied === 'vin' ? (
            <ClipboardCheck className="h-4 w-4 flex-shrink-0 text-ok" />
          ) : (
            <Copy className="h-4 w-4 flex-shrink-0 text-mist" />
          )}
        </button>
      )}

      {car.plate && (
        <button
          type="button"
          onClick={() => copy(car.plate, 'plate')}
          className="mb-3 flex w-full items-center justify-between rounded-xl border border-edge px-3 py-2.5 text-left transition-colors hover:border-amber/50"
        >
          <span>
            <span className="block text-[11px] text-mist">Держномер</span>
            <span className="font-mono text-sm text-fg">{car.plate}</span>
          </span>
          {copied === 'plate' ? (
            <ClipboardCheck className="h-4 w-4 flex-shrink-0 text-ok" />
          ) : (
            <Copy className="h-4 w-4 flex-shrink-0 text-mist" />
          )}
        </button>
      )}

      <pre className="mb-3 whitespace-pre-wrap rounded-xl bg-garage/60 px-3 py-2.5 font-mono text-[11px] leading-relaxed text-mist">
        {message}
      </pre>

      <Button type="button" variant="secondary" onClick={share} className="w-full">
        <Share2 className="mr-2 inline h-4 w-4" />
        {copied === 'specs' ? 'Скопійовано' : 'Поділитися спеками'}
      </Button>
    </Card>
  );
}
