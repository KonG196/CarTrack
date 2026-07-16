import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Loader2, Search } from 'lucide-react';

import { extractError } from '../api/client';
import { lookupPlate } from '../api/cars';
import { Button, Card, DateField, ErrorMessage, SelectField, TextField } from '../components/UI';
import BackLink from '../components/BackLink';
import { useCarStore } from '../store/carStore';

export const FUEL_TYPES = [
  { value: 'petrol', label: 'Бензин' },
  { value: 'diesel', label: 'Дизель' },
  { value: 'lpg', label: 'ГБО' },
  { value: 'electric', label: 'Електро' },
  { value: 'hybrid', label: 'Гібрид' },
];

function CarForm({ initial, onSubmit, onCancel, focusField }) {
  const odometerRef = useRef(null);

  // Reached here from the odometer pencil on the dashboard: land in the field
  // with its value selected, so a new reading overwrites the old with one tap
  // and no cursor-wrangling. Focus alone already turns the border amber.
  useEffect(() => {
    if (focusField !== 'odometer' || !odometerRef.current) return;
    const el = odometerRef.current;
    el.focus();
    el.select?.();
    el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [focusField]);

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
    vin: initial?.vin || '',
    plate: initial?.plate || '',
    scratchpad: initial?.scratchpad || '',
    contact_phone: initial?.contact_phone || '',
    insurance_number: initial?.insurance_number || '',
    insurance_until: initial?.insurance_until || '',
    tire_pressure: initial?.tire_pressure || '',
    fuel_approval: initial?.fuel_approval || '',
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [looking, setLooking] = useState(false);
  const [lookupNote, setLookupNote] = useState('');
  const [stolen, setStolen] = useState(null);
  // Which fields the register filled, so they can say so. Cleared per field the
  // moment the user edits it: the green mark claims «you did not type this»,
  // and it has to stop claiming that the instant it stops being true.
  const [autofilled, setAutofilled] = useState({});
  // Bumped on every lookup. A CSS animation does not replay while its class
  // stays put, so a second lookup would leave the already-green fields silent;
  // keying them on this nonce remounts them and the pulse fires every time.
  const [lookupNonce, setLookupNonce] = useState(0);

  const set = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }));
    setAutofilled((a) => (a[key] ? { ...a, [key]: false } : a));
  };

  const autoClass = (key) => (autofilled[key] ? 'autofilled' : '');
  const autoKey = (key) => `${key}-${lookupNonce}`;

  // Enter in the plate or VIN field runs the lookup, not the form's submit.
  // Both live inside the <form>, so Enter would otherwise save a half-empty
  // car — the opposite of what someone typing a plate to search wants.
  const onLookupEnter = (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    if (!looking && (form.plate.trim() || form.vin.trim())) handleLookup();
  };

  const handleLookup = async () => {
    const query = (form.plate || form.vin).trim();
    if (!query) return setError('Вкажіть держномер або VIN');
    setError('');
    setLookupNote('');
    setStolen(null);
    setLooking(true);
    try {
      const found = await lookupPlate(query, !form.plate.trim());
      // Only fills what the register knows; a blank field there must not wipe
      // what the owner already typed.
      const filled = {
        brand: found.brand || null,
        model: found.model || null,
        year: found.year != null ? String(found.year) : null,
        engine: found.engine || null,
        fuel_type: found.fuel_type || null,
        vin: found.vin || null,
        plate: found.plate || null,
      };
      setForm((f) => ({
        ...f,
        ...Object.fromEntries(
          Object.entries(filled).filter(([, value]) => value !== null)
        ),
      }));
      setAutofilled(
        Object.fromEntries(
          Object.entries(filled).map(([key, value]) => [key, value !== null])
        )
      );
      setLookupNonce((n) => n + 1);
      setStolen(found.is_stolen);
      const bits = [found.color, found.last_registered_at && `реєстрація ${found.last_registered_at}`]
        .filter(Boolean)
        .join(' · ');
      setLookupNote(bits ? `Знайдено: ${bits}` : 'Знайдено в реєстрі');
    } catch (err) {
      setError(extractError(err, 'Не вдалося знайти авто'));
    } finally {
      setLooking(false);
    }
  };

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
      vin: form.vin.trim().toUpperCase() || null,
      plate: form.plate.trim().toUpperCase() || null,
      scratchpad: form.scratchpad.trim() || null,
      contact_phone: form.contact_phone.trim() || null,
      insurance_number: form.insurance_number.trim() || null,
      insurance_until: form.insurance_until || null,
      tire_pressure: form.tire_pressure.trim() || null,
      fuel_approval: form.fuel_approval.trim() || null,
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
      {/* The plate goes first, and the button sits on it. Buried under «Марка»
          and «Модель» this read as one more optional field, so the fastest way
          to add a car — type eight characters and let the register do the rest —
          was the one nobody found. Everything below is what it fills in. */}
      <div className="rounded-2xl border border-edge-soft bg-raised/40 p-3">
        <div className="flex items-end gap-2">
          <TextField
            key={autoKey('plate')}
            label="Держномер"
            containerClassName={`flex-1 ${autoClass('plate')}`}
            value={form.plate}
            onChange={set('plate')}
            enterKeyHint="search"
            onKeyDown={onLookupEnter}
          />
          <Button
            type="button"
            variant="secondary"
            onClick={handleLookup}
            disabled={looking || (!form.plate.trim() && !form.vin.trim())}
            className="h-14 flex-shrink-0 px-4"
          >
            {looking ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <span className="flex items-center gap-1.5">
                <Search className="h-4 w-4" />
                Знайти
              </span>
            )}
          </Button>
        </div>
        <p className="mt-2 text-xs text-mist">
          Знайдемо марку, модель, рік і двигун у реєстрі МВС — і перевіримо, чи не
          в розшуку. Можна й за VIN.
        </p>
        {lookupNote && <p className="mt-1.5 text-xs text-mist">{lookupNote}</p>}
        {stolen === true && (
          <p className="rounded-xl border border-crit/40 bg-crit/10 px-3 py-2 text-sm text-crit">
            🚨 Авто числиться в розшуку. Перевірте деталі перед купівлею.
          </p>
        )}
        {stolen === false && (
          <p className="mt-1.5 text-xs text-ok">✓ У розшуку не числиться</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <TextField
          key={autoKey('brand')}
          label="Марка"
          required
          containerClassName={autoClass('brand')}
          value={form.brand}
          onChange={set('brand')}
        />
        <TextField
          key={autoKey('model')}
          label="Модель"
          required
          containerClassName={autoClass('model')}
          value={form.model}
          onChange={set('model')}
        />
      </div>
      <TextField
        key={autoKey('vin')}
        label="VIN"
        containerClassName={autoClass('vin')}
        value={form.vin}
        onChange={set('vin')}
        enterKeyHint="search"
        onKeyDown={onLookupEnter}
      />
      <div className="grid grid-cols-2 gap-3">
        <TextField label="Покоління" value={form.generation} onChange={set('generation')} />
        <TextField
          key={autoKey('engine')}
          label="Двигун"
          containerClassName={autoClass('engine')}
          value={form.engine}
          onChange={set('engine')}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <TextField
          key={autoKey('year')}
          label="Рік"
          type="number"
          inputMode="numeric"
          enterKeyHint="next"
          numeric
          required
          containerClassName={autoClass('year')}
          value={form.year}
          onChange={set('year')}
        />
        <SelectField
          key={autoKey('fuel_type')}
          label="Пальне"
          containerClassName={autoClass('fuel_type')}
          value={form.fuel_type}
          onChange={set('fuel_type')}
          options={FUEL_TYPES}
        />
      </div>
      <TextField
        ref={odometerRef}
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
      <div>
        <label htmlFor="scratchpad" className="mb-1 block px-1 text-xs text-mist">
          Нотатки водія
        </label>
        <textarea
          id="scratchpad"
          rows={3}
          maxLength={2000}
          value={form.scratchpad}
          onChange={set('scratchpad')}
          placeholder="Коди воріт, телефон СТО, PIN магнітоли…"
          className="w-full resize-none rounded-xl border border-edge bg-panel px-3.5 py-2.5 text-sm text-fg placeholder:text-mist/50 focus:border-amber focus:outline-none"
        />
        <p className="mt-1 px-1 text-xs text-mist/70">
          Швидкий доступ із Telegram: команда /note
        </p>
      </div>

      <div className="rounded-xl border border-edge bg-raised/40 p-3">
        <p className="mb-1 text-sm font-medium text-fg">QR-паспорт</p>
        <p className="mb-3 text-xs text-mist">
          Дані для публічної сторінки авто (сервіс, парковка). QR генерується в Гаражі.
        </p>
        <div className="space-y-3">
          <TextField
            label="Контактний телефон"
            type="tel"
            inputMode="tel"
            hint="напр. 067 000 00 00"
            value={form.contact_phone}
            onChange={set('contact_phone')}
          />
          <div className="grid grid-cols-2 gap-3">
            <TextField
              label="ОСЦПВ, номер"
              value={form.insurance_number}
              onChange={set('insurance_number')}
            />
            <DateField
              label="ОСЦПВ, дійсна до"
              clearable
              value={form.insurance_until}
              onChange={(v) => setForm((f) => ({ ...f, insurance_until: v }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <TextField
              label="Тиск у шинах"
              hint="напр. 2.2/2.4 бар"
              value={form.tire_pressure}
              onChange={set('tire_pressure')}
            />
            <TextField
              label="Допуск пального"
              hint="напр. Дизель, EN590"
              value={form.fuel_approval}
              onChange={set('fuel_approval')}
            />
          </div>
        </div>
      </div>

      {/* Sticky action bar: always in reach above the bottom nav, so a long
          form never means scrolling to the very end to save. */}
      <div className="sticky bottom-0 z-20 -mx-4 border-t border-edge bg-garage px-4 pt-3 pb-[calc(env(safe-area-inset-bottom)+4.75rem)]">
        {error && <ErrorMessage className="mb-3">{error}</ErrorMessage>}
        <div className="flex gap-2">
          <Button type="submit" disabled={submitting} className="flex-1">
            {submitting ? 'Збереження…' : 'Зберегти'}
          </Button>
          <Button variant="secondary" onClick={onCancel}>
            Скасувати
          </Button>
        </div>
      </div>
    </form>
  );
}

// Add and edit share one page, because they are the same form with a different
// starting point. The route decides: /garage/new is a blank form, and
// /garage/:carId/edit is that car pre-filled.
export default function CarEditor() {
  const { carId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const cars = useCarStore((s) => s.cars);
  const addCar = useCarStore((s) => s.addCar);
  const editCar = useCarStore((s) => s.editCar);

  const editing = carId != null;
  const car = editing ? cars.find((c) => String(c.id) === String(carId)) : null;

  // The car list may still be loading on a hard refresh straight to the edit
  // URL. A missing car then is «not loaded yet», not «does not exist», so wait
  // rather than showing a wrong empty form.
  if (editing && !car) {
    return (
      <Card>
        <p className="text-sm text-mist">Завантаження авто…</p>
      </Card>
    );
  }

  const handleSubmit = async (payload) => {
    if (editing) {
      await editCar(car.id, payload);
    } else {
      await addCar(payload);
    }
    navigate('/garage', { state: { toast: editing ? 'Авто оновлено' : 'Авто додано' } });
  };

  return (
    <div className="stagger space-y-4">
      <BackLink to="/garage">{editing ? 'Редагувати авто' : 'Нове авто'}</BackLink>
      <Card>
        <CarForm
          initial={car}
          onSubmit={handleSubmit}
          onCancel={() => navigate('/garage')}
          focusField={searchParams.get('focus')}
        />
      </Card>
    </div>
  );
}
