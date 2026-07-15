import { useEffect, useState } from 'react';
import { CircleDot, Plus, Trash2, Check, Gauge, CalendarDays } from 'lucide-react';
import { extractError } from '../api/client';
import {
  getTireSets,
  createTireSet,
  deleteTireSet,
  installTireSet,
  tireSeasonLabel,
  TIRE_SEASONS,
} from '../api/tires';
import { formatKm, formatDate } from '../utils/format';
import { canDo } from '../utils/permissions';
import { Button, TextField, SelectField, Card, Spinner, ErrorMessage, ConfirmDialog } from './UI';

function TireForm({ onSubmit, onCancel }) {
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
    if (!form.name.trim()) return setError('Вкажіть назву');
    const dotYear = parseInt(form.dot_year, 10);
    if (form.dot_year && (!Number.isFinite(dotYear) || dotYear < 1980 || dotYear > 2100)) {
      return setError('Вкажіть коректний рік випуску');
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
      setError(extractError(err, 'Не вдалося додати комплект'));
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <TextField label="Назва" required value={form.name} onChange={set('name')} />
      <SelectField
        label="Сезон"
        value={form.season}
        onChange={set('season')}
        options={TIRE_SEASONS}
      />
      <div className="grid grid-cols-2 gap-3">
        <TextField label="Розмір" value={form.size} onChange={set('size')} hint="напр. 205/55 R16" />
        <TextField
          label="Рік випуску (DOT)"
          type="number"
          inputMode="numeric"
          numeric
          value={form.dot_year}
          onChange={set('dot_year')}
        />
      </div>
      <TextField
        label="Куплені"
        type="date"
        value={form.purchased_at}
        onChange={set('purchased_at')}
      />
      <ErrorMessage>{error}</ErrorMessage>
      <div className="flex gap-2">
        <Button type="submit" disabled={submitting} className="flex-1">
          {submitting ? 'Збереження…' : 'Додати комплект'}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          Скасувати
        </Button>
      </div>
    </form>
  );
}

export default function TiresCard({ car, onToast }) {
  const canManage = canDo(car?.your_role, 'tire:manage');
  const [tireSets, setTireSets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [deletingSet, setDeletingSet] = useState(null);
  const [installingId, setInstallingId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    getTireSets(car.id)
      .then((data) => {
        if (!cancelled) setTireSets(data);
      })
      .catch(() => {
        if (!cancelled) setError('Не вдалося завантажити комплекти шин');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
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
    onToast('Комплект додано');
  };

  const handleInstall = async (tireSet) => {
    if (installingId != null) return;
    setError('');
    setInstallingId(tireSet.id);
    try {
      await installTireSet(tireSet.id);
      await reload();
      onToast(`Встановлено: ${tireSet.name}`);
    } catch (err) {
      setError(extractError(err, 'Не вдалося встановити комплект'));
    } finally {
      setInstallingId(null);
    }
  };

  const confirmDelete = async () => {
    const tireSet = deletingSet;
    setDeletingSet(null);
    if (!tireSet) return;
    setError('');
    try {
      await deleteTireSet(tireSet.id);
      setTireSets((prev) => prev.filter((t) => t.id !== tireSet.id));
      onToast('Комплект видалено');
    } catch (err) {
      setError(extractError(err, 'Не вдалося видалити комплект'));
    }
  };

  return (
    <Card>
      <ConfirmDialog
        open={deletingSet !== null}
        title="Видалити комплект?"
        message={deletingSet ? `Видалити «${deletingSet.name}»?` : ''}
        onConfirm={confirmDelete}
        onCancel={() => setDeletingSet(null)}
      />

      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
          <CircleDot className="h-4 w-4 text-mist" />
          Шини · {car.brand} {car.model}
        </h2>
        {!showForm && canManage && (
          <Button variant="ghost" onClick={() => setShowForm(true)} className="px-2.5 py-1.5 text-amber">
            <Plus className="h-4 w-4" />
            Додати
          </Button>
        )}
      </div>

      {error && <ErrorMessage className="mb-2">{error}</ErrorMessage>}

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
            ? 'Зимові, літні, всесезонні — з розміром, роком випуску і пробігом на встановленому комплекті.'
            : 'Власник ще не додав комплектів шин.'}
        </p>
      ) : (
        <div className="divide-y divide-edge">
          {tireSets.map((tireSet) => (
            <div key={tireSet.id} className="flex items-start justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-sm font-medium text-fg">
                  <span className="truncate">{tireSet.name}</span>
                  {tireSet.is_installed && (
                    <span className="flex flex-shrink-0 items-center gap-1 rounded-full bg-ok/15 px-2 py-0.5 text-xs font-medium text-ok">
                      <Check className="h-3 w-3" />
                      Встановлені
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
                      {formatKm(tireSet.km_on_set)} на комплекті
                    </span>
                  )}
                  {tireSet.purchased_at && (
                    <span className="flex items-center gap-1">
                      <CalendarDays className="h-3 w-3" />
                      {formatDate(tireSet.purchased_at)}
                    </span>
                  )}
                </p>
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
                      {installingId === tireSet.id ? 'Встановлення…' : 'Встановити'}
                    </Button>
                  )}
                  <button
                    type="button"
                    onClick={() => setDeletingSet(tireSet)}
                    aria-label={`Видалити ${tireSet.name}`}
                    className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-crit/10 hover:text-crit"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
