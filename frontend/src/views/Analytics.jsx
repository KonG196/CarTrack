import { useEffect } from 'react';
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
import { formatMoney, formatDate, monthLabel } from '../utils/format';
import { Card, Spinner, ErrorMessage } from '../components/UI';

// Categorical palette validated for the slate-900 surface (dataviz skill,
// scripts/validate_palette.js: CVD worst adjacent dE 41.3, contrast >= 3:1)
const SERIES = [
  { key: 'refuel', label: 'Заправки', color: '#3987e5' },
  { key: 'maintenance', label: 'ТО', color: '#199e70' },
  { key: 'repair', label: 'Ремонт', color: '#c98500' },
  { key: 'expense', label: 'Інше', color: '#9085e9' },
];

const SURFACE = '#0f172a'; // slate-900 card surface
const GRID = '#1e293b'; // hairline gridline
const MUTED = '#64748b'; // axis / tick ink

function ChartTooltip({ active, payload, label, valueFormatter }) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 shadow-lg shadow-black/40">
      <p className="mb-1 text-xs font-medium text-slate-300">{label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} className="flex items-center gap-1.5 text-xs text-slate-200">
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

function compactHryvnia(v) {
  if (Math.abs(v) >= 1000) return `${Math.round(v / 1000)}к`;
  return String(v);
}

export default function Analytics() {
  const activeCarId = useCarStore((s) => s.activeCarId);
  const carsLoaded = useCarStore((s) => s.carsLoaded);
  const analytics = useCarStore((s) => s.analytics);
  const analyticsLoading = useCarStore((s) => s.analyticsLoading);
  const analyticsError = useCarStore((s) => s.analyticsError);
  const fetchAnalytics = useCarStore((s) => s.fetchAnalytics);

  useEffect(() => {
    if (activeCarId) {
      fetchAnalytics().catch(() => {});
    }
  }, [activeCarId, fetchAnalytics]);

  if (carsLoaded && !activeCarId) {
    return (
      <Card className="mt-8 p-8 text-center">
        <p className="text-sm text-slate-400">Додайте авто, щоб побачити аналітику.</p>
      </Card>
    );
  }

  if (analyticsError) return <ErrorMessage>{analyticsError}</ErrorMessage>;
  if (analyticsLoading || !analytics) return <Spinner />;

  const monthly = (analytics.monthly || []).map((m) => ({
    ...m,
    label: monthLabel(m.month),
  }));
  const hasSpending = monthly.some((m) => m.total > 0);

  const fuelHistory = (analytics.fuel?.history || []).map((h) => ({
    ...h,
    label: formatDate(h.date),
  }));
  const avgConsumption = analytics.fuel?.avg_consumption_l_100km;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2.5">
        <Card className="p-3.5">
          <p className="text-xs text-slate-500">Всього витрачено</p>
          <p className="mt-1 text-lg font-semibold text-white">
            {formatMoney(analytics.totals.all_time)}
          </p>
        </Card>
        <Card className="p-3.5">
          <p className="text-xs text-slate-500">Цей місяць</p>
          <p className="mt-1 text-lg font-semibold text-white">
            {formatMoney(analytics.totals.this_month)}
          </p>
        </Card>
      </div>

      <Card className="p-3.5">
        <p className="mb-2 text-xs text-slate-500">За категоріями (весь час)</p>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
          {SERIES.map(({ key, label, color }) => (
            <div key={key} className="flex items-center justify-between gap-2 text-sm">
              <span className="flex items-center gap-1.5 text-slate-400">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
                {label}
              </span>
              <span className="font-medium text-slate-200">
                {formatMoney(analytics.totals.by_type?.[key] ?? 0)}
              </span>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-white">Витрати за місяцями, ₴</h2>
        {!hasSpending ? (
          <p className="py-6 text-center text-sm text-slate-500">
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

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-white">Витрата пального, л/100 км</h2>
        {fuelHistory.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500">
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
                {avgConsumption != null && (
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
                <Line
                  type="monotone"
                  dataKey="consumption_l_100km"
                  name="Витрата"
                  stroke="#3987e5"
                  strokeWidth={2}
                  dot={{ r: 3, fill: '#3987e5', stroke: SURFACE, strokeWidth: 2 }}
                  activeDot={{ r: 5, fill: '#3987e5', stroke: SURFACE, strokeWidth: 2 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        {analytics.fuel?.last_consumption_l_100km != null && (
          <p className="mt-2 text-xs text-slate-500">
            Остання виміряна витрата: {analytics.fuel.last_consumption_l_100km.toFixed(2)} л/100 км
          </p>
        )}
      </Card>
    </div>
  );
}
