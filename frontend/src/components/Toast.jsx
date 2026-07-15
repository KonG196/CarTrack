import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { CheckCircle2, AlertTriangle, Info } from 'lucide-react';
import useAnimatedPresence from '../hooks/useAnimatedPresence';

const CLOSE_MS = 180;

const VARIANTS = {
  ok: { icon: CheckCircle2, className: 'border-ok/40 bg-ok/10 text-ok' },
  warn: { icon: AlertTriangle, className: 'border-amber/40 bg-amber/10 text-amber' },
  info: { icon: Info, className: 'border-signal/40 bg-signal/10 text-signal' },
};

export default function Toast({ message, onDone, duration = 3000, variant = 'ok' }) {
  const { mounted, closing, requestClose } = useAnimatedPresence(
    Boolean(message),
    onDone,
    CLOSE_MS,
  );

  useEffect(() => {
    if (!message) return undefined;
    const timer = setTimeout(requestClose, duration);
    return () => clearTimeout(timer);
  }, [message, duration, requestClose]);

  if (!mounted) return null;

  const { icon: Icon, className } = VARIANTS[variant] || VARIANTS.ok;

  return createPortal(
    <div className="pointer-events-none fixed inset-x-0 top-4 z-[60] flex justify-center px-4">
      <div
        className={`toast-pop flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm shadow-lg shadow-black/40 backdrop-blur ${className}`}
        data-closing={closing ? 'true' : undefined}
        role="status"
        aria-live="polite"
      >
        <Icon className="h-4 w-4 flex-shrink-0" />
        {message}
      </div>
    </div>,
    document.body,
  );
}
