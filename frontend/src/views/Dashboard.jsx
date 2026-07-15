import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Car,
  Fuel,
  Receipt,
  Wallet,
  Droplets,
  Route,
  Gauge,
  ChevronRight,
  CalendarClock,
  Pencil,
  Check,
  CheckCircle2,
  X,
  Loader2,
} from 'lucide-react';
import { useCarStore } from '../store/carStore';
import { extractError } from '../api/client';
import { getRefuelContext } from '../api/logs';
import { canDo } from '../utils/permissions';
import { formatMoney, formatKm, formatDate } from '../utils/format';
import { Card, Spinner, ErrorMessage, ConfirmDialog } from '../components/UI';
import Toast from '../components/Toast';
import CompleteIntervalModal from '../components/CompleteIntervalModal';

const STATUS_STYLES = {
  ok: { bar: 'bg-ok', text: 'text-ok', label: 'В нормі' },
  due_soon: { bar: 'bg-amber', text: 'text-amber', label: 'Скоро' },
  overdue: { bar: 'bg-crit', text: 'text-crit', label: 'Прострочено' },
};

const BUDGET_STYLES = {
  ok: { bar: 'bg-ok', text: 'text-fg' },
  warn: { bar: 'bg-amber', text: 'text-amber' },
  over: { bar: 'bg-crit', text: 'text-crit' },
};

function StatCard({ icon: Icon, label, value }) {
  return (
    <Card className="flex flex-col gap-1.5 p-3.5">
      <span className="flex items-start gap-1.5 text-xs text-mist">
        <Icon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
        {label}
      </span>
      <span className="mt-auto font-mono text-lg font-semibold leading-tight tabular-nums text-fg">
        {value}
      </span>
    </Card>
  );
}

