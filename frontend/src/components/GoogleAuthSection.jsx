import { useTranslation } from 'react-i18next';
import GoogleSignInButton from './GoogleSignInButton';

// The Google button, then an «or» divider — placed ABOVE the email/password
// form. Renders nothing when no Google client id is configured, so the divider
// never dangles over an empty space.
export default function GoogleAuthSection({ onCredential, onError }) {
  const { t } = useTranslation();

  if (!import.meta.env.VITE_GOOGLE_CLIENT_ID) return null;

  return (
    <div className="mb-4">
      <GoogleSignInButton onCredential={onCredential} onError={onError} />
      <div className="mt-4 flex items-center gap-3">
        <span className="h-px flex-1 bg-edge" />
        <span className="text-xs uppercase tracking-wider text-mist">{t('auth.orDivider')}</span>
        <span className="h-px flex-1 bg-edge" />
      </div>
    </div>
  );
}
