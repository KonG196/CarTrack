import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Car,
  Fuel,
  ArrowUpRight,
  Wallet,
  Droplets,
  Route,
  Gauge,
  ChevronRight,
  CalendarClock,
  Pencil,
  CheckCircle2,
} from 'lucide-react';
import { useCarStore } from '../store/carStore';
import { getRefuelContext } from '../api/logs';
import { canDo } from '../utils/permissions';
import { fuelKindLabel } from '../utils/fuelKind';
import { formatMoney, formatMoneyCompact, formatKm, formatDate } from '../utils/format';
import { Card, Spinner, ErrorMessage } from '../components/UI';
import Toast from '../components/Toast';
import NotificationsBanner from '../components/NotificationsBanner';
import CompleteIntervalModal from '../components/CompleteIntervalModal';
import CopyCarName from '../components/CopyCarName';

const STATUS_STYLES = {
  ok: { bar: 'bg-ok', text: 'text-ok', labelKey: 'statusOk' },
  due_soon: { bar: 'bg-amber', text: 'text-amber', labelKey: 'statusDueSoon' },
  overdue: { bar: 'bg-crit', text: 'text-crit', labelKey: 'statusOverdue' },
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
      <span className="mt-auto whitespace-nowrap font-mono text-base font-semibold leading-tight tabular-nums text-fg">
        {value}
      </span>
    </Card>
  );
}

