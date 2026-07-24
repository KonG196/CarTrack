import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  ChevronRight,
  Droplets,
  FileDown,
  Loader2,
  PiggyBank,
  Sparkles,
  Wallet,
  Wrench,
} from 'lucide-react';

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts';
import { useTranslation, Trans } from 'react-i18next';
import { useCarStore } from '../store/carStore';
import { expenseCategoryLabel } from '../i18n/domain';
import { extractError } from '../api/client';
import { downloadCarReport } from '../api/reports';
import {
  formatMoney,
  formatMoneyCompact,
  formatKm,
  formatDate,
  monthLabel,
  formatConsumptionValue,
  formatVolume,
  consumptionUnitLabel,
  volumeUnitLabel,
  distanceUnitLabel,
} from '../utils/format';
import { consumptionFromL100, volumeFromLitres, costPerDistanceFromPerKm, isImperial } from '../units';
import { useUnitStore } from '../store/unitStore';
import { currentCurrencySymbol } from '../store/currencyStore';
import { expenseCategoryRows, shouldShowStations } from '../utils/analyticsBreakdown';
import {
  consumptionChartRows,
  consumptionKinds,
  fuelKindLabel,
  hasMixedKinds,
  priceChartKinds,
  priceChartRows,
  shouldShowPriceChart,
} from '../utils/fuelKind';
import { Button, Card, Spinner, ErrorMessage } from '../components/UI';
import TripCostCard from '../components/TripCostCard';

// Categorical chart palette — a colour system of its own, separate from the app's
// amber accent: here colour marks record type, not importance. Validated against
// the panel background (#121A26) for lightness banding, saturation floor,
// colourblind separation (worst adjacent pair ΔE 41.3 protan) and contrast >= 3:1.
const SERIES = [
  { key: 'refuel', color: '#3987e5' },
  { key: 'maintenance', color: '#199e70' },
  { key: 'repair', color: '#c98500' },
  { key: 'expense', color: '#9085e9' },
];

const FUEL_KIND_COLORS = {
  petrol: '#3987e5',
  lpg: '#199e70',
  diesel: '#c98500',
  electric: '#9085e9',
};

const SURFACE = '#121A26';
const GRID = '#1D2A3E';
const MUTED = '#93A1B8';

function ChartTooltip({ active, payload, label, valueFormatter }) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-xl border border-edge-soft bg-raised px-3 py-2 shadow-lg shadow-black/40">
      <p className="mb-1 text-xs font-medium text-fg">{label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} className="flex items-center gap-1.5 text-xs text-fg">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: entry.color || entry.stroke }}
          />
          {entry.name}: {valueFormatter(entry.value)}
        </p>
      ))}
    </div>
  );
}

function PriceTooltip({ active, payload, label }) {
  const { t } = useTranslation();
  const entries = (payload || []).filter((entry) => entry.value != null);
  if (!active || entries.length === 0) return null;
  return (
    <div className="rounded-xl border border-edge-soft bg-raised px-3 py-2 shadow-lg shadow-black/40">
      <p className="mb-1 text-xs font-medium text-fg">{label}</p>
      {entries.map((entry) => (
        <p key={entry.dataKey} className="flex items-center gap-1.5 text-xs text-fg">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: entry.color || entry.stroke }}
          />
          {entry.name}: {Number(entry.value).toFixed(2)} {t('analytics.unitUahPerL', { currency: currentCurrencySymbol(), unit: volumeUnitLabel() })}
          {entry.payload?.[`${entry.dataKey}__station`] && (
            <span className="text-mist">· {entry.payload[`${entry.dataKey}__station`]}</span>
          )}
        </p>
      ))}
    </div>
  );
}

