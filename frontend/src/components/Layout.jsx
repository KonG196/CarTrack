import { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { Home, BookOpen, PlusCircle, BarChart2, Settings, Car, LogOut } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useCarStore } from '../store/carStore';
import { Menu } from './UI';
import OfflineBanner from './OfflineBanner';
import Toast from './Toast';
import Wordmark from './Wordmark';

function recordsPlural(n) {
  const tens = n % 100;
  const ones = n % 10;
  if (ones === 1 && tens !== 11) return 'запис';
  if (ones >= 2 && ones <= 4 && (tens < 12 || tens > 14)) return 'записи';
  return 'записів';
}

const NAV_ITEMS = [
  { to: '/', label: 'Головна', icon: Home, end: true },
  { to: '/logbook', label: 'Журнал', icon: BookOpen },
  { to: '/add', label: 'Додати', icon: PlusCircle, primary: true },
  { to: '/analytics', label: 'Аналітика', icon: BarChart2 },
  { to: '/garage', label: 'Гараж', icon: Settings },
];

function CarSelector() {
  const cars = useCarStore((s) => s.cars);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const setActiveCar = useCarStore((s) => s.setActiveCar);

  if (cars.length === 0) return null;

  const active = cars.find((c) => String(c.id) === String(activeCarId)) || cars[0];

  return (
    <Menu
      ariaLabel="Активне авто"
      value={String(active.id)}
      onSelect={setActiveCar}
      items={cars.map((car) => ({
        value: String(car.id),
        label: `${car.brand} ${car.model}`,
      }))}
      buttonClassName="flex max-w-[9.5rem] items-center gap-1.5 rounded-xl border border-edge bg-panel py-1.5 pl-2.5 pr-3 text-sm text-fg transition-colors hover:border-edge-soft"
      button={
        <>
          <Car className="h-4 w-4 flex-shrink-0 text-amber" />
          <span className="truncate">{active.model}</span>
        </>
      }
    />
  );
}

export default function Layout() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const fetchMe = useAuthStore((s) => s.fetchMe);
  const logout = useAuthStore((s) => s.logout);
  const fetchCars = useCarStore((s) => s.fetchCars);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const fetchMembers = useCarStore((s) => s.fetchMembers);
  const flushOutbox = useCarStore((s) => s.flushOutbox);
  const resetCars = useCarStore((s) => s.reset);
  const location = useLocation();
  const [syncToast, setSyncToast] = useState('');

  useEffect(() => {
    if (token && !user) {
      fetchMe().catch(() => {});
    }
  }, [token, user, fetchMe]);

  useEffect(() => {
    if (token) {
      fetchCars().catch(() => {});
    }
  }, [token, fetchCars]);

  useEffect(() => {
    if (token && activeCarId) {
      fetchMembers(activeCarId).catch(() => {});
    }
  }, [token, activeCarId, fetchMembers]);

  const sync = useCallback(() => {
    flushOutbox()
      .then((report) => {
        if (report.sent > 0) {
          setSyncToast(`${report.sent} ${recordsPlural(report.sent)} синхронізовано`);
        }
      })
      .catch(() => {});
  }, [flushOutbox]);

  useEffect(() => {
    if (!token) return undefined;
    if (navigator.onLine) sync();
    window.addEventListener('online', sync);
    return () => window.removeEventListener('online', sync);
  }, [token, sync]);

  const handleLogout = () => {
    resetCars();
    logout();
  };

  return (
    <div className="min-h-screen bg-garage">
      <header className="sticky top-0 z-40 border-b border-edge bg-garage/90 backdrop-blur">
        <div className="mx-auto flex max-w-md items-center justify-between gap-3 px-4 py-3">
          <NavLink to="/" aria-label="На головну">
            <Wordmark />
          </NavLink>
          <div className="flex items-center gap-2">
            <CarSelector />
            <button
              type="button"
              onClick={handleLogout}
              aria-label="Вийти"
              title="Вийти"
              className="rounded-xl p-2 text-mist transition-colors hover:bg-panel hover:text-fg"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      <OfflineBanner />
      <Toast message={syncToast} onDone={() => setSyncToast('')} />

      <main className="mx-auto max-w-md px-4 pb-28 pt-4" key={location.pathname}>
        <Outlet />
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-edge bg-garage/95 backdrop-blur">
        <div className="mx-auto grid max-w-md grid-cols-5 items-end px-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-1.5">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end, primary }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex flex-col items-center gap-0.5 text-[11px] font-medium transition-colors ${
                  primary ? 'text-mist' : isActive ? 'text-amber' : 'text-mist hover:text-fg'
                }`
              }
            >
              {primary ? (
                <span className="-mt-8 flex h-14 w-14 items-center justify-center rounded-full border-4 border-garage bg-amber text-amber-ink shadow-lg shadow-black/50 transition-transform active:scale-95 motion-reduce:transition-none">
                  <Icon className="h-7 w-7" />
                </span>
              ) : (
                <Icon className="h-5 w-5" />
              )}
              <span>{label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
