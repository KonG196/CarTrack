import { useCallback, useEffect, useState } from 'react';

import { getSpecs } from '../api/specs';
import i18n from '../i18n';
import { buildSpecsMessage, hasSomethingToShare } from '../utils/partsCard';

// The copy-the-shop-details behaviour, without a layout. Both the settings card
// and the dashboard heading tap the car's name to copy, but they place the icon
// differently — so the logic lives here and each renders its own trigger.
export default function useCarSpecsCopy(car, onCopied) {
  const [specs, setSpecs] = useState([]);
  const [copied, setCopied] = useState(false);

  // The spec sheet is a separate resource, and only its shop-relevant rows end
  // up in the message. Failing to load it is not worth surfacing: the message
  // is still useful without an oil approval in it.
  useEffect(() => {
    if (!car?.id) return undefined;
    let cancelled = false;
    getSpecs(car.id)
      .then((data) => !cancelled && setSpecs(data))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [car?.id]);

  useEffect(() => {
    if (!copied) return undefined;
    const timer = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timer);
  }, [copied]);

  const copy = async () => {
    const message = buildSpecsMessage(car, specs);
    if (!message) return;
    try {
      await navigator.clipboard.writeText(message);
      setCopied(true);
      onCopied?.(i18n.t('carSpecsCopy.copiedToShop'));
    } catch {
      onCopied?.(i18n.t('carSpecsCopy.copyFailed'));
    }
  };

  // The product tour flashes the checkmark without touching the clipboard: the
  // real clipboard write needs a user gesture, and a demo should not fire a
  // toast or copy anything. The 1600ms auto-reset above clears it.
  const previewCopied = useCallback(() => setCopied(true), []);

  return { copy, copied, canCopy: hasSomethingToShare(car), previewCopied };
}
