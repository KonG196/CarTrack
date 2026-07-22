import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import { Loader2, Trash2, Upload, Activity, FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useCarStore } from '../store/carStore';
import { extractError } from '../api/client';
import { importObdCsv, getObdSessions, getObdSession, deleteObdSession } from '../api/obd';
import { formatDate } from '../utils/format';
import { metricLabel, sortMetrics, chartPoints, formatDuration } from '../utils/obdMetrics';
import { canDo } from '../utils/permissions';
import { Button, Card, Spinner, ErrorMessage, ConfirmDialog } from '../components/UI';

const VERDICT_TONES = {
  ok: 'border-ok/40 bg-ok/10 text-ok',
  warn: 'border-amber/40 bg-amber/10 text-amber',
  crit: 'border-crit/40 bg-crit/10 text-crit',
};

const GRID = '#1D2A3E';
const MUTED = '#93A1B8';
const SURFACE = '#121A26';
const LINE = '#3987e5';

function VerdictCard({ verdict }) {
  return (
    <div
      className={`rounded-2xl border px-3.5 py-3 text-sm ${
        VERDICT_TONES[verdict.level] || VERDICT_TONES.ok
      }`}
    >
      {verdict.text}
    </div>
  );
}

function MetricChart({ metric }) {
  const { t } = useTranslation();
  const points = chartPoints(metric.series);
  const unit = metric.unit ? ` ${metric.unit}` : '';

  return (
    <Card>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="font-display text-sm font-semibold text-fg">{metricLabel(metric.key)}</h3>
        <span className="font-mono text-xs tabular-nums text-mist">
          {t('diagnostics.metricStats', {
            min: metric.min.toFixed(1),
            max: metric.max.toFixed(1),
            last: metric.last.toFixed(1),
            unit,
          })}
        </span>
      </div>
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 6, right: 8, left: -20, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID} strokeWidth={1} />
            <XAxis
              dataKey="t"
              type="number"
              domain={['dataMin', 'dataMax']}
              tick={{ fill: MUTED, fontSize: 10 }}
              axisLine={{ stroke: GRID }}
              tickLine={false}
              tickFormatter={(sec) => `${Math.round(sec)}${t('diagnostics.secondsShort')}`}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: MUTED, fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              width={44}
              domain={['auto', 'auto']}
              tickFormatter={(v) => (Math.abs(v) >= 100 ? String(Math.round(v)) : v.toFixed(1))}
            />
            <Tooltip
              contentStyle={{
                background: '#0D1520',
                border: `1px solid ${GRID}`,
                borderRadius: 12,
                fontSize: 12,
              }}
              labelStyle={{ color: MUTED }}
              itemStyle={{ color: '#E9EEF6' }}
              labelFormatter={(sec) => t('diagnostics.chartLabelFromStart', { sec: Math.round(sec) })}
              formatter={(v) => [`${v}${unit}`, metricLabel(metric.key)]}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={LINE}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: LINE, stroke: SURFACE, strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

function EmptyState({ canImport }) {
  const { t } = useTranslation();
  return (
    <Card className="flex flex-col items-center gap-3 p-8 text-center">
      <Activity className="h-8 w-8 text-mist/70" />
      <p className="text-sm text-mist">{t('diagnostics.emptyTitle')}</p>
      {canImport && (
      <div className="text-left text-xs text-mist/80">
        <p className="mb-1.5 font-medium text-mist">{t('diagnostics.howToTitle')}</p>
        <ol className="list-decimal space-y-1 pl-4">
          <li>{t('diagnostics.howStep1')}</li>
          <li>{t('diagnostics.howStep2')}</li>
          <li>{t('diagnostics.howStep3')}</li>
          <li>{t('diagnostics.howStep4')}</li>
        </ol>
        <p className="mt-2">{t('diagnostics.howNote')}</p>
      </div>
      )}
    </Card>
  );
}

export default function Diagnostics() {
  const { t } = useTranslation();
  const cars = useCarStore((s) => s.cars);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const carsLoaded = useCarStore((s) => s.carsLoaded);

  const [sessions, setSessions] = useState([]);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const fileInputRef = useRef(null);

  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;
  const canImport = canDo(activeCar?.your_role, 'obd:import');

  const load = useCallback(async () => {
    if (!activeCarId) return;
    setLoading(true);
    setError('');
    try {
      const list = await getObdSessions(activeCarId);
      setSessions(list);
      setDetail(list.length > 0 ? await getObdSession(list[0].id) : null);
    } catch (err) {
      setError(extractError(err, t('diagnostics.errLoad')));
    } finally {
      setLoading(false);
    }
  }, [activeCarId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleFile = async (file) => {
    if (!file || !activeCarId || uploading) return;
    setError('');
    setUploading(true);
    try {
      const imported = await importObdCsv(activeCarId, file);
      setDetail(imported);
      setSessions(await getObdSessions(activeCarId));
    } catch (err) {
      setError(extractError(err, t('diagnostics.errImport')));
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setDragging(false);
    handleFile(event.dataTransfer.files?.[0]);
  };

  const handleSelect = async (session) => {
    setError('');
    try {
      setDetail(await getObdSession(session.id));
    } catch (err) {
      setError(extractError(err, t('diagnostics.errOpenSession')));
    }
  };

  const handleDelete = async () => {
    const session = deleting;
    setDeleting(null);
    if (!session) return;
    try {
      await deleteObdSession(session.id);
      await load();
    } catch (err) {
      setError(extractError(err, t('diagnostics.errDeleteSession')));
    }
  };

  if (carsLoaded && !activeCarId) {
    return (
      <Card className="rise-in mt-8 p-8 text-center">
        <p className="text-sm text-mist">{t('diagnostics.noCarPrompt')}</p>
      </Card>
    );
  }

  const metrics = detail ? sortMetrics(detail.metrics) : [];
  const unmapped = detail?.unmapped_columns || [];

  return (
    <div className="stagger space-y-4">
      <div className="flex items-center justify-between px-1">
        <h1 className="font-display text-lg font-semibold text-fg">{t('diagnostics.title')}</h1>
      </div>

      {error && <ErrorMessage>{error}</ErrorMessage>}

      {canImport && (
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') fileInputRef.current?.click();
          }}
          aria-label={t('diagnostics.uploadAria')}
          className={`flex cursor-pointer flex-col items-center gap-2 rounded-2xl border border-dashed p-6 text-center transition-colors ${
            dragging ? 'border-amber bg-amber/5' : 'border-edge-soft bg-panel hover:border-amber/50'
          }`}
        >
          {uploading ? (
            <Loader2 className="h-6 w-6 animate-spin text-amber" />
          ) : (
            <Upload className="h-6 w-6 text-mist" />
          )}
          <p className="text-sm text-fg">
            {uploading ? t('diagnostics.parsing') : t('diagnostics.dropHint')}
          </p>
          <p className="text-xs text-mist/70">{t('diagnostics.fileLimit')}</p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(event) => {
              handleFile(event.target.files?.[0]);
              event.target.value = '';
            }}
          />
        </div>
      )}

      {loading && <Spinner />}

      {!loading && sessions.length === 0 && <EmptyState canImport={canImport} />}

      {detail && (
        <>
          {detail.verdicts.length > 0 && (
            <div className="space-y-2">
              <h2 className="px-1 font-display text-sm font-semibold text-fg">{t('diagnostics.findingsHeading')}</h2>
              {detail.verdicts.map((verdict) => (
                <VerdictCard key={verdict.key} verdict={verdict} />
              ))}
            </div>
          )}

          {unmapped.length > 0 && (
            <p className="px-1 text-xs text-mist/70">
              {t('diagnostics.unmapped', {
                count: unmapped.length,
                word: t(unmapped.length === 1 ? 'diagnostics.columnOne' : 'diagnostics.columnMany'),
                cols: unmapped.slice(0, 3).join(', '),
                ellipsis: unmapped.length > 3 ? '…' : '',
              })}
            </p>
          )}

          {metrics.length > 0 && (
            <div className="space-y-2.5">
              <h2 className="px-1 font-display text-sm font-semibold text-fg">
                {t('diagnostics.metricsHeading', {
                  duration: formatDuration(detail.session.duration_s),
                })}
              </h2>
              {metrics.map((metric) => (
                <MetricChart key={metric.key} metric={metric} />
              ))}
            </div>
          )}
        </>
      )}

      {sessions.length > 0 && (
        <Card>
          <h2 className="mb-2 font-display text-sm font-semibold text-fg">{t('diagnostics.sessionsHeading')}</h2>
          <div className="divide-y divide-edge">
            {sessions.map((session) => {
              const isOpen = detail?.session?.id === session.id;
              return (
                <div key={session.id} className="flex items-center justify-between gap-2 py-2.5">
                  <button
                    type="button"
                    onClick={() => handleSelect(session)}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  >
                    <FileText
                      className={`h-4 w-4 flex-shrink-0 ${isOpen ? 'text-amber' : 'text-mist'}`}
                    />
                    <span className="min-w-0">
                      <span
                        className={`block truncate text-sm ${isOpen ? 'text-amber' : 'text-fg'}`}
                      >
                        {session.filename}
                      </span>
                      <span className="mt-0.5 block text-xs text-mist/70">
                        {t('diagnostics.sessionMeta', {
                          date: formatDate(session.recorded_at || session.created_at),
                          duration: formatDuration(session.duration_s),
                          count: session.sample_count,
                        })}
                      </span>
                    </span>
                  </button>
                  {canImport && (
                    <Button
                      variant="ghost"
                      onClick={() => setDeleting(session)}
                      aria-label={t('diagnostics.deleteSessionAria', { filename: session.filename })}
                      className="px-2.5 py-1.5"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <ConfirmDialog
        open={Boolean(deleting)}
        title={t('diagnostics.deleteConfirmTitle')}
        message={t('diagnostics.deleteConfirmMessage', { filename: deleting?.filename || '' })}
        onConfirm={handleDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