// When a service is due: an interval falls due when EITHER its distance or its
// time runs out, so it can be overdue on one axis while the other still has
// slack. Once overdue, surface only what is overdue — showing «через 10 873 км»
// (or a negative «через -1 000 км») next to a past due date read as a glitch.
function upcomingWhen(item, t) {
  const kmOverdue = item.km_left != null && item.km_left < 0;
  const daysOverdue = item.days_left != null && item.days_left < 0;
  if (kmOverdue || daysOverdue) {
    const bits = [];
    if (daysOverdue) bits.push(t('analytics.daysAgo', { n: Math.abs(item.days_left) }));
    if (kmOverdue) bits.push(t('analytics.overdueByKm', { km: formatKm(Math.abs(item.km_left)) }));
    return bits.join(' · ');
  }
  const bits = [];
  if (item.predicted_due_date) bits.push(formatDate(item.predicted_due_date));
  if (item.km_left != null) bits.push(t('analytics.inKm', { km: formatKm(item.km_left) }));
  return bits.join(' · ') || '—';
}

function ForecastSection({ forecast }) {
  const { t } = useTranslation();
  const upcoming = forecast?.upcoming || [];

  return (
    <div className="space-y-2.5">

      <div className="grid grid-cols-3 gap-2.5">
        <Card className="p-3">
          <p className="text-xs text-mist">{t('analytics.avgSpendPerMonth')}</p>
          <p className="mt-1 font-mono text-sm font-semibold tabular-nums text-fg">
            {formatMoney(forecast?.avg_monthly_spend)}
          </p>
        </Card>
        <Card className="p-3">
          <p className="text-xs text-mist">{t('analytics.projectedThisMonth')}</p>
          <p className="mt-1 font-mono text-sm font-semibold tabular-nums text-fg">
            {formatMoney(forecast?.projected_month_total)}
          </p>
        </Card>
        <Card className="p-3">
          <p className="text-xs text-mist">{t('analytics.distancePerMonth')}</p>
          <p className="mt-1 font-mono text-sm font-semibold tabular-nums text-fg">
            {formatKm(forecast?.monthly_km_rate)}
          </p>
        </Card>
      </div>

      <Card>
        <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold text-fg">
          <Wrench className="h-4 w-4 text-amber" />
          {t('analytics.upcomingMaintenance')}
        </h3>
        {upcoming.length === 0 ? (
          <p className="py-3 text-sm text-mist">
            {t('analytics.noUpcoming')}
          </p>
        ) : (
          <div className="divide-y divide-edge">
            {upcoming.map((item) => (
              <div
                key={item.interval_id}
                className="flex items-start justify-between gap-3 py-2.5"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-fg">{item.title}</p>
                  <p className="mt-0.5 text-xs text-mist">{upcomingWhen(item, t)}</p>
                </div>
                {item.estimated_cost != null && (
                  <div className="flex-shrink-0 text-right">
                    <p className="font-mono text-sm font-medium tabular-nums text-fg">
                      ~{formatMoney(item.estimated_cost)}
                    </p>
                    {/* «Ваша ціна» is a fact from this car's bills; «по ринку»
                        is a guess that has never seen the car. Labelling both
                        «орієнтовно» would hide which is which. */}
                    <p className="text-[10px] text-mist/70">
                      {item.estimated_cost_source === 'history'
                        ? t('analytics.costFromHistory')
                        : t('analytics.costFromMarket')}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

const TABS = [
  { key: 'costs', icon: Wallet },
  { key: 'fuel', icon: Droplets },
  { key: 'tco', icon: PiggyBank },
];
const TAB_KEYS = TABS.map((t) => t.key);

function TabBar({ tab, onTab }) {
  const { t } = useTranslation();
  return (
    <div className="grid grid-cols-3 gap-1 rounded-2xl border border-edge bg-panel p-1">
      {TABS.map(({ key, icon: Icon }) => (
        <button
          key={key}
          type="button"
          onClick={() => onTab(key)}
          aria-pressed={tab === key}
          className={`flex items-center justify-center gap-1.5 rounded-xl px-1 py-2 text-xs font-semibold transition-colors ${
            tab === key ? 'bg-amber text-amber-ink' : 'text-mist hover:text-fg'
          }`}
        >
          <Icon className="h-4 w-4 flex-shrink-0" />
          {t(`analytics.tab.${key}`)}
        </button>
      ))}
    </div>
  );
}

// A big-number tile for the Efficiency tab.
function TcoTile({ label, value, unit, hint }) {
  return (
    <Card className="min-w-0 p-4">
      <p className="text-xs text-mist">{label}</p>
      <p className="mt-1.5 break-words font-mono text-2xl font-semibold tabular-nums text-fg">
        {value}
        {unit ? <span className="ml-1 text-base font-normal text-mist">{unit}</span> : null}
      </p>
      {hint ? <p className="mt-1 text-[11px] leading-snug text-mist/70">{hint}</p> : null}
    </Card>
  );
}

const LITRES_PER_GAL = 3.785411784;

export default function Analytics() {
  const { t } = useTranslation();
  const units = useUnitStore((s) => s.units);
  const imperial = isImperial(units);
  const compactHryvnia = (v) =>
    Math.abs(v) >= 1000 ? `${Math.round(v / 1000)}${t('analytics.thousandsSuffix')}` : String(v);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const cars = useCarStore((s) => s.cars);
  const carsLoaded = useCarStore((s) => s.carsLoaded);
  const analytics = useCarStore((s) => s.analytics);
  const analyticsLoading = useCarStore((s) => s.analyticsLoading);
  const analyticsError = useCarStore((s) => s.analyticsError);
  const fetchAnalytics = useCarStore((s) => s.fetchAnalytics);

  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;
  const activeCarName = activeCar?.model || null;

  // The active tab lives in the URL (?tab=) so the product tour can drive it via
  // its normal path navigation.
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');
  const tab = TAB_KEYS.includes(tabParam) ? tabParam : 'costs';
  const setTab = (key) =>
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set('tab', key);
        return next;
      },
      { replace: true },
    );

  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState('');

  useEffect(() => {
    if (activeCarId) {
      fetchAnalytics().catch(() => {});
    }
  }, [activeCarId, fetchAnalytics]);

  if (carsLoaded && !activeCarId) {
    return (
      <Card className="rise-in mt-8 p-8 text-center">
        <p className="text-sm text-mist">{t('analytics.noActiveCar')}</p>
      </Card>
    );
  }

  const handleDownloadReport = async () => {
    if (!activeCarId || reportLoading) return;
    setReportError('');
    setReportLoading(true);
    try {
      await downloadCarReport(activeCarId);
    } catch (err) {
      setReportError(extractError(err, t('analytics.reportError')));
    } finally {
      setReportLoading(false);
    }
  };

  const header = (
    <div className="flex items-center justify-between px-1">
      <h1 className="font-display text-lg font-semibold text-fg">{t('analytics.title')}</h1>
      <Button
        variant="secondary"
        data-tour="analytics-report"
        onClick={handleDownloadReport}
        disabled={reportLoading}
        className="px-3 py-1.5"
      >
        {reportLoading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <FileDown className="h-4 w-4" />
        )}
        {reportLoading ? t('analytics.generating') : t('analytics.reportPdf')}
      </Button>
    </div>
  );

  if (analyticsError) {
    return (
      <div className="stagger space-y-4">
        {header}
        {reportError && <ErrorMessage>{reportError}</ErrorMessage>}
        <ErrorMessage>{analyticsError}</ErrorMessage>
      </div>
    );
  }

  if (analyticsLoading || !analytics) {
    return (
      <div className="stagger space-y-4">
        {header}
        <Spinner />
      </div>
    );
  }

  const monthly = (analytics.monthly || []).map((m) => ({
    ...m,
    label: monthLabel(m.month),
  }));
  const hasSpending = monthly.some((m) => m.total > 0);

  const byKind = analytics.fuel?.by_kind || {};
  const mixedKinds = hasMixedKinds(byKind);

  // Chart values are stored metric; convert each numeric series to the display
  // system so the plotted shape, axes and tooltips all read in the user's units.
  // Consumption→mpg is an INVERSE, so an imperial consumption chart legitimately
  // flips (a thirsty month is a LOW mpg point).
  const convConsumption = (v) => (v == null ? v : consumptionFromL100(v, units));
  const convPricePerVol = (v) =>
    v == null ? v : imperial ? v * LITRES_PER_GAL : v;
  const convertRowSeries = (row, keys, fn) => {
    const next = { ...row };
    for (const k of keys) if (typeof next[k] === 'number') next[k] = fn(next[k]);
    return next;
  };

  const fuelKinds = consumptionKinds(byKind);
  const consumptionSeriesKeys = ['consumption_l_100km', ...fuelKinds];
  const fuelHistory = (mixedKinds ? consumptionChartRows(byKind) : analytics.fuel?.history || [])
    .map((h) => convertRowSeries(h, consumptionSeriesKeys, convConsumption))
    .map((h) => ({ ...h, label: formatDate(h.date) }));
  const avgConsumption = convConsumption(analytics.fuel?.avg_consumption_l_100km ?? null);

  const priceHistory = analytics.price_history || [];
  const showPriceChart = shouldShowPriceChart(priceHistory);
  const priceKinds = priceChartKinds(priceHistory);
  const priceRows = priceChartRows(priceHistory)
    .map((row) => convertRowSeries(row, priceKinds, convPricePerVol))
    .map((row) => ({ ...row, label: formatDate(row.date) }));

  const expenseRows = expenseCategoryRows(analytics.expense_by_category);
  const stations = analytics.stations || [];
  const showStations = shouldShowStations(stations);

  return (
    <div className="stagger space-y-4">
      {header}
      {reportError && <ErrorMessage>{reportError}</ErrorMessage>}

      <Link to="/year" className="block">
        <Card className="flex items-center gap-3 border-amber/40 p-3 transition active:scale-[0.99] motion-reduce:active:scale-100">
          <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-amber/15">
            <Sparkles className="h-4 w-4 text-amber" />
          </span>
          <p className="flex-1 text-sm font-medium text-fg">{t('analytics.yourYear')}</p>
          <ChevronRight className="h-4 w-4 flex-shrink-0 text-mist" />
        </Card>
      </Link>

      <TabBar tab={tab} onTab={setTab} />

      {tab === 'costs' && (
        <>
      <div data-tour="analytics-forecast">
        <ForecastSection forecast={analytics.forecast} />
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        <Card className="p-3.5">
          <p className="text-xs text-mist">{t('analytics.totalSpent')}</p>
          <p className="mt-1 font-mono text-lg font-semibold tabular-nums text-fg">
            {formatMoney(analytics.totals.all_time)}
          </p>
        </Card>
        <Card className="p-3.5">
          <p className="text-xs text-mist">{t('analytics.thisMonth')}</p>
          <p className="mt-1 font-mono text-lg font-semibold tabular-nums text-fg">
            {formatMoney(analytics.totals.this_month)}
          </p>
        </Card>
      </div>

      <Card className="p-3.5">
        <p className="mb-2 text-xs text-mist">{t('analytics.byCategoryAllTime')}</p>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
          {SERIES.map(({ key, color }) => (
            <div key={key} className="flex min-w-0 items-center justify-between gap-2 text-sm">
              <span className="flex min-w-0 items-center gap-1.5 text-mist">
                <span
                  className="h-2 w-2 flex-shrink-0 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="truncate">{t(`analytics.series.${key}`)}</span>
              </span>
              <span className="flex-shrink-0 whitespace-nowrap font-mono font-medium tabular-nums text-fg">
                {formatMoneyCompact(analytics.totals.by_type?.[key] ?? 0)}
              </span>
            </div>
          ))}
        </div>
        {expenseRows.length > 0 && (
          <div className="mt-3 border-t border-edge pt-3">
            <p className="mb-2 text-xs text-mist">
              {t('analytics.otherByCategory')}
            </p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              {expenseRows.map(({ name, total }) => (
                <div key={name} className="flex min-w-0 items-center justify-between gap-2 text-sm">
                  <span className="truncate text-mist">{expenseCategoryLabel(name)}</span>
                  <span className="flex-shrink-0 whitespace-nowrap font-mono font-medium tabular-nums text-fg">
                    {formatMoneyCompact(total)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      <Card data-tour="analytics-charts">
        <h2 className="mb-3 font-display text-sm font-semibold text-fg">{t('analytics.monthlySpending', { currency: currentCurrencySymbol() })}</h2>
        {!hasSpending ? (
          <p className="py-6 text-center text-sm text-mist">
            {t('analytics.noSpendingYet')}
          </p>
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthly} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke={GRID} strokeWidth={1} />
                <XAxis
                  dataKey="label"
                  tick={{ fill: MUTED, fontSize: 10 }}
                  axisLine={{ stroke: GRID }}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fill: MUTED, fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={compactHryvnia}
                  width={44}
                />
                <Tooltip
                  cursor={{ fill: 'rgba(148, 163, 184, 0.08)' }}
                  content={<ChartTooltip valueFormatter={formatMoney} />}
                />
                <Legend
                  iconType="circle"
                  iconSize={8}
                  wrapperStyle={{ fontSize: 11, color: MUTED, paddingTop: 6 }}
                />
                {SERIES.map(({ key, color }, idx) => (
                  <Bar
                    key={key}
                    dataKey={key}
                    name={t(`analytics.series.${key}`)}
                    stackId="spend"
                    fill={color}
                    stroke={SURFACE}
                    strokeWidth={1}
                    maxBarSize={28}
                    radius={idx === SERIES.length - 1 ? [4, 4, 0, 0] : 0}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
        </>
      )}

      {tab === 'fuel' && (
        <>
      {analytics.fuel?.spike && (
        <Card>
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber" />
            <div className="min-w-0 text-sm">
              <p className="font-medium text-amber">
                {t('analytics.fuelSpikeTitle', {
                  fuel: t(`analytics.fuelWord.${analytics.fuel.spike.fuel_kind}`, {
                    defaultValue: t('analytics.fuelWord.fallback'),
                  }),
                  pct: analytics.fuel.spike.pct_over,
                })}
              </p>
              <p className="mt-0.5 text-mist">
                {t('analytics.fuelSpikeBody', {
                  consumption: formatConsumptionValue(analytics.fuel.spike.consumption_l_100km),
                  baseline: formatConsumptionValue(analytics.fuel.spike.baseline_l_100km),
                  unit: consumptionUnitLabel(),
                  date: formatDate(analytics.fuel.spike.date),
                })}
              </p>
            </div>
          </div>
        </Card>
      )}
      <Card>
        <h2 className="mb-3 font-display text-sm font-semibold text-fg">{t('analytics.fuelConsumptionTitle', { unit: consumptionUnitLabel() })}</h2>
        {fuelHistory.length === 0 ? (
          <p className="py-6 text-center text-sm text-mist">
            {t('analytics.notEnoughData')}
          </p>
        ) : (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={fuelHistory} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke={GRID} strokeWidth={1} />
                <XAxis
                  dataKey="label"
                  tick={{ fill: MUTED, fontSize: 10 }}
                  axisLine={{ stroke: GRID }}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fill: MUTED, fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  width={44}
                  domain={['auto', 'auto']}
                  tickFormatter={(v) => v.toFixed(1)}
                />
                <Tooltip
                  content={
                    <ChartTooltip
                      valueFormatter={(v) => `${Number(v).toFixed(2)} ${consumptionUnitLabel()}`}
                    />
                  }
                />
                {avgConsumption != null && !mixedKinds && (
                  <ReferenceLine
                    y={avgConsumption}
                    stroke={MUTED}
                    strokeDasharray="4 4"
                    label={{
                      value: t('analytics.avgReferenceLabel', { value: avgConsumption.toFixed(1) }),
                      fill: MUTED,
                      fontSize: 10,
                      position: 'insideTopRight',
                    }}
                  />
                )}
                {mixedKinds && (
                  <Legend
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ fontSize: 11, color: MUTED, paddingTop: 6 }}
                  />
                )}
                {mixedKinds ? (
                  fuelKinds.map((kind) => {
                    const color = FUEL_KIND_COLORS[kind] || MUTED;
                    return (
                      <Line
                        key={kind}
                        type="monotone"
                        dataKey={kind}
                        name={fuelKindLabel(kind)}
                        stroke={color}
                        strokeWidth={2}
                        connectNulls
                        dot={{ r: 3, fill: color, stroke: SURFACE, strokeWidth: 2 }}
                        activeDot={{ r: 5, fill: color, stroke: SURFACE, strokeWidth: 2 }}
                      />
                    );
                  })
                ) : (
                  <Line
                    type="monotone"
                    dataKey="consumption_l_100km"
                    name={t('analytics.consumptionLine')}
                    stroke="#3987e5"
                    strokeWidth={2}
                    dot={{ r: 3, fill: '#3987e5', stroke: SURFACE, strokeWidth: 2 }}
                    activeDot={{ r: 5, fill: '#3987e5', stroke: SURFACE, strokeWidth: 2 }}
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        {mixedKinds ? (
          <div className="mt-2 divide-y divide-edge border-t border-edge">
            {fuelKinds.map((kind) => (
              <div key={kind} className="flex items-center justify-between gap-3 py-2">
                <span className="flex items-center gap-1.5 text-xs text-mist">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: FUEL_KIND_COLORS[kind] || MUTED }}
                  />
                  {fuelKindLabel(kind)}
                </span>
                <span className="font-mono text-xs tabular-nums text-fg">
                  {byKind[kind].avg_consumption_l_100km != null
                    ? `${formatConsumptionValue(byKind[kind].avg_consumption_l_100km)} ${consumptionUnitLabel()}`
                    : '—'}
                  <span className="text-mist/70">
                    {' '}
                    · {Math.round(volumeFromLitres(byKind[kind].total_liters, units))} {volumeUnitLabel()} ·{' '}
                    {formatMoney(byKind[kind].total_cost)}
                  </span>
                </span>
              </div>
            ))}
          </div>
        ) : (
          analytics.fuel?.last_consumption_l_100km != null && (
            <p className="mt-2 text-xs text-mist">
              {t('analytics.lastConsumption', {
                value: formatConsumptionValue(analytics.fuel.last_consumption_l_100km),
                unit: consumptionUnitLabel(),
              })}
            </p>
          )
        )}
      </Card>

      {showPriceChart && (
        <Card>
          <h2 className="mb-3 font-display text-sm font-semibold text-fg">{t('analytics.pricePerLiterTitle', { currency: currentCurrencySymbol(), unit: volumeUnitLabel() })}</h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={priceRows} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke={GRID} strokeWidth={1} />
                <XAxis
                  dataKey="label"
                  tick={{ fill: MUTED, fontSize: 10 }}
                  axisLine={{ stroke: GRID }}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fill: MUTED, fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  width={44}
                  domain={['auto', 'auto']}
                  tickFormatter={(v) => v.toFixed(0)}
                />
                <Tooltip content={<PriceTooltip />} />
                {priceKinds.length > 1 && (
                  <Legend
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ fontSize: 11, color: MUTED, paddingTop: 6 }}
                  />
                )}
                {priceKinds.map((kind) => {
                  const color = FUEL_KIND_COLORS[kind] || MUTED;
                  return (
                    <Line
                      key={kind}
                      type="monotone"
                      dataKey={kind}
                      name={fuelKindLabel(kind)}
                      stroke={color}
                      strokeWidth={2}
                      connectNulls
                      dot={{ r: 3, fill: color, stroke: SURFACE, strokeWidth: 2 }}
                      activeDot={{ r: 5, fill: color, stroke: SURFACE, strokeWidth: 2 }}
                    />
                  );
                })}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {showStations && (
        <Card>
          <h2 className="mb-1 font-display text-sm font-semibold text-fg">{t('analytics.myStations')}</h2>
          <p className="mb-2 text-xs text-mist">
            {t('analytics.stationsHint')}
          </p>
          <div className="divide-y divide-edge">
            {stations.map((station) => (
              <div
                key={station.name}
                className="flex items-start justify-between gap-3 py-2.5"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-fg">{station.name}</p>
                  <p className="mt-0.5 text-xs text-mist">
                    {station.refuels} {t('analytics.unitRefuels')} · {volumeFromLitres(station.total_liters, units).toFixed(1)}{' '}
                    {volumeUnitLabel()}
                    {station.avg_price_per_liter != null && (
                      <span className="text-mist/70">
                        {' '}
                        · {(imperial ? station.avg_price_per_liter * LITRES_PER_GAL : station.avg_price_per_liter).toFixed(2)} {t('analytics.unitUahPerL', { currency: currentCurrencySymbol(), unit: volumeUnitLabel() })}
                      </span>
                    )}
                  </p>
                </div>
                <div className="flex-shrink-0 text-right">
                  <p className="font-mono text-sm font-medium tabular-nums text-fg">
                    {formatMoney(station.total_cost)}
                  </p>
                  <p className="text-[10px] text-mist/70">
                    {station.avg_consumption_l_100km != null
                      ? `${formatConsumptionValue(station.avg_consumption_l_100km)} ${consumptionUnitLabel()}`
                      : '—'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div data-tour="analytics-trip">
        <TripCostCard analytics={analytics} carName={activeCarName} />
      </div>
        </>
      )}

      {tab === 'tco' && (
        <>
          {analytics.lpg_savings && (
            <Card className="flex items-start gap-3 border-ok/40 bg-ok/5">
              <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-ok/15">
                <PiggyBank className="h-5 w-5 text-ok" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-fg">
                  {t('analytics.lpgSaved')}{' '}
                  <span className="font-semibold text-ok">
                    {formatMoney(analytics.lpg_savings.saved_total)}
                  </span>
                </p>
                <p className="mt-0.5 text-xs text-mist">
                  {t('analytics.lpgSavingsDetail', {
                    currency: currentCurrencySymbol(),
                    perKm: analytics.lpg_savings.saved_per_km.toFixed(2),
                    distance: formatKm(analytics.lpg_savings.gas_distance_km),
                  })}
                </p>
              </div>
            </Card>
          )}
          <div className="grid grid-cols-2 gap-2.5">
            <TcoTile
              label={t('analytics.tcoCostPerKm', {
                currency: currentCurrencySymbol(),
                unit: distanceUnitLabel(),
              })}
              value={
                analytics.tco?.cost_per_km != null
                  ? formatMoney(costPerDistanceFromPerKm(analytics.tco.cost_per_km, units))
                  : '—'
              }
              hint={t('analytics.tcoCostPerKmHint')}
            />
            <TcoTile
              label={t('analytics.tcoCostPerDay', { currency: currentCurrencySymbol() })}
              value={
                analytics.tco?.cost_per_day != null
                  ? formatMoneyCompact(analytics.tco.cost_per_day)
                  : '—'
              }
              hint={t('analytics.tcoCostPerDayHint')}
            />
            <TcoTile
              label={t('analytics.tcoConsumption')}
              value={
                analytics.fuel?.avg_consumption_l_100km != null
                  ? formatConsumptionValue(analytics.fuel.avg_consumption_l_100km)
                  : '—'
              }
              unit={consumptionUnitLabel()}
            />
            <TcoTile
              label={t('analytics.tcoSpendPerMonth')}
              value={
                analytics.forecast?.avg_monthly_spend != null
                  ? formatMoneyCompact(analytics.forecast.avg_monthly_spend)
                  : '—'
              }
            />
          </div>
          <Card className="p-4">
            <p className="text-xs leading-relaxed text-mist">
              <Trans
                i18nKey="analytics.tcoExplainer"
                components={{ b: <span className="text-fg" /> }}
                values={{
                  currency: currentCurrencySymbol(),
                  distance:
                    analytics.tco?.distance_km != null
                      ? ` (${formatKm(analytics.tco.distance_km)})`
                      : '',
                }}
              />
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
