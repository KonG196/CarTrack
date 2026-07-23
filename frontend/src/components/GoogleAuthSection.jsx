import { useTranslation } from 'react-i18next';
import GoogleSignInButton from './GoogleSignInButton';

// «or» divider + the Google button, shared by Login and Register. Renders
// nothing when no Google client id is configured (GoogleSignInButton returns
// null), so the divider never dangles above an empty space.
export default function GoogleAuthSection({ onCredential, onError }) {
  const { t } = useTranslation();

  if (!import.meta.env.VITE_GOOGLE_CLIENT_ID) return null;

  return (
    <div className="mt-4">
      <div className="mb-4 flex items-center gap-3">
        <span className="h-px flex-1 bg-edge" />
        <span className="text-xs uppercase tracking-wider text-mist">{t('auth.orDivider')}</span>
        <span className="h-px flex-1 bg-edge" />
      </div>
      <GoogleSignInButton onCredential={onCredential} onError={onError} />
    </div>
  );
}
