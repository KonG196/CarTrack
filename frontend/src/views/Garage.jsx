import { useEffect, useRef, useState } from 'react';
import {
  Car,
  Plus,
  Pencil,
  Trash2,
  Check,
  CheckCircle2,
  Gauge,
  CalendarDays,
  Sparkles,
  ShieldCheck,
  Send,
  Copy,
  ExternalLink,
  FileDown,
  FileSpreadsheet,
  Loader2,
  Database,
  Upload,
  Activity,
  Wrench,
  UserCircle,
} from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useCarStore } from '../store/carStore';
import { useAuthStore } from '../store/authStore';
import { extractError } from '../api/client';
import { downloadCarReport } from '../api/reports';
import { getIntervalPresets } from '../api/intervals';
import * as backupApi from '../api/backup';
import * as telegramApi from '../api/telegram';
import { formatKm, formatDate } from '../utils/format';
import { canDo, roleLabel } from '../utils/permissions';
import { Button, TextField, SelectField, Card, Spinner, ErrorMessage, ConfirmDialog } from '../components/UI';
import Toast from '../components/Toast';
import CompleteIntervalModal from '../components/CompleteIntervalModal';
import DocumentsCard from '../components/DocumentsCard';
import SharingCard from '../components/SharingCard';
import TiresCard from '../components/TiresCard';

const FUEL_TYPES = [
  { value: 'petrol', label: 'Бензин' },
  { value: 'diesel', label: 'Дизель' },
  { value: 'lpg', label: 'ГБО' },
  { value: 'electric', label: 'Електро' },
  { value: 'hybrid', label: 'Гібрид' },
];

const fuelLabel = (value) => FUEL_TYPES.find((f) => f.value === value)?.label || value;

