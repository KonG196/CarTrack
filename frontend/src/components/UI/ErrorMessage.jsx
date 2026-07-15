import { AlertTriangle } from 'lucide-react';

export default function ErrorMessage({ children, className = '' }) {
  if (!children) return null;
  return (
    <div
      className={`flex items-start gap-2 rounded-xl border border-crit/40 bg-crit/10 px-3.5 py-2.5 text-sm text-crit ${className}`}
      role="alert"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
      <span>{children}</span>
    </div>
  );
}
