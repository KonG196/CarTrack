import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Languages, Bell, ChevronRight } from 'lucide-react';

import { Card } from '../components/UI';
import BackLink from '../components/BackLink';
import LanguageToggle from '../components/LanguageToggle';
import CurrencySelect from '../components/CurrencySelect';
import UnitToggle from '../components/UnitToggle';

// Preferences hub: the global display choices (language, currency, units) plus
// a link into Notifications. Moved off the main Settings page to keep it lean.
// Sharing stays in Settings — it's per-car, not a global preference.
export default function Preferences() {
  const { t } = useTranslation();

  return (
    <div className="stagger space-y-4">
      <BackLink to="/garage">{t('preferences.title')}</BackLink>

      <Card>
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
          <Languages className="h-4 w-4 text-amber" />
          {t('preferences.languageTitle')}
        </h2>
        <p className="mt-1 text-xs text-mist">{t('preferences.languageDesc')}</p>
        <LanguageToggle variant="segmented" className="mt-3" />
        <div className="mt-4">
          <span className="text-xs text-mist">{t('preferences.currencyLabel')}</span>
          <CurrencySelect className="mt-1.5" />
        </div>
        <div className="mt-4">
          <span className="text-xs text-mist">{t('units.settingsLabel')}</span>
          <UnitToggle className="mt-1.5" />
        </div>
      </Card>

      <Link to="/notifications" className="block transition active:scale-[0.99] motion-reduce:active:scale-100">
        <Card className="flex items-center gap-3 transition-colors hover:border-edge-soft">
          <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-signal/15">
            <Bell className="h-5 w-5 text-signal" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-fg">{t('preferences.notificationsTitle')}</p>
            <p className="truncate text-xs text-mist">{t('preferences.notificationsSubtitle')}</p>
          </div>
          <ChevronRight className="h-4 w-4 flex-shrink-0 text-mist" />
        </Card>
      </Link>
    </div>
  );
}
