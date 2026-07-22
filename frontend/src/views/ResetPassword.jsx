import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { requestPasswordReset, confirmPasswordReset } from '../api/auth';
import { extractError } from '../api/client';
import { Button, TextField, Card, ErrorMessage } from '../components/UI';
import Toast from '../components/Toast';
import Wordmark from '../components/Wordmark';
import LanguageToggle from '../components/LanguageToggle';

export default function ResetPassword() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState('');
  const [channel, setChannel] = useState('email');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [info, setInfo] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState('');

  // Magic link from the letter (/reset?email=&code=): prefill and jump to the
  // new-password step, so the person only has to type the new password. Reset
  // can't finish itself — a new password is still required.
  useEffect(() => {
    const mail = searchParams.get('email');
    const value = searchParams.get('code');
    if (mail && value) {
      setEmail(mail);
      setCode(value);
      setStep(2);
      setInfo(t('auth.reset.onlyNewPassword'));
    }
  }, [searchParams, t]);

  const handleRequest = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await requestPasswordReset(email.trim(), channel);
      setInfo(data?.detail || t('auth.reset.codeSentGeneric'));
      setStep(2);
    } catch (err) {
      setError(extractError(err, t('auth.reset.sendFailed')));
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async (e) => {
    e.preventDefault();
    setError('');
    if (password !== confirm) {
      setError(t('auth.reset.passwordMismatch'));
      return;
    }
    if (password.length < 8) {
      setError(t('auth.reset.passwordTooShort'));
      return;
    }
    setLoading(true);
    try {
      await confirmPasswordReset(email.trim(), code.trim(), password);
      setToast(t('auth.reset.success'));
    } catch (err) {
      setError(extractError(err, t('auth.reset.invalidCode')));
      setLoading(false);
    }
  };

  const backToRequest = () => {
    setStep(1);
    setInfo('');
    setError('');
    setCode('');
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-garage px-4">
      <Toast message={toast} onDone={() => navigate('/login', { replace: true })} />
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
          <h1 className="mb-4 font-display text-lg font-semibold text-fg">{t('auth.reset.title')}</h1>
          {step === 1 ? (
            <form onSubmit={handleRequest} className="flex flex-col gap-3.5">
              <p className="text-sm text-mist">{t('auth.reset.intro')}</p>
              <div className="flex flex-col gap-1.5">
                <span className="text-xs text-mist">{t('auth.reset.channelLabel')}</span>
                <div className="flex gap-2">
                  {[
                    { value: 'email', label: t('auth.reset.channelEmail') },
                    { value: 'telegram', label: t('auth.reset.channelTelegram') },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setChannel(option.value)}
                      className={`flex-1 rounded-xl border px-3 py-2 text-sm transition-colors ${
                        channel === option.value
                          ? 'border-amber bg-amber/10 text-amber'
                          : 'border-edge text-mist hover:text-fg'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                <span className="text-xs text-mist">{t('auth.reset.channelHint')}</span>
              </div>
              <TextField
                label={t('auth.reset.email')}
                type="email"
                autoComplete="email"
                enterKeyHint="done"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <ErrorMessage>{error}</ErrorMessage>
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? t('auth.reset.sending') : t('auth.reset.sendCode')}
              </Button>
            </form>
          ) : (
            <form onSubmit={handleConfirm} className="flex flex-col gap-3.5">
              {info && <p className="text-sm text-ok">{info}</p>}
              <TextField
                label={t('auth.reset.codeLabel')}
                inputMode="numeric"
                enterKeyHint="next"
                autoComplete="one-time-code"
                numeric
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
              <TextField
                label={t('auth.reset.newPassword')}
                type="password"
                autoComplete="new-password"
                required
                hint={t('auth.reset.passwordHint')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <TextField
                label={t('auth.reset.confirm')}
                type="password"
                autoComplete="new-password"
                enterKeyHint="done"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
              <ErrorMessage>{error}</ErrorMessage>
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? t('auth.reset.changing') : t('auth.reset.changePassword')}
              </Button>
              <Button variant="ghost" onClick={backToRequest} disabled={loading} className="w-full">
                {t('auth.reset.resendCode')}
              </Button>
            </form>
          )}
          <p className="mt-4 text-center text-sm text-mist">
            {t('auth.reset.remembered')}{' '}
            <Link to="/login" className="font-semibold text-amber hover:text-amber-deep">
              {t('auth.reset.login')}
            </Link>
          </p>
        </Card>
      </div>
    </div>
  );
}
