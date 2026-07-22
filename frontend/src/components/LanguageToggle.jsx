import { useTranslation } from 'react-i18next';
import { LANGS } from '../i18n';

// Language switcher. Two shapes:
//   • "pill"      — compact EN|UK, sits in the corner of the auth screens.
//   • "segmented" — full-width row with native language names, used in Settings.
// Changing the language is instant (i18next re-renders); the choice is persisted
// to localStorage by the i18n module, and mirrored to the backend once logged in
// via the `languageChanged` listener in the auth store.
export default function LanguageToggle({ variant = 'pill', className = '' }) {
  const { t, i18n } = useTranslation();
  const current = String(i18n.language || 'en').slice(0, 2);

  const change = (lng) => {
    if (lng !== current) i18n.changeLanguage(lng);
  };

  if (variant === 'segmented') {
    return (
      <div
        role="group"
        aria-label={t('lang.label')}
        className={`flex gap-2 ${className}`}
      >
        {LANGS.map((lng) => {
          const active = lng === current;
          return (
            <button
              key={lng}
              type="button"
              onClick={() => change(lng)}
              aria-pressed={active}
              className={`flex-1 rounded-xl border px-3 py-2 text-sm transition-colors ${
                active
                  ? 'border-amber bg-amber/10 text-amber'
                  : 'border-edge text-mist hover:text-fg'
              }`}
            >
              {t(`lang.${lng}`)}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div
      role="group"
      aria-label={t('lang.label')}
      className={`inline-flex overflow-hidden rounded-lg border border-edge text-xs font-medium ${className}`}
    >
      {LANGS.map((lng) => {
        const active = lng === current;
        return (
          <button
            key={lng}
            type="button"
            onClick={() => change(lng)}
            aria-pressed={active}
            className={`px-2.5 py-1 uppercase tracking-wide transition-colors ${
              active ? 'bg-amber text-amber-ink' : 'text-mist hover:text-fg'
            }`}
          >
            {t(`lang.short.${lng}`)}
          </button>
        );
      })}
    </div>
  );
}
