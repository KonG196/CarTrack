import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  CircleDot,
  Plus,
  Trash2,
  Check,
  Gauge,
  CalendarDays,
  RotateCw,
  Snowflake,
  Sun,
  AlertTriangle,
} from 'lucide-react';
import { extractError } from '../api/client';
import {
  getTireSets,
  getTireSeasonStatus,
  createTireSet,
  deleteTireSet,
  installTireSet,
  rotateTireSet,
  tireSeasonLabel,
  TIRE_SEASONS,
} from '../api/tires';
import { tireAgeYears, tireAgeLevel, tireSeasonMismatch } from '../utils/tireAge';

// Makers advise swapping the axles every ~10 000 km; past that the card nudges.
const ROTATION_INTERVAL_KM = 10000;
import { formatKm, formatDate } from '../utils/format';
import { canDo } from '../utils/permissions';
import { Button, DateField, TextField, SelectField, Card, Spinner, ErrorMessage, ConfirmDialog } from './UI';

function TireForm({ onSubmit, onCancel }) {
  const { t } = useTranslation();
  const [form, setForm] = useState({
    name: '',
    season: 'winter',
    size: '',
    dot_year: '',
    purchased_at: '',
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!form.name.trim()) return setError(t('tiresCard.errName'));
    const dotYear = parseInt(form.dot_year, 10);
    if (form.dot_year && (!Number.isFinite(dotYear) || dotYear < 1980 || dotYear > 2100)) {
      return setError(t('tiresCard.errDotYear'));
    }

    setSubmitting(true);
    try {
      await onSubmit({
        name: form.name.trim(),
        season: form.season,
        size: form.size.trim() || null,
        dot_year: form.dot_year ? dotYear : null,
        purchased_at: form.purchased_at || null,
      });
    } catch (err) {
      setError(extractError(err, t('tiresCard.errAdd')));
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <TextField label={t('tiresCard.name')} required value={form.name} onChange={set('name')} />
      <SelectField
        label={t('tiresCard.season')}
        value={form.season}
        onChange={set('season')}
        options={TIRE_SEASONS}
      />
      <div className="grid grid-cols-2 gap-3">
        <TextField label={t('tiresCard.size')} value={form.size} onChange={set('size')} hint={t('tiresCard.sizeHint')} />
        <TextField
          label={t('tiresCard.dotYear')}
          type="number"
          inputMode="numeric"
          numeric
          value={form.dot_year}
          onChange={set('dot_year')}
        />
      </div>
      <DateField
        label={t('tiresCard.purchased')}
        clearable
        value={form.purchased_at}
        onChange={(v) => setForm((f) => ({ ...f, purchased_at: v }))}
      />
      <ErrorMessage>{error}</ErrorMessage>
      <div className="flex gap-2">
        <Button type="submit" disabled={submitting} className="flex-1">
          {submitting ? t('common.saving') : t('tiresCard.addSet')}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
      </div>
    </form>
  );
}

export default function TiresCard({ car, onToast }) {
  const { t } = useTranslation();
  const canManage = canDo(car?.your_role, 'tire:manage');
  const [tireSets, setTireSets] = useState([]);
  const [seasonStatus, setSeasonStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [deletingSet, setDeletingSet] = useState(null);
  const [installingId, setInstallingId] = useState(null);
  const [rotatingId, setRotatingId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    setSeasonStatus(null);
    setTireSets([]); // drop the previous car's sets so a slow/failed load never shows them
    getTireSets(car.id)
      .then((data) => {
        if (!cancelled) setTireSets(data);
      })
      .catch(() => {
        if (!cancelled) setError(t('tiresCard.errLoad'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    // Best-effort: the seasonal banner is a nice-to-have, so a failure here
    // must not block or error the set list.
    getTireSeasonStatus(car.id)
      .then((data) => {
        if (!cancelled) setSeasonStatus(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [car.id]);

  const reload = async () => {
    setTireSets(await getTireSets(car.id));
  };

  const handleCreate = async (payload) => {
    await createTireSet(car.id, payload);
    await reload();
    setShowForm(false);
    onToast(t('tiresCard.toastAdded'));
  };

  const handleInstall = async (tireSet) => {
    if (installingId != null) return;
    setError('');
    setInstallingId(tireSet.id);
    try {
      await installTireSet(tireSet.id);
      await reload();
      onToast(t('tiresCard.toastInstalled', { name: tireSet.name }));
    } catch (err) {
      setError(extractError(err, t('tiresCard.errInstall')));
    } finally {
      setInstallingId(null);
    }
  };

  const handleRotate = async (tireSet) => {
    if (rotatingId != null) return;
    setError('');
    setRotatingId(tireSet.id);
    try {
      await rotateTireSet(tireSet.id);
      await reload();
      onToast(t('tiresCard.toastRotated'));
    } catch (err) {
      setError(extractError(err, t('tiresCard.errRotate')));
    } finally {
      setRotatingId(null);
    }
  };

  const confirmDelete = async () => {
    const tireSet = deletingSet;
    setDeletingSet(null);
    if (!tireSet) return;
    setError('');
    try {
      await deleteTireSet(tireSet.id);
      setTireSets((prev) => prev.filter((s) => s.id !== tireSet.id));
      onToast(t('tiresCard.toastDeleted'));
    } catch (err) {
      setError(extractError(err, t('tiresCard.errDelete')));
    }
  };

  return (
    <Card>
      <ConfirmDialog
        open={deletingSet !== null}
        title={t('tiresCard.deleteSetTitle')}
        message={deletingSet ? t('tiresCard.deleteSetConfirm', { name: deletingSet.name }) : ''}
        onConfirm={confirmDelete}
        onCancel={() => setDeletingSet(null)}
      />

      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
          <CircleDot className="h-4 w-4 text-mist" />
          {t('tiresCard.title')} · {car.brand} {car.model}
        </h2>
        {!showForm && canManage && (
          <Button variant="ghost" onClick={() => setShowForm(true)} className="px-2.5 py-1.5 text-amber">
            <Plus className="h-4 w-4" />
            {t('common.add')}
          </Button>
        )}
      </div>

      {error && <ErrorMessage className="mb-2">{error}</ErrorMessage>}

      {!loading &&
        !error &&
        seasonStatus?.changeover_season &&
        tireSeasonMismatch(
          seasonStatus.changeover_season,
          tireSets.find((s) => s.is_installed),
        ) && (
          <div className="mb-3 flex items-start gap-2 rounded-xl border border-edge bg-raised p-3 text-sm font-medium text-amber">
            {seasonStatus.changeover_season === 'winter' ? (
              <Snowflake className="mt-0.5 h-4 w-4 flex-shrink-0" />
            ) : (
              <Sun className="mt-0.5 h-4 w-4 flex-shrink-0" />
            )}
            <span>
              {seasonStatus.changeover_season === 'winter'
                ? t('tiresCard.changeoverWinter')
                : t('tiresCard.changeoverSummer')}
              {tireSets.length === 0 ? t('tiresCard.changeoverAddSet') : '.'}
            </span>
          </div>
        )}

      {!loading && !error && seasonStatus?.washer_changeover_due && (
        <p className="mb-3 flex items-center gap-1.5 text-xs text-mist">
          <Snowflake className="h-3 w-3 flex-shrink-0" />
          {t('tiresCard.washerChangeover')}
        </p>
      )}

      {showForm && (
        <div className="mb-3 rounded-xl border border-edge bg-raised p-3">
          <TireForm onSubmit={handleCreate} onCancel={() => setShowForm(false)} />
        </div>
      )}

      {loading ? (
        <Spinner className="py-4" />
      ) : tireSets.length === 0 ? (
        <p className="py-2 text-sm text-mist">
          {canManage
            ? t('tiresCard.emptyManage')
            : t('tiresCard.emptyViewer')}
        </p>
      ) : (
        <div className="divide-y divide-edge">
          {tireSets.map((tireSet) => {
            const ageYears = tireAgeYears(tireSet);
            const ageLevel = tireAgeLevel(ageYears);
            return (
            <div key={tireSet.id} className="flex items-start justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-sm font-medium text-fg">
                  <span className="truncate">{tireSet.name}</span>
                  {tireSet.is_installed && (
                    <span className="flex flex-shrink-0 items-center gap-1 rounded-full bg-ok/15 px-2 py-0.5 text-xs font-medium text-ok">
                      <Check className="h-3 w-3" />
                      {t('tiresCard.installed')}
                    </span>
                  )}
                </p>
                <p className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-mist">
                  <span>{tireSeasonLabel(tireSet.season)}</span>
                  {tireSet.size && <span>{tireSet.size}</span>}
                  {tireSet.dot_year != null && <span>DOT {tireSet.dot_year}</span>}
                  {tireSet.km_on_set != null && (
                    <span className="flex items-center gap-1">
                      <Gauge className="h-3 w-3" />
                      {t('tiresCard.kmOnSet', { km: formatKm(tireSet.km_on_set) })}
                    </span>
                  )}
                  {tireSet.purchased_at && (
                    <span className="flex items-center gap-1">
                      <CalendarDays className="h-3 w-3" />
                      {formatDate(tireSet.purchased_at)}
                    </span>
                  )}
                </p>
                {(ageLevel === 'warn' || ageLevel === 'crit') && (
                  <p
                    className={`mt-1 flex items-center gap-1 text-xs font-medium ${
                      ageLevel === 'crit' ? 'text-crit' : 'text-amber'
                    }`}
                  >
                    <AlertTriangle className="h-3 w-3 flex-shrink-0" />
                    {ageLevel === 'crit'
                      ? t('tiresCard.tireAgeReplace', { years: ageYears })
                      : t('tiresCard.tireAgeCheck', { years: ageYears })}
                  </p>
                )}
                {tireSet.is_installed && tireSet.km_since_rotation != null && (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span
                      className={`text-xs ${
                        tireSet.km_since_rotation >= ROTATION_INTERVAL_KM
                          ? 'font-medium text-amber'
                          : 'text-mist'
                      }`}
                    >
                      {tireSet.km_since_rotation >= ROTATION_INTERVAL_KM
                        ? t('tiresCard.rotationDue', { km: formatKm(tireSet.km_since_rotation) })
                        : t('tiresCard.rotationSince', { km: formatKm(tireSet.km_since_rotation) })}
                    </span>
                    {canManage && (
                      <Button
                        variant="secondary"
                        onClick={() => handleRotate(tireSet)}
                        disabled={rotatingId != null}
                        className="px-2.5 py-1 text-xs"
                      >
                        <RotateCw className="h-3.5 w-3.5" />
                        {rotatingId === tireSet.id ? t('tiresCard.recording') : t('tiresCard.rotateAxles')}
                      </Button>
                    )}
                  </div>
                )}
              </div>
              {canManage && (
                <div className="flex flex-shrink-0 items-center gap-1">
                  {!tireSet.is_installed && (
                    <Button
                      variant="secondary"
                      onClick={() => handleInstall(tireSet)}
                      disabled={installingId != null}
                      className="px-2.5 py-1.5"
                    >
                      {installingId === tireSet.id ? t('tiresCard.installing') : t('tiresCard.install')}
                    </Button>
                  )}
                  <button
                    type="button"
                    onClick={() => setDeletingSet(tireSet)}
                    aria-label={t('tiresCard.deleteAria', { name: tireSet.name })}
                    className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-crit/10 hover:text-crit"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              )}
            </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
