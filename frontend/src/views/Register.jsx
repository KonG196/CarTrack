import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Car } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { extractError } from '../api/client';
import { Button, Input, Card, ErrorMessage } from '../components/UI';

export default function Register() {
  const register = useAuthStore((s) => s.register);
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (password !== confirm) {
      setError('Паролі не збігаються');
      return;
    }
    if (password.length < 6) {
      setError('Пароль має містити щонайменше 6 символів');
      return;
    }
    setLoading(true);
    try {
      await register(email.trim(), password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(extractError(err, 'Не вдалося зареєструватися'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center gap-2">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600">
            <Car className="h-8 w-8 text-white" />
          </span>
          <h1 className="text-2xl font-semibold text-white">Kapot Tracker</h1>
          <p className="text-sm text-slate-500">Журнал вашого авто</p>
        </div>
        <Card>
          <h2 className="mb-4 text-lg font-medium text-white">Реєстрація</h2>
          <form onSubmit={handleSubmit} className="space-y-3.5">
            <Input
              label="Email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
            <Input
              label="Пароль"
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Мінімум 6 символів"
            />
            <Input
              label="Повторіть пароль"
              type="password"
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="••••••••"
            />
            <ErrorMessage>{error}</ErrorMessage>
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? 'Створення…' : 'Створити акаунт'}
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-slate-500">
            Вже є акаунт?{' '}
            <Link to="/login" className="font-medium text-blue-500 hover:text-blue-400">
              Увійти
            </Link>
          </p>
        </Card>
      </div>
    </div>
  );
}
