import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../store/authStore';
import { extractError } from '../api/client';
import { safeNext, withNext } from '../utils/nextPath';
import { Button, TextField, Card, ErrorMessage } from '../components/UI';
import Wordmark from '../components/Wordmark';
import LanguageToggle from '../components/LanguageToggle';

export default function Register() {
  const { t } = useTranslation();
  const register = useAuthStore((s) => s.register);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = safeNext(searchParams.get('next'));
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

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
      const { pendingVerification } = await register(email.trim(), password);
      if (pendingVerification) {
        navigate(`/verify?email=${encodeURIComponent(email.trim())}`, { replace: true });
        return;
      }
      navigate(next, { replace: true });
    } catch (err) {
      setError(extractError(err, t('auth.register.failed')));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-garage px-4">
      <div className="rise-in w-full max-w-md">
        <div className="mb-4 flex justify-end">
          <LanguageToggle />
        </div>
        <div className="mb-6 flex flex-col items-center gap-2">
          <Wordmark size="lg" />
          <p className="font-mono text-xs uppercase tracking-[0.14em] text-mist">
            {t('auth.tagline')}
          </p>
        </div>
        <Card>
          <h1 className="mb-4 font-display text-lg font-semibold text-fg">{t('auth.register.title')}</h1>
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
