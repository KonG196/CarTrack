import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  CalendarDays,
  CheckCircle2,
  Gauge,
  Pencil,
  Plus,
  ShieldCheck,
  Sparkles,
  Trash2,
} from 'lucide-react';

import { extractError } from '../api/client';
import { getIntervalPresets } from '../api/intervals';
import BackLink from '../components/BackLink';
import CompleteIntervalModal from '../components/CompleteIntervalModal';
import Toast from '../components/Toast';
import {
  Button,
  Card,
  ConfirmDialog,
  DateField,
  ErrorMessage,
  Spinner,
  TextField,
} from '../components/UI';
import { useCarStore } from '../store/carStore';
import { canDo } from '../utils/permissions';
import { formatDate, formatKm } from '../utils/format';

// Colour is reserved for what needs attention: "ok" gets none, otherwise amber
// stops meaning anything. Moved here with the intervals block — it lived in
// Garage and referencing it from the new page threw on render.
const STATUS_TEXT = {
  ok: 'text-fg',
  due_soon: 'text-amber',
  overdue: 'text-crit',
};

function IntervalForm({ car, initial, onSubmit, onCancel }) {
  const { t } = useTranslation();
  const [form, setForm] = useState({
    title: initial?.title || '',
    interval_km: initial?.interval_km != null ? String(initial.interval_km) : '',
    interval_days: initial?.interval_days != null ? String(initial.interval_days) : '',
    // Left blank on create: prefilling the car's *current* odometer / today
    // reads as "the service was just done", which quietly zeroes the interval
    // even when the last service was long ago. The owner states when it was
    // actually last done (and may leave it blank if they don't know).
    last_odometer:
      initial != null && initial.last_odometer != null ? String(initial.last_odometer) : '',
    last_date: initial ? initial.last_date || '' : '',
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const intervalKm = parseInt(form.interval_km, 10);
    const intervalDays = parseInt(form.interval_days, 10);
    const hasKm = Number.isFinite(intervalKm) && intervalKm > 0;
    const hasDays = Number.isFinite(intervalDays) && intervalDays > 0;
    if (!form.title.trim()) return setError(t('intervals.errTitleRequired'));
    if (!hasKm && !hasDays) return setError(t('intervals.errIntervalRequired'));

    // For edits, cleared fields go as explicit null so PATCH erases them.
    const payload = { title: form.title.trim() };
    if (hasKm) payload.interval_km = intervalKm;
    else if (initial) payload.interval_km = null;
    if (hasDays) payload.interval_days = intervalDays;
    else if (initial) payload.interval_days = null;
    const lastOdo = parseInt(form.last_odometer, 10);
    if (Number.isFinite(lastOdo) && lastOdo >= 0) payload.last_odometer = lastOdo;
    else if (initial) payload.last_odometer = null;
    if (form.last_date) payload.last_date = form.last_date;
    else if (initial) payload.last_date = null;

    setSubmitting(true);
    try {
      await onSubmit(payload);
    } catch (err) {
      setError(
        extractError(
          err,
          initial ? t('intervals.errSave') : t('intervals.errCreate')
        )
      );
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <TextField
        label={t('intervals.fieldTitle')}
        required
        value={form.title}
        onChange={set('title')}
      />
      <div className="grid grid-cols-2 gap-3">
        <TextField
          label={t('intervals.fieldIntervalKm')}
          type="number"
          inputMode="numeric"
          enterKeyHint="next"
          min="0"
          numeric
          value={form.interval_km}
          onChange={set('interval_km')}
        />
        <TextField
          label={t('intervals.fieldIntervalDays')}
          type="number"
          inputMode="numeric"
          enterKeyHint="next"
          min="0"
          numeric
          value={form.interval_days}
          onChange={set('interval_days')}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <TextField
          label={t('intervals.fieldLastOdometer')}
          type="number"
          inputMode="numeric"
          enterKeyHint="next"
          min="0"
          numeric
          value={form.last_odometer}
          onChange={set('last_odometer')}
          hint={initial ? undefined : t('intervals.lastServiceHint')}
        />
        <DateField
          label={t('intervals.fieldLastDate')}
          value={form.last_date}
          onChange={(v) => setForm((f) => ({ ...f, last_date: v }))}
        />
      </div>
      <ErrorMessage>{error}</ErrorMessage>
      <div className="flex gap-2">
        <Button type="submit" disabled={submitting} className="flex-1">
          {submitting
            ? t('common.saving')
            : initial
              ? t('common.saveChanges')
              : t('intervals.addInterval')}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
      </div>
    </form>
  );
}

const PRESET_GROUPS = {
  maintenance: {
    icon: Sparkles,
    labelKey: 'presetMaintenanceLabel',
    toastKey: 'presetMaintenanceToast',
    errorKey: 'presetMaintenanceError',
  },
  compliance: {
    icon: ShieldCheck,
    labelKey: 'presetComplianceLabel',
    toastKey: 'presetComplianceToast',
    errorKey: 'presetComplianceError',
  },
};

function PresetButtons({ variant, className = '', loadingGroup, onPresets }) {
  const { t } = useTranslation();
  return (
    <div className={`grid grid-cols-2 gap-2 ${className}`}>
      {Object.entries(PRESET_GROUPS).map(([group, { icon: Icon, labelKey }]) => (
        <Button
          key={group}
          variant={variant}
          onClick={() => onPresets(group)}
          disabled={loadingGroup !== null}
          className="w-full"
        >
          <Icon className="h-4 w-4" />
          {loadingGroup === group ? t('intervals.creating') : t(`intervals.${labelKey}`)}
        </Button>
      ))}
    </div>
  );
}

export default function Intervals() {
  const { t } = useTranslation();
  const cars = useCarStore((s) => s.cars);
  const carsLoaded = useCarStore((s) => s.carsLoaded);
  const carsLoading = useCarStore((s) => s.carsLoading);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const intervals = useCarStore((s) => s.intervals);
  const intervalsLoading = useCarStore((s) => s.intervalsLoading);
  const intervalsError = useCarStore((s) => s.intervalsError);
  const fetchIntervals = useCarStore((s) => s.fetchIntervals);
  const fetchCars = useCarStore((s) => s.fetchCars);
  const addInterval = useCarStore((s) => s.addInterval);
  const editInterval = useCarStore((s) => s.editInterval);
  const removeInterval = useCarStore((s) => s.removeInterval);
  const addIntervalPresets = useCarStore((s) => s.addIntervalPresets);
  const completeInterval = useCarStore((s) => s.completeInterval);

  const [toast, setToast] = useState('');
  const [actionError, setActionError] = useState('');
  const [showIntervalForm, setShowIntervalForm] = useState(false);
  const [editingIntervalId, setEditingIntervalId] = useState(null);
  const [deletingInterval, setDeletingInterval] = useState(null);
  const [completingInterval, setCompletingInterval] = useState(null);
  const [presetsLoading, setPresetsLoading] = useState(null);

  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;
  // Intervals are the owner's regimen; an editor may still close a completed one.
  const canManageIntervals = canDo(activeCar?.your_role, 'interval:manage');
  const canCompleteIntervals = canDo(activeCar?.your_role, 'interval:complete');

  useEffect(() => {
    if (!carsLoaded) fetchCars().catch(() => {});
  }, [carsLoaded, fetchCars]);

  useEffect(() => {
    if (activeCarId) fetchIntervals().catch(() => {});
  }, [activeCarId, fetchIntervals]);

  const handleAddInterval = async (payload) => {
    await addInterval(payload);
    setShowIntervalForm(false);
    setToast(t('intervals.toastAdded'));
  };

  const handleEditInterval = async (intervalId, payload) => {
    await editInterval(intervalId, payload);
    setEditingIntervalId(null);
    setToast(t('intervals.toastUpdated'));
  };

  const confirmDeleteInterval = async () => {
    const interval = deletingInterval;
    setDeletingInterval(null);
    if (!interval) return;
    setActionError('');
    try {
      await removeInterval(interval.id);
    } catch (err) {
      setActionError(extractError(err, t('intervals.errDelete')));
    }
  };

  const handlePresets = async (group) => {
    if (!activeCar || presetsLoading) return;
    setActionError('');
    setPresetsLoading(group);
    try {
      const presets = await getIntervalPresets();
      const added = await addIntervalPresets(activeCar, presets[group] || []);
      // Say what actually happened. «Створено» when a car adds a full set for
      // the first time is a lie the day some of them already exist.
      setToast(
        added
          ? t(`intervals.${PRESET_GROUPS[group].toastKey}`)
          : t('intervals.presetsAlreadyAdded')
      );
    } catch (err) {
      setActionError(extractError(err, t(`intervals.${PRESET_GROUPS[group].errorKey}`)));
    } finally {
      setPresetsLoading(null);
    }
  };

  if (carsLoading && !carsLoaded) return <Spinner />;

  if (!activeCar) {
    return (
      <div className="space-y-4">
        <Card>
          <p className="text-sm text-mist">
            {t('intervals.noCarPrompt')}
          </p>
          <Link
            to="/garage/new"
            className="mt-3 inline-flex items-center gap-1 rounded-xl bg-amber px-4 py-2 text-sm font-medium text-amber-ink"
          >
            <Plus className="h-4 w-4" />
            {t('intervals.addCar')}
          </Link>
        </Card>
      </div>
    );
  }

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />
      <ConfirmDialog
        open={deletingInterval !== null}
        title={t('intervals.deleteDialogTitle')}
        message={
          deletingInterval
            ? t('intervals.deleteDialogMessage', { title: deletingInterval.title })
            : ''
        }
        confirmLabel={t('common.delete')}
        onConfirm={confirmDeleteInterval}
        onCancel={() => setDeletingInterval(null)}
      />
      <CompleteIntervalModal
        interval={completingInterval}
        car={activeCar}
        onComplete={completeInterval}
        onClose={() => setCompletingInterval(null)}
        onToast={setToast}
      />

      <BackLink to="/garage">{t('intervals.title')}</BackLink>

      {actionError && <ErrorMessage>{actionError}</ErrorMessage>}

        <Card>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h2 className="font-display text-sm font-semibold text-fg">
              {t('intervals.title')} · {activeCar.brand} {activeCar.model}
            </h2>
            {!showIntervalForm && canManageIntervals && (
              <Button
                variant="ghost"
                onClick={() => setShowIntervalForm(true)}
                className="px-2.5 py-1.5 text-amber"
              >
                <Plus className="h-4 w-4" />
                {t('common.add')}
              </Button>
            )}
          </div>

          {intervalsError && <ErrorMessage className="mb-2">{intervalsError}</ErrorMessage>}

          {showIntervalForm && (
            <div className="rise-in mb-3 rounded-xl border border-edge bg-raised p-3">
              <IntervalForm
                car={activeCar}
                onSubmit={handleAddInterval}
                onCancel={() => setShowIntervalForm(false)}
              />
            </div>
          )}

          {intervalsLoading && intervals.length === 0 ? (
            <Spinner className="py-4" />
          ) : intervals.length === 0 ? (
            <div className="py-2">
              <p className={canManageIntervals ? 'mb-3 text-sm text-mist' : 'text-sm text-mist'}>
                {canManageIntervals
                  ? t('intervals.emptyManage')
                  : t('intervals.emptyViewer')}
              </p>
              {canManageIntervals && (
                <PresetButtons
                  variant="secondary"
                  loadingGroup={presetsLoading}
                  onPresets={handlePresets}
                />
              )}
            </div>
          ) : (
            <>
              <div className="divide-y divide-edge">
                {intervals.map((interval) =>
                  editingIntervalId === interval.id ? (
                    <div key={interval.id} className="rise-in py-3">
                      <IntervalForm
                        car={activeCar}
                        initial={interval}
                        onSubmit={(payload) => handleEditInterval(interval.id, payload)}
                        onCancel={() => setEditingIntervalId(null)}
                      />
                    </div>
                  ) : (
                    <div key={interval.id} className="flex items-start justify-between gap-3 py-3">
                      {(() => {
                        const info = (
                          <>
                            <p
                              className={`flex items-center gap-1.5 text-sm font-medium ${STATUS_TEXT[interval.status] || 'text-fg'}`}
                            >
                              {interval.title}
                              {canCompleteIntervals && (
                                <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0 text-mist/40 transition-colors group-hover:text-ok" />
                              )}
                            </p>
                            <p className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-mist">
                              {interval.interval_km != null && (
                                <span className="flex items-center gap-1">
                                  <Gauge className="h-3 w-3" />
                                  {t('intervals.everyKm', { km: formatKm(interval.interval_km) })}
                                </span>
                              )}
                              {interval.interval_days != null && (
                                <span className="flex items-center gap-1">
                                  <CalendarDays className="h-3 w-3" />
                                  {t('intervals.everyDays', { days: interval.interval_days })}
                                </span>
                              )}
                            </p>
                            <p className="mt-0.5 text-xs text-mist/70">
                              {t('intervals.last')}{' '}
                              {interval.last_odometer != null ? formatKm(interval.last_odometer) : '—'} ·{' '}
                              {formatDate(interval.last_date)}
                            </p>
                          </>
                        );
                        // Tapping the interval opens its «Виконано» form. Edit and
                        // delete stay as their own icons on the right.
                        return canCompleteIntervals ? (
                          <button
                            type="button"
                            onClick={() => setCompletingInterval(interval)}
                            aria-label={t('intervals.markDoneAria', { title: interval.title })}
                            className="group min-w-0 flex-1 rounded-lg text-left transition active:opacity-70 motion-reduce:active:opacity-100"
                          >
                            {info}
                          </button>
                        ) : (
                          <div className="min-w-0 flex-1">{info}</div>
                        );
                      })()}
                      <div className="flex flex-shrink-0 items-center gap-1">
                        {canManageIntervals && (
                          <>
                            <button
                              type="button"
                              onClick={() => setEditingIntervalId(interval.id)}
                              aria-label={t('intervals.editAria', { title: interval.title })}
                              className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-raised hover:text-fg"
                            >
                              <Pencil className="h-4 w-4" />
                            </button>
                            <button
                              type="button"
                              onClick={() => setDeletingInterval(interval)}
                              aria-label={t('intervals.deleteAria', { title: interval.title })}
                              className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-crit/10 hover:text-crit"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  )
                )}
              </div>
            </>
          )}
        </Card>
    </div>
  );
}