function BudgetCard({ budget }) {
  const { t } = useTranslation();
  const style = BUDGET_STYLES[budget.status] || BUDGET_STYLES.ok;
  const pct = Math.max(0, Math.min(100, budget.pct_used));

  return (
    <Card>
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-display text-sm font-semibold text-fg">{t('dashboard.budgetTitle')}</h2>
        <span className={`font-mono text-xs tabular-nums ${style.text}`}>
          {formatMoney(budget.spent_this_month)} / {formatMoney(budget.limit)}
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-raised">
        <div className={`bar-fill h-full rounded-full ${style.bar}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-mist">
        <span>{t('dashboard.budgetPctUsed', { pct: Math.round(budget.pct_used) })}</span>
        {budget.projected_month_total != null && (
          <span>{t('dashboard.budgetProjected', { amount: formatMoney(budget.projected_month_total) })}</span>
        )}
      </div>
    </Card>
  );
}

function RangeCard({ rangeKm }) {
  const { t } = useTranslation();
  return (
    <Card className="flex items-center gap-3">
      <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-signal/15">
        <Gauge className="h-5 w-5 text-signal" />
      </span>
      <p className="flex-1 text-sm text-fg">
        {t('dashboard.rangeOnFullTank')}{' '}
        <span className="font-mono font-semibold tabular-nums">~{formatKm(rangeKm)}</span>
      </p>
    </Card>
  );
}

function IntervalRow({ interval, onComplete, canComplete, tourId }) {
  const { t } = useTranslation();
  const style = STATUS_STYLES[interval.status] || STATUS_STYLES.ok;
  const pct = Math.max(0, Math.min(100, interval.health_pct ?? 0));

  // An interval falls due when EITHER its distance or its time runs out, so a
  // brake-fluid job can be overdue on time while the odometer still has slack.
  // Showing that slack ("10 873 км залишилось") next to a «Прострочено» badge
  // reads as a contradiction — once overdue, only surface what is overdue.
  const overdue = interval.status === 'overdue';
  const parts = [];
  if (interval.km_left !== null && interval.km_left !== undefined) {
    if (interval.km_left < 0) parts.push(t('dashboard.overdueBy', { distance: formatKm(Math.abs(interval.km_left)) }));
    else if (!overdue) parts.push(t('dashboard.kmLeft', { distance: formatKm(interval.km_left) }));
  }
  if (interval.days_left !== null && interval.days_left !== undefined) {
    if (interval.days_left < 0) parts.push(t('dashboard.daysAgo', { days: Math.abs(interval.days_left) }));
    else if (!overdue) parts.push(t('dashboard.daysLeft', { days: interval.days_left }));
  }

  const body = (
    <>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-sm font-medium text-fg">{interval.title}</p>
        <span className={`text-xs font-medium ${style.text}`}>{t(`dashboard.${style.labelKey}`)}</span>
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
            {t('dashboard.approxDate', { date: formatDate(interval.predicted_due_date) })}
          </span>
        )}
        {canComplete && (
          <CheckCircle2 className="ml-auto h-4 w-4 flex-shrink-0 text-mist/40 transition-colors group-hover:text-ok" />
        )}
      </div>
    </>
  );

  // Tapping the interval is the action: it opens the «Виконано» form for this
  // one. A separate button read as a status badge — «already done» — which is
  // the opposite of what it did. The whole row is the target now.
  if (!canComplete) return <div data-tour={tourId} className="py-3 first:pt-0 last:pb-0">{body}</div>;
  return (
    <button
      type="button"
      data-tour={tourId}
      onClick={() => onComplete(interval)}
      aria-label={t('dashboard.markDoneAria', { title: interval.title })}
      className="group block w-full py-3 text-left transition first:pt-0 last:pb-0 hover:bg-raised/40 active:bg-raised motion-reduce:active:bg-transparent"
    >
      {body}
    </button>
  );
}

export default function Dashboard() {
  const { t } = useTranslation();
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
  const completeInterval = useCarStore((s) => s.completeInterval);

  const navigate = useNavigate();
  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;

  const canEditCar = canDo(activeCar?.your_role, 'car:edit');
  const canAddEntries = canDo(activeCar?.your_role, 'log:create');
  const canCompleteIntervals = canDo(activeCar?.your_role, 'interval:complete');

  const [completingInterval, setCompletingInterval] = useState(null);
  const [toast, setToast] = useState('');

  const [refuelContext, setRefuelContext] = useState(null);
  const noRefuelsYet = refuelContext != null && refuelContext.last_refuel_odometer == null;

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
        <h2 className="font-display text-lg font-semibold text-fg">{t('dashboard.welcomeTitle')}</h2>
        <p className="text-sm text-mist">
          {t('dashboard.welcomeSubtitle')}
        </p>
        <Link
          to="/garage"
          className="mt-2 inline-flex items-center gap-1 rounded-xl bg-amber px-5 py-2.5 text-sm font-medium text-amber-ink transition-colors hover:bg-amber-deep"
        >
          {t('dashboard.addCar')}
          <ChevronRight className="h-4 w-4" />
        </Link>
      </Card>
    );
  }

  const fuel = analytics?.fuel;

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />
      <NotificationsBanner />

      <CompleteIntervalModal
        interval={completingInterval}
        car={activeCar}
        onComplete={completeInterval}
        onClose={() => setCompletingInterval(null)}
        onToast={setToast}
      />

      {activeCar && (
        <>
          {/* Odometer vertically centred against the (possibly three-line)
              name, not pinned to the top. */}
          <div className="flex items-center justify-between gap-2 px-1">
            <div className="min-w-0" data-tour="car-name">
              {/* The colour lives in `generation` after a comma («7 (BA5),
                  Urano Gray»); the dashboard shows the generation but not the
                  colour, so it is trimmed off here. */}
              <h1 className="font-display text-lg font-semibold leading-tight text-fg">
                <CopyCarName car={activeCar} onCopied={setToast}>
                  {activeCar.brand} {activeCar.model}
                  {activeCar.generation ? ` ${activeCar.generation.split(',')[0].trim()}` : ''}
                </CopyCarName>
              </h1>
              <p className="mt-0.5 text-xs text-mist">
                {activeCar.year}
                {activeCar.engine ? ` · ${activeCar.engine}` : ''} · {fuelKindLabel(activeCar.fuel_type)}
              </p>
            </div>
            <span className="flex flex-shrink-0 items-center gap-0.5 text-sm text-mist" data-tour="odometer">
              {formatKm(activeCar.current_odometer)}
              {canEditCar && (
                <button
                  type="button"
                  onClick={() => navigate(`/garage/${activeCar.id}/edit?focus=odometer`)}
                  aria-label={t('dashboard.editOdometerAria')}
                  className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-panel hover:text-fg"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
              )}
            </span>
          </div>
        </>
      )}

      {analyticsError && <ErrorMessage>{analyticsError}</ErrorMessage>}

      {analyticsLoading && !analytics ? (
        <Spinner />
      ) : (
        analytics && (
          <div className="grid grid-cols-3 gap-2.5" data-tour="stats">
            <StatCard
              icon={Wallet}
              label={t('dashboard.statThisMonth')}
              value={formatMoneyCompact(analytics.totals.this_month)}
            />
            <StatCard
              icon={Droplets}
              label={t('dashboard.statConsumption')}
              value={
                fuel?.avg_consumption_l_100km != null
                  ? fuel.avg_consumption_l_100km.toFixed(1)
                  : '—'
              }
            />
            <StatCard
              icon={Route}
              label={t('dashboard.statPer100km')}
              value={
                analytics.tco?.cost_per_km != null
                  ? formatMoney(Math.round(analytics.tco.cost_per_km * 100))
                  : '—'
              }
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
              {t('dashboard.addFirstRefuel')}
            </p>
            <ChevronRight className="h-4 w-4 flex-shrink-0 text-mist" />
          </Card>
        </Link>
      )}

      <Card data-tour="intervals">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="font-display text-sm font-semibold text-fg">{t('dashboard.intervalsTitle')}</h2>
          <Link
            to="/intervals"
            aria-label={t('dashboard.manageIntervalsAria')}
            className="rounded-lg p-1.5 text-mist transition-colors hover:bg-raised hover:text-amber"
          >
            <ArrowUpRight className="h-4 w-4" />
          </Link>
        </div>
        {intervalsError && <ErrorMessage className="my-2">{intervalsError}</ErrorMessage>}
        {intervalsLoading && intervals.length === 0 ? (
          <Spinner className="py-4" />
        ) : intervals.length === 0 ? (
          <p className="py-3 text-sm text-mist">
            {canDo(activeCar?.your_role, 'interval:manage')
              ? t('dashboard.noIntervalsManager')
              : t('dashboard.noIntervalsViewer')}
          </p>
        ) : (
          <div className="divide-y divide-edge">
            {intervals.map((interval, i) => (
              <IntervalRow
                key={interval.id}
                interval={interval}
                onComplete={setCompletingInterval}
                canComplete={canCompleteIntervals}
                tourId={i === 0 ? 'interval-row' : undefined}
              />
            ))}
          </div>
        )}
      </Card>

    </div>
  );
}
