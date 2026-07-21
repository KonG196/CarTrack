import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Droplets, FileDown, Loader2, PiggyBank, Wallet, Wrench } from 'lucide-react';
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
import { useCarStore } from '../store/carStore';
import { extractError } from '../api/client';
import { downloadCarReport } from '../api/reports';
import { formatMoney, formatMoneyCompact, formatKm, formatDate, monthLabel } from '../utils/format';
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
  { key: 'refuel', label: 'Заправки', color: '#3987e5' },
  { key: 'maintenance', label: 'ТО', color: '#199e70' },
  { key: 'repair', label: 'Ремонт', color: '#c98500' },
  { key: 'expense', label: 'Інше', color: '#9085e9' },
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
          {entry.name}: {Number(entry.value).toFixed(2)} ₴/л
          {entry.payload?.[`${entry.dataKey}__station`] && (
            <span className="text-mist">· {entry.payload[`${entry.dataKey}__station`]}</span>
          )}
        </p>
      ))}
    </div>
  );
}

function compactHryvnia(v) {
  if (Math.abs(v) >= 1000) return `${Math.round(v / 1000)}к`;
  return String(v);
}

// Distance to a service: «через 400 км» when it is still ahead, «прострочено на
// 1 000 км» once it is behind. Rendering a negative «через -1 000 км» read as a
// glitch.
function kmLeftLabel(km) {
  if (km == null) return '—';
  return km >= 0 ? `через ${formatKm(km)}` : `прострочено на ${formatKm(Math.abs(km))}`;
}

