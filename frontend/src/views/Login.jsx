import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { extractError } from '../api/client';
import { safeNext, withNext } from '../utils/nextPath';
import { Button, TextField, Card, ErrorMessage } from '../components/UI';
import Wordmark from '../components/Wordmark';

export default function Login() {
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = safeNext(searchParams.get('next'));
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email.trim(), password);
      navigate(next, { replace: true });
    } catch (err) {
      if (err?.response?.status === 403) {
        navigate(`/verify?email=${encodeURIComponent(email.trim())}`);
        return;
      }
      setError(extractError(err, 'Невірний email або пароль'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-garage px-4">
      <div className="rise-in w-full max-w-md">
        {/* Логотип веде на лендінг (/welcome) — звичайне <a>, бо це статична
            сторінка поза React-роутером. Повне перезавантаження тут доречне:
            людина йде на маркетингову сторінку, а не в застосунок. */}
        <a
          href="/welcome"
          className="mb-6 flex flex-col items-center gap-2 rounded-xl transition-opacity hover:opacity-90"
        >
          <Wordmark size="lg" />
          <p className="font-mono text-xs uppercase tracking-[0.14em] text-mist">
            Бортовий журнал авто
          </p>
        </a>
        <Card>
          <h1 className="mb-4 font-display text-lg font-semibold text-fg">Вхід</h1>
          <form onSubmit={handleSubmit} className="flex flex-col gap-3.5">
            <TextField
              label="Email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <TextField
              label="Пароль"
              type="password"
              autoComplete="current-password"
              enterKeyHint="done"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <ErrorMessage>{error}</ErrorMessage>
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? 'Вхід…' : 'Увійти'}
            </Button>
          </form>
          <p className="mt-4 text-center text-sm">
            <Link to="/reset" className="font-semibold text-amber hover:text-amber-deep">
              Забули пароль?
            </Link>
          </p>
          <p className="mt-2 text-center text-sm text-mist">
            Немає акаунта?{' '}
            <Link
              to={withNext('/register', next)}
              className="font-semibold text-amber hover:text-amber-deep"
            >
              Зареєструватися
            </Link>
          </p>
        </Card>
      </div>
    </div>
  );
}
