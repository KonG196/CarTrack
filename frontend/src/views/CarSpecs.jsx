import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Plus, Pencil, Trash2, Wrench } from 'lucide-react';
import { extractError } from '../api/client';
import { getCar } from '../api/cars';
import {
  getSpecs,
  createSpec,
  updateSpec,
  deleteSpec,
  applySpecPreset,
  groupSpecsByCategory,
  SPEC_CATEGORIES,
} from '../api/specs';
import { canDo } from '../utils/permissions';
import { specCategoryLabel } from '../i18n/domain';
import { Button, TextField, SelectField, Card, Spinner, ErrorMessage, ConfirmDialog } from '../components/UI';
import Toast from '../components/Toast';

// Category is a canonical (Ukrainian) value; only its display is localized.
const CATEGORY_OPTIONS = SPEC_CATEGORIES.map((c) => ({ value: c, label: specCategoryLabel(c) }));

const PRESET_KEY = 'golf7_16tdi';

function SpecForm({ initial, onSubmit, onCancel }) {
  const { t } = useTranslation();
  const [form, setForm] = useState({
    category: initial?.category || SPEC_CATEGORIES[0],
    name: initial?.name || '',
    value: initial?.value || '',
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!form.name.trim()) return setError(t('carSpecs.errNameRequired'));
    if (!form.value.trim()) return setError(t('carSpecs.errValueRequired'));

    setSubmitting(true);
    try {
      await onSubmit({
        category: form.category,
        name: form.name.trim(),
        value: form.value.trim(),
      });
    } catch (err) {
      setError(extractError(err, t('carSpecs.errSaveFailed')));
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <SelectField
        label={t('carSpecs.category')}
        value={form.category}
        onChange={set('category')}
        options={CATEGORY_OPTIONS}
      />
      <div className="grid grid-cols-2 gap-3">
        <TextField label={t('carSpecs.name')} required value={form.name} onChange={set('name')} />
        <TextField label={t('carSpecs.value')} required value={form.value} onChange={set('value')} />
      </div>
      <ErrorMessage>{error}</ErrorMessage>
      <div className="flex gap-2">
        <Button type="submit" disabled={submitting} className="flex-1">
          {submitting ? t('common.saving') : initial ? t('common.saveChanges') : t('carSpecs.addRow')}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
      </div>
    </form>
  );
}

export default function CarSpecs() {
  const { t } = useTranslation();
  const { carId } = useParams();

  const [car, setCar] = useState(null);
  const [specs, setSpecs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [toast, setToast] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [deletingSpec, setDeletingSpec] = useState(null);
  const [presetLoading, setPresetLoading] = useState(false);

  const canManage = canDo(car?.your_role, 'spec:manage');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    Promise.all([getCar(carId), getSpecs(carId)])
      .then(([carData, specsData]) => {
        if (cancelled) return;
        setCar(carData);
        setSpecs(specsData);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err?.response?.status === 404 ? t('carSpecs.carNotFound') : t('carSpecs.loadFailed')
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [carId]);

  const handleAdd = async (payload) => {
    await createSpec(carId, payload);
    setSpecs(await getSpecs(carId));
    setShowForm(false);
    setToast(t('carSpecs.rowAdded'));
  };

  const handleEdit = async (specId, payload) => {
    await updateSpec(specId, payload);
    setSpecs(await getSpecs(carId));
    setEditingId(null);
    setToast(t('carSpecs.rowUpdated'));
  };

  const confirmDelete = async () => {
    const spec = deletingSpec;
    setDeletingSpec(null);
    if (!spec) return;
    setActionError('');
    try {
      await deleteSpec(spec.id);
      setSpecs((prev) => prev.filter((s) => s.id !== spec.id));
      setToast(t('carSpecs.rowDeleted'));
    } catch (err) {
      setActionError(extractError(err, t('carSpecs.errDeleteFailed')));
    }
  };

  const handlePreset = async () => {
    if (presetLoading) return;
    setActionError('');
    setPresetLoading(true);
    try {
      setSpecs(await applySpecPreset(carId, PRESET_KEY));
      setToast(t('carSpecs.presetApplied'));
    } catch (err) {
      setActionError(extractError(err, t('carSpecs.errPresetFailed')));
    } finally {
      setPresetLoading(false);
    }
  };

  if (loading) return <Spinner />;

  if (error) {
    return (
      <div className="stagger space-y-4">
        <ErrorMessage>{error}</ErrorMessage>
        <Link to="/garage" className="inline-flex items-center gap-1.5 text-sm text-mist hover:text-fg">
          <ArrowLeft className="h-4 w-4" />
          {t('carSpecs.toGarage')}
        </Link>
      </div>
    );
  }

  const groups = groupSpecsByCategory(specs);

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />

      <ConfirmDialog
        open={deletingSpec !== null}
        title={t('carSpecs.deleteRowTitle')}
        message={deletingSpec ? t('carSpecs.deleteRowMessage', { name: deletingSpec.name }) : ''}
        onConfirm={confirmDelete}
        onCancel={() => setDeletingSpec(null)}
      />

      <div className="flex items-center justify-between gap-2 px-1">
        <div className="min-w-0">
          <Link
            to="/garage"
            className="inline-flex items-center gap-1.5 text-xs text-mist transition-colors hover:text-fg"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            {t('carSpecs.toGarage')}
          </Link>
          <h1 className="mt-1 truncate font-display text-lg font-semibold text-fg">
            {t('carSpecs.title')}{car ? ` · ${car.brand} ${car.model}` : ''}
          </h1>
        </div>
        {!showForm && canManage && (
          <Button variant="secondary" onClick={() => setShowForm(true)} className="flex-shrink-0 px-3 py-1.5">
            <Plus className="h-4 w-4" />
            {t('common.add')}
          </Button>
        )}
      </div>

      {actionError && <ErrorMessage>{actionError}</ErrorMessage>}

      {showForm && (
        <Card>
          <h2 className="mb-3 font-display text-sm font-semibold text-fg">{t('carSpecs.newRow')}</h2>
          <SpecForm onSubmit={handleAdd} onCancel={() => setShowForm(false)} />
        </Card>
      )}

      {specs.length === 0 && !showForm ? (
        <Card className="flex flex-col items-center gap-3 p-8 text-center">
          <Wrench className="h-8 w-8 text-mist/70" />
          <p className="text-sm text-mist">
            {canManage ? t('carSpecs.emptyManage') : t('carSpecs.emptyViewer')}
          </p>
          {canManage && (
            <Button onClick={handlePreset} disabled={presetLoading} className="w-full">
              {presetLoading ? t('carSpecs.applying') : t('carSpecs.presetLabel')}
            </Button>
          )}
        </Card>
      ) : (
        groups.map(({ category, specs: rows }) => (
          <Card key={category}>
            <h2 className="mb-2 font-display text-sm font-semibold text-fg">{specCategoryLabel(category)}</h2>
            <div className="divide-y divide-edge">
              {rows.map((spec) =>
                editingId === spec.id ? (
                  <div key={spec.id} className="py-3">
                    <SpecForm
                      initial={spec}
                      onSubmit={(payload) => handleEdit(spec.id, payload)}
                      onCancel={() => setEditingId(null)}
                    />
                  </div>
                ) : (
                  <div key={spec.id} className="flex items-center justify-between gap-3 py-2.5">
                    <span className="min-w-0 flex-1 text-sm text-mist">{spec.name}</span>
                    <span className="min-w-0 text-right text-sm font-medium text-fg">{spec.value}</span>
                    {canManage && (
                      <div className="flex flex-shrink-0 items-center">
                        <button
                          type="button"
                          onClick={() => setEditingId(spec.id)}
                          aria-label={t('carSpecs.editAria', { name: spec.name })}
                          className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-raised hover:text-fg"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeletingSpec(spec)}
                          aria-label={t('carSpecs.deleteAria', { name: spec.name })}
                          className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-crit/10 hover:text-crit"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    )}
                  </div>
                )
              )}
            </div>
          </Card>
        ))
      )}
    </div>
  );
}
