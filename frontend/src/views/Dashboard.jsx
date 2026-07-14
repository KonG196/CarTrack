import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Car, Fuel, Receipt, Wallet, Droplets, Route, ChevronRight, CalendarClock } from 'lucide-react';
import { useCarStore } from '../store/carStore';
import { formatMoney, formatKm, formatDate } from '../utils/format';
import { Card, Spinner, ErrorMessage } from '../components/UI';

const STATUS_STYLES = {
  ok: { bar: 'bg-blue-500', text: 'text-blue-400', label: 'В нормі' },
  due_soon: { bar: 'bg-amber-500', text: 'text-amber-400', label: 'Скоро' },
  overdue: { bar: 'bg-red-500', text: 'text-red-400', label: 'Прострочено' },
};

function StatCard({ icon: Icon, label, value }) {
  return (
    <Card className="flex flex-col gap-1.5 p-3.5">
      <span className="flex items-center gap-1.5 text-xs text-slate-500">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </span>
      <span className="text-lg font-semibold leading-tight text-white">{value}</span>
    </Card>
  );
}

function IntervalRow({ interval }) {
  const style = STATUS_STYLES[interval.status] || STATUS_STYLES.ok;
  const pct = Math.max(0, Math.min(100, interval.health_pct ?? 0));

  const parts = [];
  if (interval.km_left !== null && interval.km_left !== undefined) {
    parts.push(interval.km_left >= 0 ? `${formatKm(interval.km_left)} залишилось` : `${formatKm(Math.abs(interval.km_left))} прострочено`);
  }
  if (interval.days_left !== null && interval.days_left !== undefined) {
    parts.push(interval.days_left >= 0 ? `${interval.days_left} дн.` : `${Math.abs(interval.days_left)} дн. тому`);
  }

  return (
    <div className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-sm font-medium text-slate-100">{interval.title}</p>
        <span className={`text-xs font-medium ${style.text}`}>{style.label}</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full rounded-full ${style.bar}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-slate-500">
        {parts.map((p) => (
          <span key={p}>{p}</span>
        ))}
        {interval.predicted_due_date && (
          <span className="flex items-center gap-1">
            <CalendarClock className="h-3 w-3" />
            приблизно {formatDate(interval.predicted_due_date)}
          </span>
        )}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const cars = useCarStore((s) => s.cars);
  const carsLoading = useCarStore((s) => s.carsLoading);
  const carsLoaded = useCarStore((s) => s.carsLoaded);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const analytics = useCarStore((s) => s.analytics);
  const analyticsLoading = useCarStore((s) => s.analyticsLoading);
  const analyticsError = useCarStore((s) => s.analyticsError);
  const intervals = useCarStore((s) => s.intervals);
  const intervalsLoading = useCarStore((s) => s.intervalsLoading);
  const intervalsError = useCarStore((s) => s.intervalsError);
  const fetchAnalytics = useCarStore((s) => s.fetchAnalytics);
  const fetchIntervals = useCarStore((s) => s.fetchIntervals);

  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;

  useEffect(() => {
    if (activeCarId) {
      fetchAnalytics().catch(() => {});
      fetchIntervals().catch(() => {});
    }
  }, [activeCarId, fetchAnalytics, fetchIntervals]);

  if (carsLoading && !carsLoaded) return <Spinner />;

  if (carsLoaded && cars.length === 0) {
    return (
      <Card className="mt-8 flex flex-col items-center gap-3 p-8 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600/15">
          <Car className="h-7 w-7 text-blue-500" />
        </span>
        <h2 className="text-lg font-semibold text-white">Вітаємо в Kapot Tracker!</h2>
        <p className="text-sm text-slate-400">
          Додайте своє перше авто, щоб почати вести журнал витрат та обслуговування.
        </p>
        <Link
          to="/garage"
          className="mt-2 inline-flex items-center gap-1 rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500"
        >
          Додати авто
          <ChevronRight className="h-4 w-4" />
        </Link>
      </Card>
    );
  }

  const fuel = analytics?.fuel;

  return (
    <div className="space-y-4">
      {activeCar && (
        <div className="flex items-baseline justify-between px-1">
          <h1 className="text-lg font-semibold text-white">
            {activeCar.brand} {activeCar.model}
          </h1>
          <span className="text-sm text-slate-500">{formatKm(activeCar.current_odometer)}</span>
        </div>
      )}

      {analyticsError && <ErrorMessage>{analyticsError}</ErrorMessage>}

      {analyticsLoading && !analytics ? (
        <Spinner />
      ) : (
        analytics && (
          <div className="grid grid-cols-3 gap-2.5">
            <StatCard
              icon={Wallet}
              label="Цей місяць"
              value={formatMoney(analytics.totals.this_month)}
            />
            <StatCard
              icon={Droplets}
              label="л/100 км"
              value={
                fuel?.avg_consumption_l_100km != null
                  ? fuel.avg_consumption_l_100km.toFixed(1)
                  : '—'
              }
            />
            <StatCard
              icon={Route}
              label="₴/км"
              value={fuel?.avg_cost_per_km != null ? fuel.avg_cost_per_km.toFixed(2) : '—'}
            />
          </div>
        )
      )}

      <div className="grid grid-cols-2 gap-2.5">
        <Link
          to="/add?type=refuel"
          className="flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-3.5 text-sm font-medium text-white transition-colors hover:bg-blue-500"
        >
          <Fuel className="h-4 w-4" />
          Заправка
        </Link>
        <Link
          to="/add?type=expense"
          className="flex items-center justify-center gap-2 rounded-2xl border border-slate-700 bg-slate-800 px-4 py-3.5 text-sm font-medium text-slate-100 transition-colors hover:bg-slate-700"
        >
          <Receipt className="h-4 w-4" />
          Витрата
        </Link>
      </div>

      <Card>
        <div className="mb-1 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Інтервали ТО</h2>
          <Link to="/garage" className="text-xs text-blue-500 hover:text-blue-400">
            Керувати
          </Link>
        </div>
        {intervalsError && <ErrorMessage className="my-2">{intervalsError}</ErrorMessage>}
        {intervalsLoading && intervals.length === 0 ? (
          <Spinner className="py-4" />
        ) : intervals.length === 0 ? (
          <p className="py-3 text-sm text-slate-500">
            Немає інтервалів обслуговування. Додайте їх у розділі «Гараж».
          </p>
        ) : (
          <div className="divide-y divide-slate-800">
            {intervals.map((interval) => (
              <IntervalRow key={interval.id} interval={interval} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
