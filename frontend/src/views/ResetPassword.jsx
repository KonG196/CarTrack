import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { requestPasswordReset, confirmPasswordReset } from '../api/auth';
import { extractError } from '../api/client';
import { Button, TextField, Card, ErrorMessage } from '../components/UI';
import Toast from '../components/Toast';
import Wordmark from '../components/Wordmark';

export default function ResetPassword() {
  const navigate = useNavigate();
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

  const handleRequest = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await requestPasswordReset(email.trim(), channel);
      setInfo(data?.detail || 'Якщо акаунт існує — ми надіслали код.');
      setStep(2);
    } catch (err) {
      setError(extractError(err, 'Не вдалося надіслати код'));
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async (e) => {
    e.preventDefault();
    setError('');
    if (password !== confirm) {
      setError('Паролі не збігаються');
      return;
    }
    if (password.length < 8) {
      setError('Пароль має містити щонайменше 8 символів');
      return;
    }
    setLoading(true);
    try {
      await confirmPasswordReset(email.trim(), code.trim(), password);
      setToast('Пароль змінено. Увійдіть з новим паролем.');
    } catch (err) {
      setError(extractError(err, 'Невірний або прострочений код'));
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
        <div className="mb-6 flex flex-col items-center gap-2">
          <Wordmark size="lg" />
          <p className="font-mono text-xs uppercase tracking-[0.14em] text-mist">
            Бортовий журнал авто
          </p>
        </div>
        <Card>
          <h1 className="mb-4 font-display text-lg font-semibold text-fg">Скидання пароля</h1>
          {step === 1 ? (
            <form onSubmit={handleRequest} className="flex flex-col gap-3.5">
              <p className="text-sm text-mist">
                Вкажіть email акаунта — надішлемо 6-значний код.
              </p>
              <div className="flex flex-col gap-1.5">
                <span className="text-xs text-mist">Куди надіслати код</span>
                <div className="flex gap-2">
                  {[
                    { value: 'email', label: 'На пошту' },
                    { value: 'telegram', label: 'У Telegram' },
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
                <span className="text-xs text-mist">
                  Telegram спрацює, лише якщо ви привʼязали бота — інакше код прийде на пошту.
                </span>
              </div>
              <TextField
                label="Email"
                type="email"
                autoComplete="email"
                enterKeyHint="done"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <ErrorMessage>{error}</ErrorMessage>
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? 'Надсилання…' : 'Надіслати код'}
              </Button>
            </form>
          ) : (
            <form onSubmit={handleConfirm} className="flex flex-col gap-3.5">
              {info && <p className="text-sm text-ok">{info}</p>}
              <TextField
                label="Код з листа або Telegram"
                inputMode="numeric"
                enterKeyHint="next"
                autoComplete="one-time-code"
                numeric
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
              <TextField
                label="Новий пароль"
                type="password"
                autoComplete="new-password"
                required
                hint="Мінімум 8 символів"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <TextField
                label="Повторіть пароль"
                type="password"
                autoComplete="new-password"
                enterKeyHint="done"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
              <ErrorMessage>{error}</ErrorMessage>
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? 'Зміна пароля…' : 'Змінити пароль'}
              </Button>
              <Button variant="ghost" onClick={backToRequest} disabled={loading} className="w-full">
                Надіслати код ще раз
              </Button>
            </form>
          )}
          <p className="mt-4 text-center text-sm text-mist">
            Згадали пароль?{' '}
            <Link to="/login" className="font-semibold text-amber hover:text-amber-deep">
              Увійти
            </Link>
          </p>
        </Card>
      </div>
    </div>
  );
}
