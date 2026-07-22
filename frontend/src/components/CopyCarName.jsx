import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Copy } from 'lucide-react';

import useCarSpecsCopy from '../hooks/useCarSpecsCopy';

// A car's name as a copy button: the shop details go to the clipboard, and the
// icon rides inline right after the text — grey, on the last line — rather than
// drifting to the far edge. Rendered `inline` so it flows and wraps inside the
// heading element the caller wraps it in.
//
// `active:opacity-60` is the press feedback: a tap that copies but shows nothing
// leaves the user unsure it registered.
export default function CopyCarName({ car, onCopied, children, className = '' }) {
  const { t } = useTranslation();
  const { copy, copied, canCopy, previewCopied } = useCarSpecsCopy(car, onCopied);
  const btnRef = useRef(null);

  // The product tour flashes the checkmark by dispatching this event on the
  // button — a demonstration of the result, without copying or a toast.
  useEffect(() => {
    const el = btnRef.current;
    if (!el) return undefined;
    const onDemo = () => previewCopied();
    el.addEventListener('kapot:tour-demo', onDemo);
    return () => el.removeEventListener('kapot:tour-demo', onDemo);
  }, [previewCopied]);

  if (!canCopy) return <>{children}</>;

  return (
    <button
      ref={btnRef}
      type="button"
      onClick={copy}
      data-tour-demo="copy"
      title={t('copyCarName.copyTitle')}
      className={`inline text-left transition-opacity active:opacity-60 ${className}`}
    >
      {children}
      {copied ? (
        <Check className="ml-1.5 inline-block h-4 w-4 align-[-0.15em] text-ok" />
      ) : (
        <Copy className="ml-1.5 inline-block h-4 w-4 align-[-0.15em] text-mist" />
      )}
    </button>
  );
}
