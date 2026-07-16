import { Link } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';

// Back navigation for a sub-page: top-left, an arrow followed by the page
// title, and the whole row is the target — not just the arrow. A label sitting
// next to a hit area that excludes it is a label people tap and nothing happens.
export default function BackLink({ to, children }) {
  return (
    <Link
      to={to}
      className="-ml-1.5 mb-1 inline-flex items-center gap-1 rounded-lg py-1 pl-1 pr-2 transition hover:bg-raised active:scale-[0.98] motion-reduce:active:scale-100"
    >
      <ChevronLeft className="h-6 w-6 flex-shrink-0 text-mist" />
      <span className="font-display text-xl font-semibold text-fg">{children}</span>
    </Link>
  );
}
