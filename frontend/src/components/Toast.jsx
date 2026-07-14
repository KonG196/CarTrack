import { useEffect, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';

export default function Toast({ message, onDone, duration = 3000 }) {
  const [visible, setVisible] = useState(Boolean(message));

  useEffect(() => {
    if (!message) return undefined;
    setVisible(true);
    const timer = setTimeout(() => {
      setVisible(false);
      if (onDone) onDone();
    }, duration);
    return () => clearTimeout(timer);
  }, [message, duration, onDone]);

  if (!message || !visible) return null;

  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-50 flex justify-center px-4">
      <div className="flex items-center gap-2 rounded-xl border border-emerald-800 bg-emerald-950/95 px-4 py-2.5 text-sm text-emerald-200 shadow-lg shadow-black/40">
        <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
        {message}
      </div>
    </div>
  );
}
