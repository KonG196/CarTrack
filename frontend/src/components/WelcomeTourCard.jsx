import { useTranslation } from 'react-i18next';
import { Compass, X } from 'lucide-react';
import { useTour } from '../tour/TourContext';

// A one-time, dismissible welcome block on the dashboard offering the overview
// tour. Replaces the old per-page auto-launch that users found intrusive: the
// tour now runs ONLY when asked. Showing/dismissing both mark the tour seen, so
// the card appears once per account and never nags.
export default function WelcomeTourCard() {
  const { t } = useTranslation();
  const { start, wasSeen, markSeen } = useTour();

  if (wasSeen('overview')) return null;

  return (
    <div className="tour-callout relative overflow-hidden rounded-2xl border border-amber/40 bg-gradient-to-br from-panel to-raised p-4">
      <button
        type="button"
        onClick={() => markSeen('overview')}
        aria-label={t('welcomeTour.dismiss')}
        className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-lg text-mist transition-colors hover:bg-raised hover:text-fg"
      >
        <X className="h-4 w-4" />
      </button>
      <div className="flex items-start gap-3 pr-6">
        <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-amber/15">
          <Compass className="h-5 w-5 text-amber" />
        </span>
        <div className="min-w-0">
          <h2 className="font-display text-base font-semibold text-fg">
            {t('welcomeTour.title')}
          </h2>
          <p className="mt-0.5 text-sm leading-snug text-mist">{t('welcomeTour.body')}</p>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          onClick={() => start('overview')}
          className="flex-1 rounded-xl bg-amber px-4 py-2.5 text-sm font-semibold text-amber-ink transition active:scale-[0.98] motion-reduce:active:scale-100"
        >
          {t('welcomeTour.start')}
        </button>
        <button
          type="button"
          onClick={() => markSeen('overview')}
          className="rounded-xl px-4 py-2.5 text-sm font-medium text-mist transition-colors hover:text-fg"
        >
          {t('welcomeTour.skip')}
        </button>
      </div>
    </div>
  );
}
