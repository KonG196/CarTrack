import { useEffect } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { Home, BookOpen, PlusCircle, BarChart2, Settings, Car, LogOut } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useCarStore } from '../store/carStore';

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

  return (
    <div className="flex items-center gap-1.5 rounded-xl border border-slate-800 bg-slate-900 py-1.5 pl-2.5 pr-1">
      <Car className="h-4 w-4 flex-shrink-0 text-blue-500" />
      <select
        aria-label="Активне авто"
        value={activeCarId || ''}
        onChange={(e) => setActiveCar(e.target.value)}
        className="max-w-[10rem] appearance-none bg-transparent pr-1 text-sm text-slate-200 outline-none"
      >
        {cars.map((car) => (
          <option key={car.id} value={car.id} className="bg-slate-900">
            {car.brand} {car.model}
          </option>
        ))}
      </select>
    </div>
  );
}

export default function Layout() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const fetchMe = useAuthStore((s) => s.fetchMe);
  const logout = useAuthStore((s) => s.logout);
  const fetchCars = useCarStore((s) => s.fetchCars);
  const resetCars = useCarStore((s) => s.reset);
  const location = useLocation();

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

  const handleLogout = () => {
    resetCars();
    logout();
  };

  return (
    <div className="min-h-screen bg-slate-950">
      <header className="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-md items-center justify-between gap-3 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-600">
              <Car className="h-5 w-5 text-white" />
            </span>
            <span className="text-lg font-semibold tracking-tight text-white">Kapot Tracker</span>
          </NavLink>
          <div className="flex items-center gap-2">
            <CarSelector />
            <button
              type="button"
              onClick={handleLogout}
              aria-label="Вийти"
              title="Вийти"
              className="rounded-xl p-2 text-slate-500 transition-colors hover:bg-slate-900 hover:text-slate-300"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-md px-4 pb-28 pt-4" key={location.pathname}>
        <Outlet />
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-800 bg-slate-950/95 backdrop-blur">
        <div className="mx-auto grid max-w-md grid-cols-5 items-end px-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-1.5">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end, primary }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex flex-col items-center gap-0.5 text-[11px] font-medium transition-colors ${
                  primary
                    ? 'text-slate-300'
                    : isActive
                      ? 'text-blue-500'
                      : 'text-slate-500 hover:text-slate-300'
                }`
              }
            >
              {primary ? (
                <span className="-mt-8 flex h-14 w-14 items-center justify-center rounded-full border-4 border-slate-950 bg-blue-600 text-white shadow-lg shadow-blue-950">
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
