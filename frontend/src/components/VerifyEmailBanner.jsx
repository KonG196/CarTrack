import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MailWarning, X } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { resendVerification } from '../api/auth';
import { Card } from './UI';
import Toast from './Toast';

// Dashboard nudge for unverified accounts: login is open, but receipt scan and
// plate lookup need a confirmed email. Hidden once verified (or dismissed this
// session). The CTA re-sends the verification link. The dismiss flag is scoped
// per user so dismissing on a shared device doesn't hide the nudge from the
// next unverified account that logs in there.
const dismissKey = (user) => `kapot_verify_banner_dismissed:${user?.id ?? user?.email ?? ''}`;

export default function VerifyEmailBanner() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(dismissKey(user)) === '1';
    } catch {
      return false;
    }
  });
  const [toast, setToast] = useState('');
  const [sending, setSending] = useState(false);

  // email_verified is false only for a genuinely unverified account; undefined
  // (still loading / older payload) must not flash the banner.
  if (user?.email_verified !== false || dismissed) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(dismissKey(user), '1');
    } catch {
      /* ignore */
    }
    setDismissed(true);
  };

  const resend = async () => {
    setSending(true);
    try {
      await resendVerification(user.email);
      setToast(t('dashboard.verifyBannerSent'));
    } catch {
      setToast(t('dashboard.verifyBannerFailed'));
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <Toast message={toast} onDone={() => setToast('')} />
      <Card className="flex items-center gap-3 border-amber/40 p-3">
        <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-amber/15">
          <MailWarning className="h-4 w-4 text-amber" />
        </span>
        <p className="flex-1 text-sm font-medium text-fg">{t('dashboard.verifyBannerTitle')}</p>
        <button
          type="button"
          onClick={resend}
          disabled={sending}
          className="flex-shrink-0 rounded-lg bg-amber px-3 py-1.5 font-mono text-xs font-semibold text-amber-ink transition active:scale-95 disabled:opacity-60 motion-reduce:active:scale-100"
        >
          {t('dashboard.verifyBannerCta')}
        </button>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss"
          className="flex-shrink-0 text-mist transition hover:text-fg"
        >
          <X className="h-4 w-4" />
        </button>
      </Card>
    </>
  );
}