// Colour is reserved for what needs attention: "ok" gets none, otherwise amber
// stops meaning anything.
const STATUS_TEXT = {
  ok: 'text-fg',
  due_soon: 'text-amber',
  overdue: 'text-crit',
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
    tank_liters: initial?.tank_liters != null ? String(initial.tank_liters) : '',
    monthly_budget: initial?.monthly_budget != null ? String(initial.monthly_budget) : '',
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

    // Empty means "not set" (null), not zero: zero is meaningless for both the
    // tank and the budget, and the backend rejects it anyway.
    const tank = form.tank_liters.trim() ? Number(form.tank_liters) : null;
    if (tank !== null && (!Number.isFinite(tank) || tank <= 0))
      return setError('Вкажіть коректний обʼєм бака');
    const budget = form.monthly_budget.trim() ? Number(form.monthly_budget) : null;
    if (budget !== null && (!Number.isFinite(budget) || budget <= 0))
      return setError('Вкажіть коректний бюджет');

    const payload = {
      brand: form.brand.trim(),
      model: form.model.trim(),
      generation: form.generation.trim() || null,
      engine: form.engine.trim() || null,
      year,
      fuel_type: form.fuel_type,
      current_odometer: odometer,
      tank_liters: tank,
      monthly_budget: budget,
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
        <TextField label="Марка" required value={form.brand} onChange={set('brand')} />
        <TextField label="Модель" required value={form.model} onChange={set('model')} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <TextField label="Покоління" value={form.generation} onChange={set('generation')} />
        <TextField label="Двигун" value={form.engine} onChange={set('engine')} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <TextField
          label="Рік"
          type="number"
          inputMode="numeric"
          enterKeyHint="next"
          numeric
          required
          value={form.year}
          onChange={set('year')}
        />
        <SelectField
          label="Пальне"
          value={form.fuel_type}
          onChange={set('fuel_type')}
          options={FUEL_TYPES}
        />
      </div>
      <TextField
        label="Поточний пробіг, км"
        type="number"
        inputMode="numeric"
        enterKeyHint="done"
        min="0"
        numeric
        required
        value={form.current_odometer}
        onChange={set('current_odometer')}
      />
      {/* Hints go through `hint`, not `placeholder`: TextField's placeholder is
          occupied (' ') — the floating label depends on it. */}
      <div className="grid grid-cols-2 gap-3">
        <TextField
          label="Обʼєм бака, л"
          hint="напр. 50"
          type="number"
          inputMode="decimal"
          enterKeyHint="next"
          min="0"
          step="0.1"
          numeric
          value={form.tank_liters}
          onChange={set('tank_liters')}
        />
        <TextField
          label="Бюджет на місяць, ₴"
          hint="напр. 5000"
          type="number"
          inputMode="decimal"
          enterKeyHint="done"
          min="0"
          step="100"
          numeric
          value={form.monthly_budget}
          onChange={set('monthly_budget')}
        />
      </div>
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

function IntervalForm({ car, initial, onSubmit, onCancel }) {
  const [form, setForm] = useState({
    title: initial?.title || '',
    interval_km: initial?.interval_km != null ? String(initial.interval_km) : '',
    interval_days: initial?.interval_days != null ? String(initial.interval_days) : '',
    last_odometer:
      initial != null
        ? initial.last_odometer != null
          ? String(initial.last_odometer)
          : ''
        : car
          ? String(car.current_odometer)
          : '',
    last_date: initial ? initial.last_date || '' : new Date().toISOString().slice(0, 10),
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
        extractError(err, initial ? 'Не вдалося зберегти інтервал' : 'Не вдалося створити інтервал')
      );
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <TextField
        label="Назва"
        required
        value={form.title}
        onChange={set('title')}
      />
      <div className="grid grid-cols-2 gap-3">
        <TextField
          label="Інтервал, км"
          type="number"
          inputMode="numeric"
          enterKeyHint="next"
          min="0"
          numeric
          value={form.interval_km}
          onChange={set('interval_km')}
        />
        <TextField
          label="Інтервал, дні"
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
          label="Останнє ТО, км"
          type="number"
          inputMode="numeric"
          enterKeyHint="next"
          min="0"
          numeric
          value={form.last_odometer}
          onChange={set('last_odometer')}
        />
        <TextField label="Дата останнього ТО" type="date" value={form.last_date} onChange={set('last_date')} />
      </div>
      <ErrorMessage>{error}</ErrorMessage>
      <div className="flex gap-2">
        <Button type="submit" disabled={submitting} className="flex-1">
          {submitting ? 'Збереження…' : initial ? 'Зберегти зміни' : 'Додати інтервал'}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          Скасувати
        </Button>
      </div>
    </form>
  );
}

const PRESET_GROUPS = {
  maintenance: {
    icon: Sparkles,
    label: 'Типові інтервали ТО',
    toast: 'Типові інтервали створено',
    error: 'Не вдалося створити типові інтервали',
  },
  compliance: {
    icon: ShieldCheck,
    label: 'Страховки та документи',
    toast: 'Страховки та документи створено',
    error: 'Не вдалося створити страховки та документи',
  },
};

function PresetButtons({ variant, className = '', loadingGroup, onPresets }) {
  return (
    <div className={`grid grid-cols-2 gap-2 ${className}`}>
      {Object.entries(PRESET_GROUPS).map(([group, { icon: Icon, label }]) => (
        <Button
          key={group}
          variant={variant}
          onClick={() => onPresets(group)}
          disabled={loadingGroup !== null}
          className="w-full"
        >
          <Icon className="h-4 w-4" />
          {loadingGroup === group ? 'Створення…' : label}
        </Button>
      ))}
    </div>
  );
}

/**
 * Lives on this screen rather than a separate profile: the name only affects how
 * you appear to other members of a car, and access management is here too.
 */
function ProfileCard({ onToast }) {
  const user = useAuthStore((s) => s.user);
  const saveDisplayName = useAuthStore((s) => s.saveDisplayName);

  // null means untouched, so we show the saved value. The profile arrives
  // asynchronously: seeding state from it via an effect would blank the field
  // and clobber whatever the user had already typed.
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const saved = user?.display_name || '';
  const value = draft ?? saved;
  const dirty = draft !== null && draft.trim() !== saved;

  const emailPrefix = (user?.email || '').split('@')[0];

  const handleSave = async (e) => {
    e.preventDefault();
    const name = value.trim();
    if (!name) return setError('Вкажіть імʼя');
    setError('');
    setSaving(true);
    try {
      await saveDisplayName(name);
      setDraft(null);
      onToast('Імʼя збережено');
    } catch (err) {
      setError(extractError(err, 'Не вдалося зберегти імʼя'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <div>
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
          <UserCircle className="h-4 w-4 text-mist" />
          Ваше імʼя
        </h2>
        <p className="mt-1 text-xs text-mist">
          Так вас підписано під записами у спільних авто. Без імені — {emailPrefix || 'початок email'}.
        </p>
      </div>

      {error && <ErrorMessage className="mt-3">{error}</ErrorMessage>}

      <form onSubmit={handleSave} className="mt-3 flex items-end gap-2">
        <TextField
          label="Імʼя"
          maxLength={80}
          value={value}
          onChange={(e) => setDraft(e.target.value)}
          containerClassName="flex-1"
        />
        <Button type="submit" disabled={saving || !dirty} className="flex-shrink-0">
          {saving ? 'Збереження…' : 'Зберегти'}
        </Button>
      </form>
    </Card>
  );
}

function TelegramCard({ onToast }) {
  const [status, setStatus] = useState(null);
  const [linkData, setLinkData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
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
    setConfirmUnlink(false);
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
          <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
            <Send className="h-4 w-4 text-signal" />
            Telegram-бот
          </h2>
          <p className="mt-1 text-xs text-mist">
            Нагадування про ТО та швидкі записи пробігу й витрат просто з Telegram.
          </p>
        </div>
        {status?.linked && (
          <span className="flex flex-shrink-0 items-center gap-1 rounded-full bg-ok/15 px-2.5 py-1 text-xs font-medium text-ok">
            <Check className="h-3 w-3" />
            Привʼязано
          </span>
        )}
      </div>

      {error && <ErrorMessage className="mt-3">{error}</ErrorMessage>}

      {status === null ? (
        <Spinner className="py-3" />
      ) : status.linked ? (
        <>
          <Button
            variant="ghost"
            onClick={() => setConfirmUnlink(true)}
            disabled={busy}
            className="mt-3 text-mist"
          >
            Відвʼязати
          </Button>
          <ConfirmDialog
            open={confirmUnlink}
            title="Відвʼязати Telegram?"
            message="Відвʼязати Telegram? Бот перестане надсилати нагадування."
            confirmLabel="Відвʼязати"
            onConfirm={handleUnlink}
            onCancel={() => setConfirmUnlink(false)}
          />
        </>
      ) : linkData ? (
        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-2 rounded-xl border border-edge-soft bg-garage px-3.5 py-2.5">
            <code className="min-w-0 flex-1 break-all font-mono text-xs text-fg">
              {linkData.code}
            </code>
            <button
              type="button"
              onClick={handleCopy}
              aria-label="Скопіювати код"
              className="flex-shrink-0 rounded-lg p-1.5 text-mist transition-colors hover:bg-raised hover:text-fg"
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
          <p className="text-xs text-mist">
            Надішліть боту команду{' '}
            <span className="font-mono text-fg">/start {'<код>'}</span>. Код діє{' '}
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

function DataCard({ onToast, onImported }) {
  const fileInputRef = useRef(null);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [pendingImport, setPendingImport] = useState(null); // {payload, counts}
  const [error, setError] = useState('');

  const handleExport = async () => {
    setError('');
    setExporting(true);
    try {
      await backupApi.downloadExport();
      onToast('Експорт JSON завантажено');
    } catch (err) {
      setError(extractError(err, 'Не вдалося експортувати дані'));
    } finally {
      setExporting(false);
    }
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // lets the same file be picked again
    if (!file) return;
    setError('');
    try {
      const payload = JSON.parse(await file.text());
      const counts = backupApi.summarizeImport(payload);
      setPendingImport({ payload, counts });
    } catch (err) {
      setError(
        err instanceof SyntaxError
          ? 'Не вдалося прочитати файл: це не JSON'
          : err.message || 'Файл не схожий на експорт Kapot Tracker'
      );
    }
  };

  const confirmImport = async () => {
    const pending = pendingImport;
    setPendingImport(null);
    if (!pending) return;
    setError('');
    setImporting(true);
    try {
      const result = await backupApi.importBackup(pending.payload);
      onToast(
        `Імпортовано: ${result.cars_created} авто, ${result.logs_created} записів, ${result.intervals_created} інтервалів`
      );
      await onImported();
    } catch (err) {
      setError(extractError(err, 'Не вдалося імпортувати дані'));
    } finally {
      setImporting(false);
    }
  };

  return (
    <Card>
      <div>
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
          <Database className="h-4 w-4 text-mist" />
          Дані
        </h2>
        <p className="mt-1 text-xs text-mist">
          Резервна копія гаража: експорт у JSON та відновлення з файлу. Фото до експорту не входять.
        </p>
      </div>

      {error && <ErrorMessage className="mt-3">{error}</ErrorMessage>}

      <div className="mt-3 space-y-2">
        <Button
          variant="secondary"
          onClick={handleExport}
          disabled={exporting || importing}
          className="w-full"
        >
          {exporting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FileDown className="h-4 w-4" />
          )}
          {exporting ? 'Експорт…' : 'Експортувати все (JSON)'}
        </Button>
        <Button
          variant="secondary"
          onClick={() => fileInputRef.current?.click()}
          disabled={exporting || importing}
          className="w-full"
        >
          {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {importing ? 'Імпорт…' : 'Імпортувати з файлу'}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json,.json"
          onChange={handleFileChange}
          className="hidden"
          aria-label="Файл експорту JSON"
        />
      </div>

      <ConfirmDialog
        open={pendingImport !== null}
        title="Імпортувати дані?"
        message={
          pendingImport
            ? `Буде додано: ${pendingImport.counts.cars} авто, ${pendingImport.counts.logs} записів, ${pendingImport.counts.intervals} інтервалів. Наявні дані не зміняться.`
            : ''
        }
        confirmLabel="Імпортувати"
        danger={false}
        onConfirm={confirmImport}
        onCancel={() => setPendingImport(null)}
      />
    </Card>
  );
}

// Diagnostics is entered from here, not the bottom nav: that has exactly 5 slots
// around a central round button, and a sixth would push it off-centre.
function DiagnosticsCard() {
  const navigate = useNavigate();

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
            <Activity className="h-4 w-4 text-amber" />
            Діагностика OBD
          </h2>
          <p className="mt-1 text-xs text-mist">
            Імпорт CSV-логу з Car Scanner: сажа DPF, корекції форсунок, напруга АКБ.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => navigate('/diagnostics')}
          className="flex-shrink-0 px-3 py-1.5"
        >
          Відкрити
        </Button>
      </div>
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
  const fetchCars = useCarStore((s) => s.fetchCars);
  const addCar = useCarStore((s) => s.addCar);
  const editCar = useCarStore((s) => s.editCar);
  const removeCar = useCarStore((s) => s.removeCar);

  const intervals = useCarStore((s) => s.intervals);
  const intervalsLoading = useCarStore((s) => s.intervalsLoading);
  const intervalsError = useCarStore((s) => s.intervalsError);
  const fetchIntervals = useCarStore((s) => s.fetchIntervals);
  const addInterval = useCarStore((s) => s.addInterval);
  const editInterval = useCarStore((s) => s.editInterval);
  const removeInterval = useCarStore((s) => s.removeInterval);
  const addIntervalPresets = useCarStore((s) => s.addIntervalPresets);
  const completeInterval = useCarStore((s) => s.completeInterval);

  const [formMode, setFormMode] = useState(null); // null | 'new' | car.id
  const [deletingCar, setDeletingCar] = useState(null);
  const [deletingInterval, setDeletingInterval] = useState(null);
  const [completingInterval, setCompletingInterval] = useState(null);
  const [showIntervalForm, setShowIntervalForm] = useState(false);
  const [editingIntervalId, setEditingIntervalId] = useState(null);
  const [presetsLoading, setPresetsLoading] = useState(null); // null | PRESET_GROUPS key
  const [reportingCarId, setReportingCarId] = useState(null);
  const [csvCarId, setCsvCarId] = useState(null);
  const location = useLocation();
  const navigate = useNavigate();
  const [toast, setToast] = useState(location.state?.toast || '');
  const [actionError, setActionError] = useState('');

  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;
  // Intervals are the owner's regimen; an editor may still close a completed one.
  const canManageIntervals = canDo(activeCar?.your_role, 'interval:manage');
  const canCompleteIntervals = canDo(activeCar?.your_role, 'interval:complete');

  // /join/:token delivers this toast via navigation state. Strip it from history,
  // otherwise it reappears on every back navigation.
  const clearToast = () => {
    setToast('');
    if (location.state?.toast) navigate(location.pathname, { replace: true, state: null });
  };

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

  const confirmDeleteCar = async () => {
    const car = deletingCar;
    setDeletingCar(null);
    if (!car) return;
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

  const handleEditInterval = async (intervalId, payload) => {
    await editInterval(intervalId, payload);
    setEditingIntervalId(null);
    setToast('Інтервал оновлено');
  };

  const confirmDeleteInterval = async () => {
    const interval = deletingInterval;
    setDeletingInterval(null);
    if (!interval) return;
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

  const handleDownloadCsv = async (car) => {
    if (csvCarId != null) return;
    setActionError('');
    setCsvCarId(car.id);
    try {
      await backupApi.downloadCarCsv(car.id);
      setToast('CSV журналу завантажено');
    } catch (err) {
      setActionError(extractError(err, 'Не вдалося завантажити CSV журналу'));
    } finally {
      setCsvCarId(null);
    }
  };

  const handlePresets = async (group) => {
    if (!activeCar || presetsLoading) return;
    setActionError('');
    setPresetsLoading(group);
    try {
      const presets = await getIntervalPresets();
      await addIntervalPresets(activeCar, presets[group] || []);
      setToast(PRESET_GROUPS[group].toast);
    } catch (err) {
      setActionError(extractError(err, PRESET_GROUPS[group].error));
    } finally {
      setPresetsLoading(null);
    }
  };

  if (carsLoading && !carsLoaded) return <Spinner />;

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} onDone={clearToast} />

      <ConfirmDialog
        open={deletingCar !== null}
        title="Видалити авто?"
        message={
          deletingCar
            ? `Видалити ${deletingCar.brand} ${deletingCar.model}? Разом з авто буде видалено весь журнал.`
            : ''
        }
        onConfirm={confirmDeleteCar}
        onCancel={() => setDeletingCar(null)}
      />

      <ConfirmDialog
        open={deletingInterval !== null}
        title="Видалити інтервал?"
        message={deletingInterval ? `Видалити інтервал «${deletingInterval.title}»?` : ''}
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

      <div className="flex items-center justify-between px-1">
        <h1 className="font-display text-lg font-semibold text-fg">Гараж</h1>
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
          <h2 className="mb-3 font-display text-sm font-semibold text-fg">Нове авто</h2>
          <CarForm onSubmit={handleAddCar} onCancel={() => setFormMode(null)} />
        </Card>
      )}

      {carsLoaded && cars.length === 0 && formMode !== 'new' && (
        <Card className="flex flex-col items-center gap-3 p-8 text-center">
          <Car className="h-8 w-8 text-mist/70" />
          <p className="text-sm text-mist">У гаражі поки порожньо. Додайте своє перше авто.</p>
        </Card>
      )}

      {cars.map((car) => {
        const isActive = String(car.id) === String(activeCarId);
        const isEditing = formMode === car.id;
        const isOwner = canDo(car.your_role, 'car:edit');
        return (
          <Card
            key={car.id}
            className={isActive ? 'border-amber/50 ring-1 ring-amber/30' : ''}
          >
            {isEditing ? (
              <>
                <h2 className="mb-3 font-display text-sm font-semibold text-fg">Редагувати авто</h2>
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
                    <p className="text-base font-semibold text-fg">
                      {car.brand} {car.model}
                      {car.generation ? ` ${car.generation}` : ''}
                    </p>
                    <p className="mt-0.5 text-xs text-mist">
                      {car.year} · {car.engine ? `${car.engine} · ` : ''}
                      {fuelLabel(car.fuel_type)}
                    </p>
                  </div>
                  <div className="flex flex-shrink-0 items-center gap-1.5">
                    {!isOwner && (
                      <span className="flex items-center gap-1 rounded-full bg-signal/15 px-2.5 py-1 text-xs font-medium text-signal">
                        {roleLabel(car.your_role)}
                      </span>
                    )}
                    {isActive && (
                      <span className="flex items-center gap-1 rounded-full bg-amber/15 px-2.5 py-1 text-xs font-medium text-amber">
                        <Check className="h-3 w-3" />
                        Активне
                      </span>
                    )}
                  </div>
                </div>
                <div className="mt-3 flex items-center gap-1.5 text-sm text-fg">
                  <Gauge className="h-4 w-4 text-mist" />
                  {formatKm(car.current_odometer)}
                  <span className="ml-2 text-xs text-mist/70">
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
                    onClick={() => navigate(`/garage/${car.id}/specs`)}
                    aria-label="Тех. довідка"
                    title="Тех. довідка"
                    className="px-3 py-2"
                  >
                    <Wrench className="h-4 w-4" />
                  </Button>
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
                    onClick={() => handleDownloadCsv(car)}
                    disabled={csvCarId != null}
                    aria-label="Завантажити CSV журналу"
                    title="CSV журналу"
                    className="px-3 py-2"
                  >
                    {String(csvCarId) === String(car.id) ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <FileSpreadsheet className="h-4 w-4" />
                    )}
                  </Button>
                  {isOwner && (
                    <>
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
                        onClick={() => setDeletingCar(car)}
                        aria-label="Видалити авто"
                        className="px-3 py-2"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                </div>
              </>
            )}
          </Card>
        );
      })}

      {activeCar && (
        <Card>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h2 className="font-display text-sm font-semibold text-fg">
              Інтервали ТО · {activeCar.brand} {activeCar.model}
            </h2>
            {!showIntervalForm && canManageIntervals && (
              <Button
                variant="ghost"
                onClick={() => setShowIntervalForm(true)}
                className="px-2.5 py-1.5 text-amber"
              >
                <Plus className="h-4 w-4" />
                Додати
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
                  ? 'Немає інтервалів обслуговування. Створіть власні або скористайтеся типовим набором.'
                  : 'Власник ще не додав інтервалів обслуговування.'}
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
                      <div className="min-w-0">
                        <p className={`text-sm font-medium ${STATUS_TEXT[interval.status] || 'text-fg'}`}>
                          {interval.title}
                        </p>
                        <p className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-mist">
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
                        <p className="mt-0.5 text-xs text-mist/70">
                          Останнє:{' '}
                          {interval.last_odometer != null ? formatKm(interval.last_odometer) : '—'} ·{' '}
                          {formatDate(interval.last_date)}
                        </p>
                      </div>
                      <div className="flex flex-shrink-0 items-center">
                        {canCompleteIntervals && (
                          <button
                            type="button"
                            onClick={() => setCompletingInterval(interval)}
                            aria-label={`Виконано: ${interval.title}`}
                            title="Виконано"
                            className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-ok/10 hover:text-ok"
                          >
                            <CheckCircle2 className="h-4 w-4" />
                          </button>
                        )}
                        {canManageIntervals && (
                          <>
                            <button
                              type="button"
                              onClick={() => setEditingIntervalId(interval.id)}
                              aria-label={`Редагувати інтервал ${interval.title}`}
                              className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-raised hover:text-fg"
                            >
                              <Pencil className="h-4 w-4" />
                            </button>
                            <button
                              type="button"
                              onClick={() => setDeletingInterval(interval)}
                              aria-label={`Видалити інтервал ${interval.title}`}
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
              {canManageIntervals && (
                <PresetButtons
                  variant="ghost"
                  className="mt-1"
                  loadingGroup={presetsLoading}
                  onPresets={handlePresets}
                />
              )}
            </>
          )}
        </Card>
      )}

      {activeCar && <SharingCard key={`sharing-${activeCar.id}`} car={activeCar} onToast={setToast} />}

      {activeCar && (
        <DocumentsCard
          key={activeCar.id}
          car={activeCar}
          onToast={setToast}
          onIntervalLinked={() => fetchIntervals().catch(() => {})}
        />
      )}

      {activeCar && (
        <TiresCard key={`tires-${activeCar.id}`} car={activeCar} onToast={setToast} />
      )}

      {activeCar && <DiagnosticsCard />}

      <ProfileCard onToast={setToast} />

      <TelegramCard onToast={setToast} />

      <DataCard onToast={setToast} onImported={() => fetchCars().catch(() => {})} />
    </div>
  );
}
