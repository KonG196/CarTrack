import { useCallback, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../store/authStore';
import { extractError } from '../api/client';
import { safeNext, withNext } from '../utils/nextPath';
import { Button, TextField, Card, ErrorMessage } from '../components/UI';
import Wordmark from '../components/Wordmark';
import LanguageToggle from '../components/LanguageToggle';
import GoogleAuthSection from '../components/GoogleAuthSection';

export default function Register() {
  const { t } = useTranslation();
  const register = useAuthStore((s) => s.register);
  const loginWithGoogle = useAuthStore((s) => s.loginWithGoogle);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = safeNext(searchParams.get('next'));
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Google «sign up» and «sign in» are the same call — the backend creates the
  // account if it's new, or logs into the existing one (merging by email).
  const handleGoogle = useCallback(
    async (idToken) => {
      setError('');
      try {
        await loginWithGoogle(idToken);
        navigate(next, { replace: true });
      } catch (err) {
        setError(extractError(err, t('auth.google.failed')));
      }
    },
    [loginWithGoogle, navigate, next, t],
  );

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (password !== confirm) {
      setError(t('auth.register.passwordMismatch'));
      return;
    }
    if (password.length < 6) {
      setError(t('auth.register.passwordTooShort'));
      return;
    }
    setLoading(true);
    try {
      // Register signs the user straight in now (verification no longer gates
      // login), so go to the app. Confirming the email later unlocks scan and
      // plate lookup — the dashboard nudges them to do it.
      await register(email.trim(), password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(extractError(err, t('auth.register.failed')));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-garage px-4">
      <div className="fixed right-4 top-4 z-10">
        <LanguageToggle />
      </div>
      <div className="rise-in w-full max-w-md">
        <div className="mb-10 flex flex-col items-center gap-2">
          <Wordmark size="lg" />
          <p className="font-mono text-xs uppercase tracking-[0.14em] text-mist">
            {t('auth.tagline')}
          </p>
        </div>
        <Card>
          <h1 className="mb-4 text-center font-display text-lg font-semibold text-fg">{t('auth.register.title')}</h1>

          {/* Google + «or», above the form. Self-hides without a client id. */}
          <GoogleAuthSection onCredential={handleGoogle} />

          <form onSubmit={handleSubmit} className="flex flex-col gap-3.5">
            <TextField
              label={t('auth.register.email')}
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <TextField
              label={t('auth.register.password')}
              type="password"
              autoComplete="new-password"
              required
              hint={t('auth.register.passwordHint')}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <TextField
              label={t('auth.register.confirm')}
              type="password"
              autoComplete="new-password"
              enterKeyHint="done"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
            <ErrorMessage>{error}</ErrorMessage>
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? t('auth.register.submitting') : t('auth.register.submit')}
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-mist">
            {t('auth.register.haveAccount')}{' '}
            <Link to={withNext('/login', next)} className="font-semibold text-amber hover:text-amber-deep">
              {t('auth.register.login')}
            </Link>
          </p>
        </Card>
      </div>
    </div>
  );
}
