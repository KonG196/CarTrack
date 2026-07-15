import { Loader2 } from 'lucide-react';

export default function Spinner({ className = '' }) {
  return (
    <div className={`flex justify-center py-10 ${className}`}>
      <Loader2 className="h-7 w-7 animate-spin text-amber" aria-label="Завантаження…" />
    </div>
  );
}
