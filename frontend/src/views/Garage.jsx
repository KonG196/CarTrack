import { useEffect, useState } from 'react';
import {
  Car,
  Plus,
  Pencil,
  Trash2,
  Check,
  Gauge,
  CalendarDays,
  Sparkles,
  Send,
  Copy,
  ExternalLink,
  FileDown,
  Loader2,
} from 'lucide-react';
import { useCarStore } from '../store/carStore';
import { extractError } from '../api/client';
import { downloadCarReport } from '../api/reports';
import * as telegramApi from '../api/telegram';
import { formatKm, formatDate } from '../utils/format';
import { Button, Input, Select, Card, Spinner, ErrorMessage } from '../components/UI';
import Toast from '../components/Toast';

const FUEL_TYPES = [
  { value: 'petrol', label: 'Бензин' },
  { value: 'diesel', label: 'Дизель' },
  { value: 'lpg', label: 'ГБО' },
  { value: 'electric', label: 'Електро' },
  { value: 'hybrid', label: 'Гібрид' },
];

const fuelLabel = (value) => FUEL_TYPES.find((f) => f.value === value)?.label || value;

const STATUS_TEXT = {
  ok: 'text-blue-400',
  due_soon: 'text-amber-400',
  overdue: 'text-red-400',
};

function CarForm({ initial, onSubmit, onCancel }) {
  const [form, setForm] = useState({
    brand: initial?.brand || '',
    model: initial?.model || '',
    generation: initial?.generation || '',
    engine: initial?.engine || '',
    year: initial?.year != null ? String(initial.year) : '',
    fuel_type: initial?.fuel_type || 'petrol',
    current_odometer: initial?.current_odometer != null ? String(initial.current_odometer) : '',
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const year = parseInt(form.year, 10);
    const odometer = parseInt(form.current_odometer, 10);
    if (!form.brand.trim()) return setError('Вкажіть марку');
    if (!form.model.trim()) return setError('Вкажіть модель');
    if (!Number.isFinite(year) || year < 1900 || year > 2100) return setError('Вкажіть коректний рік');
    if (!Number.isFinite(odometer) || odometer < 0) return setError('Вкажіть коректний пробіг');

    const payload = {
      brand: form.brand.trim(),
      model: form.model.trim(),
      generation: form.generation.trim() || null,
      engine: form.engine.trim() || null,
      year,
      fuel_type: form.fuel_type,
      current_odometer: odometer,
    };

    setSubmitting(true);
    try {
      await onSubmit(payload);
    } catch (err) {
      setError(extractError(err, 'Не вдалося зберегти авто'));
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <Input label="Марка" required value={form.brand} onChange={set('brand')} placeholder="Skoda" />
        <Input label="Модель" required value={form.model} onChange={set('model')} placeholder="Octavia" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Input label="Покоління" value={form.generation} onChange={set('generation')} placeholder="A7" />
        <Input label="Двигун" value={form.engine} onChange={set('engine')} placeholder="1.6 TDI" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Input
          label="Рік"
          type="number"
          inputMode="numeric"
          required
          value={form.year}
          onChange={set('year')}
          placeholder="2018"
        />
        <Select
          label="Пальне"
          value={form.fuel_type}
          onChange={set('fuel_type')}
          options={FUEL_TYPES}
        />
      </div>
      <Input
        label="Поточний пробіг, км"
        type="number"
        inputMode="numeric"
        min="0"
        required
        value={form.current_odometer}
        onChange={set('current_odometer')}
        placeholder="123456"
      />
      <ErrorMessage>{error}</ErrorMessage>
      <div className="flex gap-2">
        <Button type="submit" disabled={submitting} className="flex-1">
          {submitting ? 'Збереження…' : 'Зберегти'}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          Скасувати
        </Button>
      </div>
    </form>
  );
}

function IntervalForm({ car, onSubmit, onCancel }) {
  const [form, setForm] = useState({
    title: '',
    interval_km: '',
    interval_days: '',
    last_odometer: car ? String(car.current_odometer) : '',
    last_date: new Date().toISOString().slice(0, 10),
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
    if (!form.title.trim()) return setError('Вкажіть назву');
    if (!hasKm && !hasDays) return setError('Вкажіть інтервал у км або днях');

    const payload = { title: form.title.trim() };
    if (hasKm) payload.interval_km = intervalKm;
    if (hasDays) payload.interval_days = intervalDays;
    const lastOdo = parseInt(form.last_odometer, 10);
    if (Number.isFinite(lastOdo) && lastOdo >= 0) payload.last_odometer = lastOdo;
    if (form.last_date) payload.last_date = form.last_date;

    setSubmitting(true);
    try {
      await onSubmit(payload);
    } catch (err) {
      setError(extractError(err, 'Не вдалося створити інтервал'));
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <Input
        label="Назва"
        required
        value={form.title}
        onChange={set('title')}
        placeholder="Олива двигуна"
      />
      <div className="grid grid-cols-2 gap-3">
        <Input
          label="Інтервал, км"
          type="number"
          inputMode="numeric"
          min="0"
          value={form.interval_km}
          onChange={set('interval_km')}
          placeholder="10000"
        />
        <Input
          label="Інтервал, дні"
          type="number"
          inputMode="numeric"
          min="0"
          value={form.interval_days}
          onChange={set('interval_days')}
          placeholder="365"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Input
          label="Останнє ТО, км"
          type="number"
          inputMode="numeric"
          min="0"
          value={form.last_odometer}
          onChange={set('last_odometer')}
        />
        <Input label="Дата останнього ТО" type="date" value={form.last_date} onChange={set('last_date')} />
      </div>
      <ErrorMessage>{error}</ErrorMessage>
      <div className="flex gap-2">
        <Button type="submit" disabled={submitting} className="flex-1">
          {submitting ? 'Збереження…' : 'Додати інтервал'}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          Скасувати
        </Button>
      </div>
    </form>
  );
}

function TelegramCard({ onToast }) {
  const [status, setStatus] = useState(null); // null поки завантажується
  const [linkData, setLinkData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    telegramApi
      .getStatus()
      .then((data) => {
        if (!cancelled) setStatus(data);
      })
      .catch(() => {
        if (!cancelled) {
          setStatus({ linked: false });
          setError('Не вдалося завантажити статус Telegram');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleCreateCode = async () => {
    setError('');
    setBusy(true);
    try {
      const data = await telegramApi.createLinkCode();
      setLinkData(data);
    } catch (err) {
      setError(extractError(err, 'Не вдалося створити код привʼязки'));
    } finally {
      setBusy(false);
    }
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(linkData.code);
      onToast('Код скопійовано');
    } catch {
      setError('Не вдалося скопіювати код');
    }
  };

  const handleUnlink = async () => {
    const ok = window.confirm('Відвʼязати Telegram? Бот перестане надсилати нагадування.');
    if (!ok) return;
    setError('');
    setBusy(true);
    try {
      await telegramApi.unlink();
      setStatus({ linked: false });
      setLinkData(null);
      onToast('Telegram відвʼязано');
    } catch (err) {
      setError(extractError(err, 'Не вдалося відвʼязати Telegram'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
            <Send className="h-4 w-4 text-blue-500" />
            Telegram-бот
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            Нагадування про ТО та швидкі записи пробігу й витрат просто з Telegram.
          </p>
        </div>
        {status?.linked && (
          <span className="flex flex-shrink-0 items-center gap-1 rounded-full bg-emerald-600/15 px-2.5 py-1 text-xs font-medium text-emerald-400">
            <Check className="h-3 w-3" />
            Привʼязано
          </span>
        )}
      </div>

      {error && <ErrorMessage className="mt-3">{error}</ErrorMessage>}

      {status === null ? (
        <Spinner className="py-3" />
      ) : status.linked ? (
        <Button
          variant="ghost"
          onClick={handleUnlink}
          disabled={busy}
          className="mt-3 text-slate-400"
        >
          Відвʼязати
        </Button>
      ) : linkData ? (
        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5">
            <code className="min-w-0 flex-1 break-all font-mono text-xs text-slate-100">
              {linkData.code}
            </code>
            <button
              type="button"
              onClick={handleCopy}
              aria-label="Скопіювати код"
              className="flex-shrink-0 rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200"
            >
              <Copy className="h-4 w-4" />
            </button>
          </div>
          {linkData.deep_link && (
            <Button
              variant="secondary"
              onClick={() => window.open(linkData.deep_link, '_blank', 'noopener')}
              className="w-full"
            >
              <ExternalLink className="h-4 w-4" />
              Відкрити бота
            </Button>
          )}
          <p className="text-xs text-slate-500">
            Надішліть боту команду{' '}
            <span className="font-mono text-slate-300">/start {'<код>'}</span>. Код діє{' '}
            {linkData.expires_in_minutes} хвилин.
          </p>
        </div>
      ) : (
        <Button onClick={handleCreateCode} disabled={busy} className="mt-3 w-full">
          {busy ? 'Створення коду…' : 'Привʼязати Telegram'}
        </Button>
      )}
    </Card>
  );
}

export default function Garage() {
  const cars = useCarStore((s) => s.cars);
  const carsLoading = useCarStore((s) => s.carsLoading);
  const carsLoaded = useCarStore((s) => s.carsLoaded);
  const carsError = useCarStore((s) => s.carsError);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const setActiveCar = useCarStore((s) => s.setActiveCar);
  const addCar = useCarStore((s) => s.addCar);
  const editCar = useCarStore((s) => s.editCar);
  const removeCar = useCarStore((s) => s.removeCar);

  const intervals = useCarStore((s) => s.intervals);
  const intervalsLoading = useCarStore((s) => s.intervalsLoading);
  const intervalsError = useCarStore((s) => s.intervalsError);
  const fetchIntervals = useCarStore((s) => s.fetchIntervals);
  const addInterval = useCarStore((s) => s.addInterval);
  const removeInterval = useCarStore((s) => s.removeInterval);
  const addIntervalPresets = useCarStore((s) => s.addIntervalPresets);

  const [formMode, setFormMode] = useState(null); // null | 'new' | car.id
  const [showIntervalForm, setShowIntervalForm] = useState(false);
  const [presetsLoading, setPresetsLoading] = useState(false);
  const [reportingCarId, setReportingCarId] = useState(null);
  const [toast, setToast] = useState('');
  const [actionError, setActionError] = useState('');

  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;

  useEffect(() => {
    if (activeCarId) {
      fetchIntervals().catch(() => {});
    }
  }, [activeCarId, fetchIntervals]);

  const handleAddCar = async (payload) => {
    await addCar(payload);
    setFormMode(null);
    setToast('Авто додано');
  };

  const handleEditCar = async (carId, payload) => {
    await editCar(carId, payload);
    setFormMode(null);
    setToast('Авто оновлено');
  };

  const handleDeleteCar = async (car) => {
    const ok = window.confirm(
      `Видалити ${car.brand} ${car.model}? Разом з авто буде видалено весь журнал.`
    );
    if (!ok) return;
    setActionError('');
    try {
      await removeCar(car.id);
      setToast('Авто видалено');
    } catch (err) {
      setActionError(extractError(err, 'Не вдалося видалити авто'));
    }
  };

  const handleAddInterval = async (payload) => {
    await addInterval(payload);
    setShowIntervalForm(false);
    setToast('Інтервал додано');
  };

  const handleDeleteInterval = async (interval) => {
    const ok = window.confirm(`Видалити інтервал «${interval.title}»?`);
    if (!ok) return;
    setActionError('');
    try {
      await removeInterval(interval.id);
    } catch (err) {
      setActionError(extractError(err, 'Не вдалося видалити інтервал'));
    }
  };

  const handleDownloadReport = async (car) => {
    if (reportingCarId != null) return;
    setActionError('');
    setReportingCarId(car.id);
    try {
      await downloadCarReport(car.id);
      setToast('Звіт PDF завантажено');
    } catch (err) {
      setActionError(extractError(err, 'Не вдалося сформувати PDF-звіт'));
    } finally {
      setReportingCarId(null);
    }
  };

  const handlePresets = async () => {
    if (!activeCar) return;
    setActionError('');
    setPresetsLoading(true);
    try {
      await addIntervalPresets(activeCar);
      setToast('Типові інтервали створено');
    } catch (err) {
      setActionError(extractError(err, 'Не вдалося створити типові інтервали'));
    } finally {
      setPresetsLoading(false);
    }
  };

  if (carsLoading && !carsLoaded) return <Spinner />;

  return (
    <div className="space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />

      <div className="flex items-center justify-between px-1">
        <h1 className="text-lg font-semibold text-white">Гараж</h1>
        {formMode !== 'new' && (
          <Button variant="secondary" onClick={() => setFormMode('new')} className="px-3 py-1.5">
            <Plus className="h-4 w-4" />
            Додати авто
          </Button>
        )}
      </div>

      {carsError && <ErrorMessage>{carsError}</ErrorMessage>}
      {actionError && <ErrorMessage>{actionError}</ErrorMessage>}

      {formMode === 'new' && (
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-white">Нове авто</h2>
          <CarForm onSubmit={handleAddCar} onCancel={() => setFormMode(null)} />
        </Card>
      )}

      {carsLoaded && cars.length === 0 && formMode !== 'new' && (
        <Card className="flex flex-col items-center gap-3 p-8 text-center">
          <Car className="h-8 w-8 text-slate-600" />
          <p className="text-sm text-slate-400">У гаражі поки порожньо. Додайте своє перше авто.</p>
        </Card>
      )}

      {cars.map((car) => {
        const isActive = String(car.id) === String(activeCarId);
        const isEditing = formMode === car.id;
        return (
          <Card
            key={car.id}
            className={isActive ? 'border-blue-600/60 ring-1 ring-blue-600/40' : ''}
          >
            {isEditing ? (
              <>
                <h2 className="mb-3 text-sm font-semibold text-white">Редагувати авто</h2>
                <CarForm
                  initial={car}
                  onSubmit={(payload) => handleEditCar(car.id, payload)}
                  onCancel={() => setFormMode(null)}
                />
              </>
            ) : (
              <>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-base font-semibold text-white">
                      {car.brand} {car.model}
                      {car.generation ? ` ${car.generation}` : ''}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {car.year} · {car.engine ? `${car.engine} · ` : ''}
                      {fuelLabel(car.fuel_type)}
                    </p>
                  </div>
                  {isActive && (
                    <span className="flex items-center gap-1 rounded-full bg-blue-600/15 px-2.5 py-1 text-xs font-medium text-blue-400">
                      <Check className="h-3 w-3" />
                      Активне
                    </span>
                  )}
                </div>
                <div className="mt-3 flex items-center gap-1.5 text-sm text-slate-300">
                  <Gauge className="h-4 w-4 text-slate-500" />
                  {formatKm(car.current_odometer)}
                  <span className="ml-2 text-xs text-slate-600">
                    ≈ {Math.round(car.avg_daily_km)} км/день
                  </span>
                </div>
                <div className="mt-3 flex gap-2">
                  {!isActive && (
                    <Button
                      variant="secondary"
                      onClick={() => setActiveCar(car.id)}
                      className="flex-1 py-2"
                    >
                      Зробити активним
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    onClick={() => handleDownloadReport(car)}
                    disabled={reportingCarId != null}
                    aria-label="Завантажити звіт PDF"
                    title="Звіт PDF"
                    className="px-3 py-2"
                  >
                    {String(reportingCarId) === String(car.id) ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <FileDown className="h-4 w-4" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => setFormMode(car.id)}
                    aria-label="Редагувати авто"
                    className="px-3 py-2"
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="danger"
                    onClick={() => handleDeleteCar(car)}
                    aria-label="Видалити авто"
                    className="px-3 py-2"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </>
            )}
          </Card>
        );
      })}

      {activeCar && (
        <Card>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-white">
              Інтервали ТО · {activeCar.brand} {activeCar.model}
            </h2>
            {!showIntervalForm && (
              <Button
                variant="ghost"
                onClick={() => setShowIntervalForm(true)}
                className="px-2.5 py-1.5 text-blue-500"
              >
                <Plus className="h-4 w-4" />
                Додати
              </Button>
            )}
          </div>

          {intervalsError && <ErrorMessage className="mb-2">{intervalsError}</ErrorMessage>}

          {showIntervalForm && (
            <div className="mb-3 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
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
              <p className="mb-3 text-sm text-slate-500">
                Немає інтервалів обслуговування. Створіть власні або скористайтеся типовим набором.
              </p>
              <Button
                variant="secondary"
                onClick={handlePresets}
                disabled={presetsLoading}
                className="w-full"
              >
                <Sparkles className="h-4 w-4" />
                {presetsLoading ? 'Створення…' : 'Створити типові інтервали'}
              </Button>
            </div>
          ) : (
            <>
              <div className="divide-y divide-slate-800">
                {intervals.map((interval) => (
                  <div key={interval.id} className="flex items-start justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <p className={`text-sm font-medium ${STATUS_TEXT[interval.status] || 'text-slate-100'}`}>
                        {interval.title}
                      </p>
                      <p className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500">
                        {interval.interval_km != null && (
                          <span className="flex items-center gap-1">
                            <Gauge className="h-3 w-3" />
                            кожні {formatKm(interval.interval_km)}
                          </span>
                        )}
                        {interval.interval_days != null && (
                          <span className="flex items-center gap-1">
                            <CalendarDays className="h-3 w-3" />
                            кожні {interval.interval_days} дн.
                          </span>
                        )}
                      </p>
                      <p className="mt-0.5 text-xs text-slate-600">
                        Останнє:{' '}
                        {interval.last_odometer != null ? formatKm(interval.last_odometer) : '—'} ·{' '}
                        {formatDate(interval.last_date)}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteInterval(interval)}
                      aria-label={`Видалити інтервал ${interval.title}`}
                      className="rounded-lg p-1.5 text-slate-600 transition-colors hover:bg-red-950/50 hover:text-red-400"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
              <Button
                variant="ghost"
                onClick={handlePresets}
                disabled={presetsLoading}
                className="mt-1 w-full text-slate-400"
              >
                <Sparkles className="h-4 w-4" />
                {presetsLoading ? 'Створення…' : 'Додати типовий набір інтервалів'}
              </Button>
            </>
          )}
        </Card>
      )}

      <TelegramCard onToast={setToast} />
    </div>
  );
}