function BudgetCard({ budget }) {
  const style = BUDGET_STYLES[budget.status] || BUDGET_STYLES.ok;
  const pct = Math.max(0, Math.min(100, budget.pct_used));

  return (
    <Card>
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-display text-sm font-semibold text-fg">Бюджет місяця</h2>
        <span className={`font-mono text-xs tabular-nums ${style.text}`}>
          {formatMoney(budget.spent_this_month)} / {formatMoney(budget.limit)}
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-raised">
        <div className={`bar-fill h-full rounded-full ${style.bar}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-mist">
        <span>{Math.round(budget.pct_used)}% витрачено</span>
        {budget.projected_month_total != null && (
          <span>прогноз: {formatMoney(budget.projected_month_total)}</span>
        )}
      </div>
    </Card>
  );
}

function RangeCard({ rangeKm }) {
  return (
    <Card className="flex items-center gap-3">
      <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-signal/15">
        <Gauge className="h-5 w-5 text-signal" />
      </span>
      <p className="flex-1 text-sm text-fg">
        Запас ходу на повному баку:{' '}
        <span className="font-mono font-semibold tabular-nums">~{formatKm(rangeKm)}</span>
      </p>
    </Card>
  );
}

function IntervalRow({ interval, onComplete, canComplete }) {
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
        <p className="text-sm font-medium text-fg">{interval.title}</p>
        <span className={`text-xs font-medium ${style.text}`}>{style.label}</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-raised">
        <div className={`bar-fill h-full rounded-full ${style.bar}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-mist">
        {parts.map((p) => (
          <span key={p}>{p}</span>
        ))}
        {interval.predicted_due_date && (
          <span className="flex items-center gap-1">
            <CalendarClock className="h-3 w-3" />
            приблизно {formatDate(interval.predicted_due_date)}
          </span>
        )}
        {canComplete && (
          <button
            type="button"
            onClick={() => onComplete(interval)}
            aria-label={`Виконано: ${interval.title}`}
            className="ml-auto flex flex-shrink-0 items-center gap-1 rounded-lg px-1.5 py-0.5 font-medium text-mist/70 transition-colors hover:bg-ok/10 hover:text-ok"
          >
            <CheckCircle2 className="h-3 w-3" />
            Виконано
          </button>
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
  const editCar = useCarStore((s) => s.editCar);
  const completeInterval = useCarStore((s) => s.completeInterval);

  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;

  const canEditCar = canDo(activeCar?.your_role, 'car:edit');
  const canAddEntries = canDo(activeCar?.your_role, 'log:create');
  const canCompleteIntervals = canDo(activeCar?.your_role, 'interval:complete');

  // quick odometer edit
  const [editingOdo, setEditingOdo] = useState(false);
  const [odoValue, setOdoValue] = useState('');
  const [odoSaving, setOdoSaving] = useState(false);
  const [odoError, setOdoError] = useState('');
  const [confirmLower, setConfirmLower] = useState(false);

  const [completingInterval, setCompletingInterval] = useState(null);
  const [toast, setToast] = useState('');

  const [refuelContext, setRefuelContext] = useState(null);
  const noRefuelsYet = refuelContext != null && refuelContext.last_refuel_odometer == null;

  const startOdoEdit = () => {
    setOdoValue(String(activeCar.current_odometer));
    setOdoError('');
    setEditingOdo(true);
  };

  const cancelOdoEdit = () => {
    setEditingOdo(false);
    setOdoError('');
  };

  const saveOdometer = async () => {
    setConfirmLower(false);
    setOdoSaving(true);
    setOdoError('');
    try {
      await editCar(activeCar.id, { current_odometer: parseInt(odoValue, 10) });
      fetchIntervals().catch(() => {});
      fetchAnalytics().catch(() => {});
      setEditingOdo(false);
    } catch (err) {
      setOdoError(extractError(err, 'Не вдалося оновити пробіг'));
    } finally {
      setOdoSaving(false);
    }
  };

  const submitOdometer = () => {
    const odo = parseInt(odoValue, 10);
    if (!Number.isFinite(odo) || odo < 0) {
      setOdoError('Вкажіть коректний пробіг');
      return;
    }
    if (odo < activeCar.current_odometer) {
      setConfirmLower(true);
      return;
    }
    saveOdometer();
  };

  useEffect(() => {
    if (activeCarId) {
      fetchAnalytics().catch(() => {});
      fetchIntervals().catch(() => {});
    }
  }, [activeCarId, fetchAnalytics, fetchIntervals]);

  useEffect(() => {
    setRefuelContext(null);
    if (!activeCarId) return undefined;
    let cancelled = false;
    getRefuelContext(activeCarId)
      .then((data) => {
        if (!cancelled) setRefuelContext(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [activeCarId]);

  if (carsLoading && !carsLoaded) return <Spinner />;

  if (carsLoaded && cars.length === 0) {
    return (
      <Card className="rise-in mt-8 flex flex-col items-center gap-3 p-8 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-amber/15">
          <Car className="h-7 w-7 text-amber" />
        </span>
        <h2 className="font-display text-lg font-semibold text-fg">Вітаємо в Kapot Tracker!</h2>
        <p className="text-sm text-mist">
          Додайте своє перше авто, щоб почати вести журнал витрат та обслуговування.
        </p>
        <Link
          to="/garage"
          className="mt-2 inline-flex items-center gap-1 rounded-xl bg-amber px-5 py-2.5 text-sm font-medium text-amber-ink transition-colors hover:bg-amber-deep"
        >
          Додати авто
          <ChevronRight className="h-4 w-4" />
        </Link>
      </Card>
    );
  }

  const fuel = analytics?.fuel;

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />

      <CompleteIntervalModal
        interval={completingInterval}
        car={activeCar}
        onComplete={completeInterval}
        onClose={() => setCompletingInterval(null)}
        onToast={setToast}
      />

      {activeCar && (
        <>
          <ConfirmDialog
            open={confirmLower}
            title="Зменшити пробіг?"
            message={`Нове значення менше за поточне (${formatKm(activeCar.current_odometer)}). Точно зменшити?`}
            confirmLabel="Зменшити"
            onConfirm={saveOdometer}
            onCancel={() => setConfirmLower(false)}
          />
          <div className="flex items-center justify-between gap-2 px-1">
            <h1 className="font-display text-lg font-semibold text-fg">
              {activeCar.brand} {activeCar.model}
            </h1>
            {editingOdo ? (
              <span className="flex items-center gap-1">
                <input
                  type="number"
                  inputMode="numeric"
                  min="0"
                  autoFocus
                  value={odoValue}
                  disabled={odoSaving}
                  onChange={(e) => setOdoValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      submitOdometer();
                    }
                    if (e.key === 'Escape') cancelOdoEdit();
                  }}
                  aria-label="Поточний пробіг, км"
                  className="w-28 rounded-lg border border-edge-soft bg-raised px-2 py-1 text-right font-mono text-sm tabular-nums text-fg outline-none focus:border-amber"
                />
                <button
                  type="button"
                  onClick={submitOdometer}
                  disabled={odoSaving}
                  aria-label="Зберегти пробіг"
                  className="rounded-lg p-1.5 text-ok transition-colors hover:bg-raised"
                >
                  {odoSaving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Check className="h-4 w-4" />
                  )}
                </button>
                <button
                  type="button"
                  onClick={cancelOdoEdit}
                  disabled={odoSaving}
                  aria-label="Скасувати зміну пробігу"
                  className="rounded-lg p-1.5 text-mist transition-colors hover:bg-raised hover:text-fg"
                >
                  <X className="h-4 w-4" />
                </button>
              </span>
            ) : (
              <span className="flex items-center gap-0.5 text-sm text-mist">
                {formatKm(activeCar.current_odometer)}
                {canEditCar && (
                  <button
                    type="button"
                    onClick={startOdoEdit}
                    aria-label="Змінити пробіг"
                    className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-panel hover:text-fg"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                )}
              </span>
            )}
          </div>
          {odoError && <ErrorMessage>{odoError}</ErrorMessage>}
        </>
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

      {analytics?.budget && <BudgetCard budget={analytics.budget} />}

      {analytics?.range_km != null && <RangeCard rangeKm={analytics.range_km} />}

      {noRefuelsYet && canAddEntries && (
        <Link to="/add?type=refuel" className="block">
          <Card className="flex items-center gap-3 transition-colors hover:border-edge-soft">
            <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-amber/15">
              <Fuel className="h-5 w-5 text-amber" />
            </span>
            <p className="flex-1 text-sm text-fg">
              Додайте першу заправку — і побачите свій реальний розхід
            </p>
            <ChevronRight className="h-4 w-4 flex-shrink-0 text-mist" />
          </Card>
        </Link>
      )}

      {canAddEntries && (
        <div className="grid grid-cols-2 gap-2.5">
          <Link
            to="/add?type=refuel"
            className="flex items-center justify-center gap-2 rounded-2xl bg-amber px-4 py-3.5 text-sm font-medium text-amber-ink transition-colors hover:bg-amber-deep"
          >
            <Fuel className="h-4 w-4" />
            Заправка
          </Link>
          <Link
            to="/add?type=expense"
            className="flex items-center justify-center gap-2 rounded-2xl border border-edge-soft bg-raised px-4 py-3.5 text-sm font-medium text-fg transition-colors hover:bg-edge"
          >
            <Receipt className="h-4 w-4" />
            Витрата
          </Link>
        </div>
      )}

      <Card>
        <div className="mb-1 flex items-center justify-between">
          <h2 className="font-display text-sm font-semibold text-fg">Інтервали ТО</h2>
          <Link to="/garage" className="text-xs text-amber hover:text-amber-deep">
            Керувати
          </Link>
        </div>
        {intervalsError && <ErrorMessage className="my-2">{intervalsError}</ErrorMessage>}
        {intervalsLoading && intervals.length === 0 ? (
          <Spinner className="py-4" />
        ) : intervals.length === 0 ? (
          <p className="py-3 text-sm text-mist">
            {canDo(activeCar?.your_role, 'interval:manage')
              ? 'Немає інтервалів обслуговування. Додайте їх у розділі «Гараж».'
              : 'Власник ще не додав інтервалів обслуговування.'}
          </p>
        ) : (
          <div className="divide-y divide-edge">
            {intervals.map((interval) => (
              <IntervalRow
                key={interval.id}
                interval={interval}
                onComplete={setCompletingInterval}
                canComplete={canCompleteIntervals}
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
