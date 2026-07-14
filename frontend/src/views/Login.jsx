import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Car } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { extractError } from '../api/client';
import { Button, Input, Card, ErrorMessage } from '../components/UI';

export default function Login() {
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();
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
      navigate('/', { replace: true });
    } catch (err) {
      setError(extractError(err, 'Невірний email або пароль'));
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
          <h2 className="mb-4 text-lg font-medium text-white">Вхід</h2>
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
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
            <ErrorMessage>{error}</ErrorMessage>
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? 'Вхід…' : 'Увійти'}
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-slate-500">
            Немає акаунта?{' '}
            <Link to="/register" className="font-medium text-blue-500 hover:text-blue-400">
              Зареєструватися
            </Link>
          </p>
        </Card>
      </div>
    </div>
  );
}
