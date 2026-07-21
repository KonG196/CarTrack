import { useCallback, useEffect, useState } from 'react';
import { flushSync } from 'react-dom';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Home, BookOpen, PlusCircle, BarChart2, Settings, Car, Plus } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useCarStore } from '../store/carStore';
import { Menu } from './UI';
import AppBadge from './AppBadge';
import OfflineBanner from './OfflineBanner';
import Toast from './Toast';
import Wordmark from './Wordmark';
import { TourProvider } from '../tour/TourContext';
import TourOverlay from '../tour/TourOverlay';

function recordsPlural(n) {
  const tens = n % 100;
  const ones = n % 10;
  if (ones === 1 && tens !== 11) return 'запис';
  if (ones >= 2 && ones <= 4 && (tens < 12 || tens > 14)) return 'записи';
  return 'записів';
}

const NAV_ITEMS = [
  { to: '/', label: 'Головна', icon: Home, end: true },
  { to: '/logbook', label: 'Журнал', icon: BookOpen, tour: 'nav-logbook' },
  { to: '/add', label: 'Додати', icon: PlusCircle, primary: true, tour: 'nav-add' },
  { to: '/analytics', label: 'Аналітика', icon: BarChart2, tour: 'nav-analytics' },
  { to: '/garage', label: 'Налаштування', icon: Settings, tour: 'nav-settings' },
];

// Горизонтальний порядок табів — з нього беремо напрямок слайду.
const TAB_ORDER = ['/', '/logbook', '/analytics', '/garage'];

// Напрямок слайду: «Додати» — знизу вгору й назад униз, решта — вліво/вправо за
// порядком табів. Керує тим, які кадри бере CSS через data-vt на <html>.
function directionFor(from, to) {
  if (to === '/add') return 'up';
  if (from === '/add') return 'down';
  const fi = TAB_ORDER.indexOf(from);
  const ti = TAB_ORDER.indexOf(to);
  if (fi !== -1 && ti !== -1) return ti > fi ? 'forward' : 'back';
  return 'forward';
}

function CarSelector() {
  const cars = useCarStore((s) => s.cars);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const setActiveCar = useCarStore((s) => s.setActiveCar);

  if (cars.length === 0) return null;

  const active = cars.find((c) => String(c.id) === String(activeCarId)) || cars[0];
  // Generation without the trailing colour ("7 (BA5), Сірий" → "7 (BA5)").
  const genOf = (car) => (car.generation ? car.generation.split(',')[0].trim() : '');
  const activeGen = genOf(active);

  return (
    <Menu
      ariaLabel="Активне авто"
      value={String(active.id)}
      onSelect={setActiveCar}
      items={cars.map((car) => {
        const gen = genOf(car);
        return {
          value: String(car.id),
          label: [car.brand, car.model, gen].filter(Boolean).join(' '),
        };
      })}
      buttonClassName="flex min-w-0 max-w-[46vw] items-center gap-1.5 rounded-xl border border-edge bg-panel py-1.5 pl-2.5 pr-3 text-sm text-fg transition-colors hover:border-edge-soft"
      button={
        <>
          <Car className="h-4 w-4 flex-shrink-0 text-amber" />
          {/* Model + generation, engine tail — the whole line truncates with an
              ellipsis rather than pushing the wordmark: min-w-0 lets it shrink. */}
          <span className="min-w-0 truncate">
            {[active.model, activeGen].filter(Boolean).join(' ')}
            {active.engine ? <span className="text-mist"> · {active.engine}</span> : null}
          </span>
        </>
      }
      footer={
        <NavLink
          to="/garage/new"
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-mist transition-colors hover:bg-raised hover:text-fg"
        >
          <Plus className="h-4 w-4 flex-shrink-0" />
          Додати авто
        </NavLink>
      }
    />
  );
}

export default function Layout() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const fetchMe = useAuthStore((s) => s.fetchMe);
  const fetchCars = useCarStore((s) => s.fetchCars);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const fetchMembers = useCarStore((s) => s.fetchMembers);
  const flushOutbox = useCarStore((s) => s.flushOutbox);
  const location = useLocation();
  const navigate = useNavigate();
  const [syncToast, setSyncToast] = useState('');

  // Slide between tabs the way an iOS app does: the leaving page moves one way,
  // the arriving page moves in from the other side, both at once. BrowserRouter
  // ignores NavLink's `viewTransition` prop (that only fires under the data
  // router), so we drive the View Transition ourselves. `flushSync` commits the
  // route change inside the capture callback so the «after» snapshot is the new
  // page, already settled (`.vt` suppresses its own entrance). Marking the new
  // <main> «.vt-settle» keeps that entrance from replaying once the slide ends.
  // Where the API is missing (older Safari) the NavLink just navigates — instant,
  // no animation, as before.
  const onNavClick = useCallback(
    (e, to) => {
      const from = location.pathname;
      if (to === from) {
        e.preventDefault();
        return;
      }
      if (!document.startViewTransition) return;
      e.preventDefault();
      const html = document.documentElement;
      html.dataset.vt = directionFor(from, to);
      html.classList.add('vt');
      const transition = document.startViewTransition(() => {
        flushSync(() => navigate(to));
        document.querySelector('main')?.classList.add('vt-settle');
      });
      transition.finished.finally(() => {
        html.classList.remove('vt');
        delete html.dataset.vt;
      });
    },
    [location.pathname, navigate],
  );

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

  // A fresh page starts at the top. Without this the browser keeps the previous
  // scroll offset, so opening Profile from the foot of Settings lands you
  // halfway down a page you have not seen.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <TourProvider>
    <div className="min-h-screen bg-garage">
      <AppBadge />
      <header className="app-header sticky top-0 z-40 border-b border-edge bg-garage/90 pt-[env(safe-area-inset-top)] backdrop-blur">
        <div className="mx-auto flex max-w-md items-center justify-between gap-3 px-4 py-3">
          <NavLink to="/" aria-label="На головну" className="shrink-0">
            <Wordmark />
          </NavLink>
          <span data-tour="car-switcher" className="min-w-0">
            <CarSelector />
          </span>
        </div>
      </header>

      <OfflineBanner />
      <Toast message={syncToast} onDone={() => setSyncToast('')} />

      <main className="mx-auto max-w-md px-4 pb-28 pt-4" key={location.pathname}>
        <Outlet />
      </main>

      <nav className="app-nav fixed inset-x-0 bottom-0 z-40 border-t border-edge bg-garage/95 backdrop-blur">
        <div className="mx-auto grid max-w-md grid-cols-5 items-end px-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-1.5">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end, primary, tour }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={(e) => onNavClick(e, to)}
              data-tour={tour}
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
      <TourOverlay />
    </div>
    </TourProvider>
  );
}