function ForecastSection({ forecast }) {
  const upcoming = forecast?.upcoming || [];

  return (
    <div className="space-y-2.5">

      <div className="grid grid-cols-3 gap-2.5">
        <Card className="p-3">
          <p className="text-xs text-mist">Середні витрати/міс</p>
          <p className="mt-1 font-mono text-sm font-semibold tabular-nums text-fg">
            {formatMoney(forecast?.avg_monthly_spend)}
          </p>
        </Card>
        <Card className="p-3">
          <p className="text-xs text-mist">Прогноз на цей місяць</p>
          <p className="mt-1 font-mono text-sm font-semibold tabular-nums text-fg">
            {formatMoney(forecast?.projected_month_total)}
          </p>
        </Card>
        <Card className="p-3">
          <p className="text-xs text-mist">Пробіг км/міс</p>
          <p className="mt-1 font-mono text-sm font-semibold tabular-nums text-fg">
            {formatKm(forecast?.monthly_km_rate)}
          </p>
        </Card>
      </div>

      <Card>
        <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold text-fg">
          <Wrench className="h-4 w-4 text-amber" />
          Найближчі ТО
        </h3>
        {upcoming.length === 0 ? (
          <p className="py-3 text-sm text-mist">
            У найближчі 90 днів планових робіт не передбачається.
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
                  <p className="mt-0.5 text-xs text-mist">
                    {item.predicted_due_date
                      ? formatDate(item.predicted_due_date)
                      : item.km_left != null
                        ? kmLeftLabel(item.km_left)
                        : '—'}
                    {item.predicted_due_date && item.km_left != null && (
                      <span className="text-mist/70"> · {kmLeftLabel(item.km_left)}</span>
                    )}
                  </p>
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
                      {item.estimated_cost_source === 'history' ? 'ваша ціна' : 'по ринку'}
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
  { key: 'costs', label: 'Витрати', icon: Wallet },
  { key: 'fuel', label: 'Паливо', icon: Droplets },
  { key: 'tco', label: 'Ефективність', icon: PiggyBank },
];
const TAB_KEYS = TABS.map((t) => t.key);

function TabBar({ tab, onTab }) {
  return (
    <div className="grid grid-cols-3 gap-1 rounded-2xl border border-edge bg-panel p-1">
      {TABS.map(({ key, label, icon: Icon }) => (
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
          {label}
        </button>
      ))}
    </div>
  );
}

// A big-number tile for the Efficiency tab.
function TcoTile({ label, value, unit, hint }) {
  return (
    <Card className="p-4">
      <p className="text-xs text-mist">{label}</p>
      <p className="mt-1.5 font-mono text-2xl font-semibold tabular-nums text-fg">
        {value}
        {unit ? <span className="ml-1 text-base font-normal text-mist">{unit}</span> : null}
      </p>
      {hint ? <p className="mt-1 text-[11px] leading-snug text-mist/70">{hint}</p> : null}
    </Card>
  );
}

export default function Analytics() {
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
        <p className="text-sm text-mist">Додайте авто, щоб побачити аналітику.</p>
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
      setReportError(extractError(err, 'Не вдалося сформувати PDF-звіт'));
    } finally {
      setReportLoading(false);
    }
  };

  const header = (
    <div className="flex items-center justify-between px-1">
      <h1 className="font-display text-lg font-semibold text-fg">Аналітика</h1>
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
        {reportLoading ? 'Формування…' : 'Звіт PDF'}
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

  const fuelHistory = (
    mixedKinds ? consumptionChartRows(byKind) : analytics.fuel?.history || []
  ).map((h) => ({ ...h, label: formatDate(h.date) }));
  const fuelKinds = consumptionKinds(byKind);
  const avgConsumption = analytics.fuel?.avg_consumption_l_100km;

  const priceHistory = analytics.price_history || [];
  const showPriceChart = shouldShowPriceChart(priceHistory);
  const priceRows = priceChartRows(priceHistory).map((row) => ({
    ...row,
    label: formatDate(row.date),
  }));
  const priceKinds = priceChartKinds(priceHistory);

  const expenseRows = expenseCategoryRows(analytics.expense_by_category);
  const stations = analytics.stations || [];
  const showStations = shouldShowStations(stations);

  return (
    <div className="stagger space-y-4">
      {header}
      {reportError && <ErrorMessage>{reportError}</ErrorMessage>}

      <TabBar tab={tab} onTab={setTab} />

      {tab === 'costs' && (
        <>
      <div data-tour="analytics-forecast">
        <ForecastSection forecast={analytics.forecast} />
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        <Card className="p-3.5">
          <p className="text-xs text-mist">Всього витрачено</p>
          <p className="mt-1 font-mono text-lg font-semibold tabular-nums text-fg">
            {formatMoney(analytics.totals.all_time)}
          </p>
        </Card>
        <Card className="p-3.5">
          <p className="text-xs text-mist">Цей місяць</p>
          <p className="mt-1 font-mono text-lg font-semibold tabular-nums text-fg">
            {formatMoney(analytics.totals.this_month)}
          </p>
        </Card>
      </div>

      <Card className="p-3.5">
        <p className="mb-2 text-xs text-mist">За категоріями (весь час)</p>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
          {SERIES.map(({ key, label, color }) => (
            <div key={key} className="flex min-w-0 items-center justify-between gap-2 text-sm">
              <span className="flex min-w-0 items-center gap-1.5 text-mist">
                <span
                  className="h-2 w-2 flex-shrink-0 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="truncate">{label}</span>
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
              «Інше» за категоріями
            </p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              {expenseRows.map(({ name, total }) => (
                <div key={name} className="flex min-w-0 items-center justify-between gap-2 text-sm">
                  <span className="truncate text-mist">{name}</span>
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
        <h2 className="mb-3 font-display text-sm font-semibold text-fg">Витрати за місяцями, ₴</h2>
        {!hasSpending ? (
          <p className="py-6 text-center text-sm text-mist">
            Ще немає витрат — додайте записи в журнал.
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
                {SERIES.map(({ key, label, color }, idx) => (
                  <Bar
                    key={key}
                    dataKey={key}
                    name={label}
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
      <Card>
        <h2 className="mb-3 font-display text-sm font-semibold text-fg">Витрата пального, л/100 км</h2>
        {fuelHistory.length === 0 ? (
          <p className="py-6 text-center text-sm text-mist">
            Замало даних. Додайте щонайменше дві заправки «до повного», щоб побачити витрату.
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
                    <ChartTooltip valueFormatter={(v) => `${Number(v).toFixed(2)} л/100 км`} />
                  }
                />
                {avgConsumption != null && !mixedKinds && (
                  <ReferenceLine
                    y={avgConsumption}
                    stroke={MUTED}
                    strokeDasharray="4 4"
                    label={{
                      value: `середнє ${avgConsumption.toFixed(1)}`,
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
                    name="Витрата"
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
                    ? `${byKind[kind].avg_consumption_l_100km.toFixed(2)} л/100 км`
                    : '—'}
                  <span className="text-mist/70">
                    {' '}
                    · {byKind[kind].total_liters.toFixed(0)} л ·{' '}
                    {formatMoney(byKind[kind].total_cost)}
                  </span>
                </span>
              </div>
            ))}
          </div>
        ) : (
          analytics.fuel?.last_consumption_l_100km != null && (
            <p className="mt-2 text-xs text-mist">
              Остання виміряна витрата: {analytics.fuel.last_consumption_l_100km.toFixed(2)} л/100 км
            </p>
          )
        )}
      </Card>

      {showPriceChart && (
        <Card>
          <h2 className="mb-3 font-display text-sm font-semibold text-fg">Ціна за літр, ₴</h2>
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
          <h2 className="mb-1 font-display text-sm font-semibold text-fg">Мої АЗС</h2>
          <p className="mb-2 text-xs text-mist">
            Витрата рахується по відрізках, що починаються на цій АЗС.
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
                    {station.refuels} запр. · {station.total_liters.toFixed(1)} л
                    {station.avg_price_per_liter != null && (
                      <span className="text-mist/70">
                        {' '}
                        · {station.avg_price_per_liter.toFixed(2)} ₴/л
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
                      ? `${station.avg_consumption_l_100km.toFixed(1)} л/100 км`
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
                  Завдяки ГБО ви зберегли{' '}
                  <span className="font-semibold text-ok">
                    {formatMoney(analytics.lpg_savings.saved_total)}
                  </span>
                </p>
                <p className="mt-0.5 text-xs text-mist">
                  Чиста економія {analytics.lpg_savings.saved_per_km.toFixed(2)} ₴ на кожному
                  кілометрі · {formatKm(analytics.lpg_savings.gas_distance_km)} на газу
                </p>
              </div>
            </Card>
          )}
          <div className="grid grid-cols-2 gap-2.5">
            <TcoTile
              label="Вартість, ₴/км"
              value={
                analytics.tco?.cost_per_km != null ? analytics.tco.cost_per_km.toFixed(2) : '—'
              }
              unit="₴"
              hint="Усі витрати на пробіг"
            />
            <TcoTile
              label="Вартість, ₴/день"
              value={
                analytics.tco?.cost_per_day != null
                  ? formatMoney(analytics.tco.cost_per_day)
                  : '—'
              }
              hint="Усі витрати на дні володіння"
            />
            <TcoTile
              label="Розхід"
              value={
                analytics.fuel?.avg_consumption_l_100km != null
                  ? analytics.fuel.avg_consumption_l_100km.toFixed(1)
                  : '—'
              }
              unit="л/100 км"
            />
            <TcoTile
              label="Витрати / місяць"
              value={
                analytics.forecast?.avg_monthly_spend != null
                  ? formatMoney(analytics.forecast.avg_monthly_spend)
                  : '—'
              }
            />
          </div>
          <Card className="p-4">
            <p className="text-xs leading-relaxed text-mist">
              ₴/км і ₴/день рахуються з <span className="text-fg">усіх</span> витрат — пальне, ТО,
              ремонти, інше — поділених на пройдений пробіг
              {analytics.tco?.distance_km != null ? ` (${formatKm(analytics.tco.distance_km)})` : ''}{' '}
              і дні володіння. Це чесна вартість, а не лише пальне.
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
