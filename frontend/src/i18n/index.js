import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from './locales/en.json';
import uk from './locales/uk.json';

export const LANGS = ['en', 'uk'];
export const LANG_KEY = 'kapot_lang';

// English is the default for new users; a stored choice always wins. The value
// is also mirrored to the backend (User.language) once logged in, so emails and
// the Telegram bot speak the same language as the UI.
function initialLang() {
  try {
    const stored = localStorage.getItem(LANG_KEY);
    if (LANGS.includes(stored)) return stored;
  } catch {
    /* localStorage unavailable (private mode) — fall through to default */
  }
  return 'en';
}

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    uk: { translation: uk },
  },
  lng: initialLang(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false }, // React already escapes
  returnEmptyString: false,
});

// Keep <html lang> and the stored choice in sync with the live language.
if (typeof document !== 'undefined') {
  document.documentElement.lang = i18n.language;
  i18n.on('languageChanged', (lng) => {
    document.documentElement.lang = lng;
    try {
      localStorage.setItem(LANG_KEY, lng);
    } catch {
      /* ignore */
    }
  });
}

export default i18n;
