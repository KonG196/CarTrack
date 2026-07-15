import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Car, MailQuestion } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useCarStore } from '../store/carStore';
import { getInvite, acceptInvite } from '../api/members';
import { extractError } from '../api/client';
import { roleLabel } from '../utils/permissions';
import { Button, Card, Spinner, ErrorMessage } from '../components/UI';
import Wordmark from '../components/Wordmark';

const DEAD_INVITE =
  'Запрошення недійсне, прострочене або вже використане. Попросіть власника надіслати нове.';

function Shell({ children }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-garage px-4">
      <div className="rise-in w-full max-w-md">
        <div className="mb-6 flex flex-col items-center gap-2">
          <Wordmark size="lg" />
          <p className="font-mono text-xs uppercase tracking-[0.14em] text-mist">
            Бортовий журнал авто
          </p>
        </div>
        <Card>{children}</Card>
      </div>
    </div>
  );
}

export default function JoinCar() {
  const { token: inviteToken } = useParams();
  const navigate = useNavigate();
  const authToken = useAuthStore((s) => s.token);
  const logout = useAuthStore((s) => s.logout);
  const fetchCars = useCarStore((s) => s.fetchCars);
  const setActiveCar = useCarStore((s) => s.setActiveCar);

  const [invite, setInvite] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [needsAuth, setNeedsAuth] = useState(!authToken);
  const [accepting, setAccepting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    getInvite(inviteToken)
      .then((data) => {
        if (!cancelled) setInvite(data);
      })
      .catch((err) => {
        if (cancelled) return;
        const status = err?.response?.status;
        if (status === 401) {
          logout();
          setNeedsAuth(true);
        } else if (status === 404) {
          setError(DEAD_INVITE);
        } else {
          setError('Не вдалося завантажити запрошення. Спробуйте ще раз.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [inviteToken, logout]);

  const handleAccept = async () => {
    setError('');
    setAccepting(true);
    try {
      const membership = await acceptInvite(inviteToken);
      await fetchCars();
      if (membership?.car_id != null) setActiveCar(membership.car_id);
      navigate('/garage', { replace: true, state: { toast: 'Ви приєдналися до авто' } });
    } catch (err) {
      const status = err?.response?.status;
      setError(
        status === 404 ? DEAD_INVITE : extractError(err, 'Не вдалося прийняти запрошення')
      );
      setAccepting(false);
    }
  };

  if (loading) {
    return (
      <Shell>
        <Spinner className="py-8" />
      </Shell>
    );
  }

  if (error && !invite && !needsAuth) {
    return (
      <Shell>
        <ErrorMessage>{error}</ErrorMessage>
        <Link
          to="/"
          className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-amber hover:text-amber-deep"
        >
          На головну
        </Link>
      </Shell>
    );
  }

  const car = invite?.car;
  const carName = car ? `${car.brand} ${car.model}${car.year ? ` ${car.year}` : ''}` : null;
  const next = `/join/${encodeURIComponent(inviteToken)}`;

  return (
    <Shell>
      <div className="flex flex-col items-center gap-3 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-amber/15">
          {car ? <Car className="h-7 w-7 text-amber" /> : <MailQuestion className="h-7 w-7 text-amber" />}
        </span>

        {carName ? (
          <>
            <h1 className="font-display text-lg font-semibold text-fg">
              Вас запрошують до {carName}
            </h1>
            <p className="text-sm text-mist">
              {invite.inviter_label} відкриває вам доступ як {roleLabel(invite.role)}
              {invite.role === 'editor'
                ? ' — ви зможете вести журнал цього авто.'
                : ' — ви зможете переглядати журнал цього авто.'}
            </p>
          </>
        ) : (
          <>
            <h1 className="font-display text-lg font-semibold text-fg">Вас запрошують до авто</h1>
            <p className="text-sm text-mist">
              Увійдіть або створіть акаунт — і побачите, до якого авто вас кличуть.
            </p>
          </>
        )}
      </div>

      {error && <ErrorMessage className="mt-4">{error}</ErrorMessage>}

      {needsAuth ? (
        <div className="mt-5 space-y-2">
          <Link to={`/login?next=${encodeURIComponent(next)}`} className="block">
            <Button className="w-full">Увійти</Button>
          </Link>
          <Link to={`/register?next=${encodeURIComponent(next)}`} className="block">
            <Button variant="secondary" className="w-full">
              Зареєструватися
            </Button>
          </Link>
          <p className="pt-1 text-center text-xs text-mist/70">
            Після входу ви повернетесь сюди й зможете прийняти запрошення.
          </p>
        </div>
      ) : (
        <div className="mt-5 space-y-2">
          <Button onClick={handleAccept} disabled={accepting} className="w-full">
            {accepting
              ? 'Приєднання…'
              : `Приєднатися${carName ? ` до ${carName}` : ''} як ${roleLabel(invite?.role)}`}
          </Button>
          <Link to="/" className="block">
            <Button variant="ghost" className="w-full">
              Не зараз
            </Button>
          </Link>
        </div>
      )}
    </Shell>
  );
}
