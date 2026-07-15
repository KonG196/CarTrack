import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { MailCheck } from 'lucide-react';

import { confirmEmail, resendVerification } from '../api/auth';
import { Button, Card, ErrorMessage, TextField } from '../components/UI';
import Wordmark from '../components/Wordmark';
import Toast from '../components/Toast';
import { extractError } from '../api/client';

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [email, setEmail] = useState(searchParams.get('email') || '');
  const [code, setCode] = useState(searchParams.get('code') || '');
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [loading, setLoading] = useState(false);
  const autoSubmitted = useRef(false);

  const submit = async (mail, value) => {
    setError('');
    setLoading(true);
    try {
      await confirmEmail(mail.trim(), value.trim());
      setToast('Пошту підтверджено');
      setTimeout(() => navigate('/login', { replace: true }), 1200);
    } catch (err) {
      setError(extractError(err, 'Невірний або прострочений код'));
    } finally {
      setLoading(false);
    }
  };

  // The link from the letter carries both fields: confirm without a click,
  // but only once, or a failed attempt would retry itself forever.
  useEffect(() => {
    const mail = searchParams.get('email');
    const value = searchParams.get('code');
    if (mail && value && !autoSubmitted.current) {
      autoSubmitted.current = true;
      submit(mail, value);
    }
  }, [searchParams]);

  const handleResend = async () => {
    setError('');
    try {
      await resendVerification(email.trim());
      setToast('Якщо акаунт існує — код надіслано');
    } catch (err) {
      setError(extractError(err, 'Не вдалося надіслати код'));
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-garage px-4">
      <div className="rise-in w-full max-w-md">
        <div className="mb-6 flex flex-col items-center gap-2">
          <Wordmark size="lg" />
          <p className="font-mono text-xs uppercase tracking-[0.14em] text-mist">
            Підтвердження пошти
          </p>
        </div>
        <Card>
          <div className="mb-4 flex items-center gap-2">
            <MailCheck className="h-5 w-5 text-amber" />
            <h1 className="font-display text-lg font-semibold text-fg">Підтвердіть пошту</h1>
          </div>
          <p className="mb-4 text-sm text-mist">
            Ми надіслали 6-значний код на вашу адресу. Введіть його нижче або перейдіть за
            посиланням з листа.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit(email, code);
            }}
            className="flex flex-col gap-3.5"
          >
            <TextField
              label="Email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <TextField
              label="Код з листа"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
            />
            {error && <ErrorMessage>{error}</ErrorMessage>}
            <Button type="submit" disabled={loading}>
              {loading ? 'Перевіряю…' : 'Підтвердити'}
            </Button>
          </form>
          <div className="mt-4 flex items-center justify-between text-sm">
            <button
              type="button"
              onClick={handleResend}
              className="text-amber hover:underline"
            >
              Надіслати код ще раз
            </button>
            <Link to="/login" className="text-mist hover:text-fg">
              До входу
            </Link>
          </div>
        </Card>
      </div>
      {toast && <Toast message={toast} onDone={() => setToast('')} />}
    </div>
  );
}
