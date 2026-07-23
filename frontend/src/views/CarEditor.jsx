import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Loader2, Search } from 'lucide-react';

import { extractError } from '../api/client';
import { currentCurrencySymbol } from '../store/currencyStore';
import { currentUnits } from '../store/unitStore';
import {
  isImperial,
  kmFromDistance,
  litresFromVolume,
  KM_PER_MILE,
  LITRES_PER_US_GALLON,
} from '../units';
import { distanceUnitLabel, volumeUnitLabel } from '../utils/format';
import { lookupPlate } from '../api/cars';
import { Button, Card, DateField, ErrorMessage, SelectField, TextField } from '../components/UI';
import BackLink from '../components/BackLink';
import { useCarStore } from '../store/carStore';
import { useAuthStore } from '../store/authStore';

export const FUEL_TYPES = [
  { value: 'petrol', label: 'Бензин' },
  { value: 'diesel', label: 'Дизель' },
  { value: 'lpg', label: 'ГБО' },
  { value: 'electric', label: 'Електро' },
  { value: 'hybrid', label: 'Гібрид' },
];

function CarForm({ initial, onSubmit, onCancel, focusField }) {
  const { t } = useTranslation();
  const odometerRef = useRef(null);

  // The car's odometer/tank are stored metric; the form shows and takes the
  // user's display units and converts back on save.
  const imperial = isImperial(currentUnits());
  const toDisplayDistance = (km) => (imperial ? Math.round(km / KM_PER_MILE) : km);
  const toDisplayVolume = (l) => (imperial ? +(l / LITRES_PER_US_GALLON).toFixed(1) : l);

  const fuelOptions = FUEL_TYPES.map((f) => ({
    value: f.value,
    label: t(`carEditor.fuelType.${f.value}`),
  }));

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
    current_odometer:
      initial?.current_odometer != null ? String(toDisplayDistance(initial.current_odometer)) : '',
    tank_liters: initial?.tank_liters != null ? String(toDisplayVolume(initial.tank_liters)) : '',
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
  // Plate lookup calls the paid baza-gai API, so it stays behind a verified
  // email. false only for a genuinely unverified account; undefined must not lock.
  const lookupLocked = useAuthStore((s) => s.user?.email_verified) === false;
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
    if (lookupLocked) return setError(t('carEditor.lookupNeedsVerify'));
    const query = (form.plate || form.vin).trim();
    if (!query) return setError(t('carEditor.errPlateOrVin'));
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
      const bits = [found.color, found.last_registered_at && t('carEditor.registration', { date: found.last_registered_at })]
        .filter(Boolean)
        .join(' · ');
      setLookupNote(bits ? t('carEditor.foundColon', { bits }) : t('carEditor.foundInRegistry'));
    } catch (err) {
      setError(
        err?.response?.status === 403
          ? t('carEditor.lookupNeedsVerify')
          : extractError(err, t('carEditor.errLookupFailed'))
      );
    } finally {
      setLooking(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const year = parseInt(form.year, 10);
    const odometer = parseInt(form.current_odometer, 10);
    if (!form.brand.trim()) return setError(t('carEditor.errBrand'));
    if (!form.model.trim()) return setError(t('carEditor.errModel'));
    if (!Number.isFinite(year) || year < 1900 || year > 2100) return setError(t('carEditor.errYear'));
    if (!Number.isFinite(odometer) || odometer < 0) return setError(t('carEditor.errOdometer'));

    // Empty means "not set" (null), not zero: zero is meaningless for both the
    // tank and the budget, and the backend rejects it anyway.
    const tank = form.tank_liters.trim() ? Number(form.tank_liters) : null;
    if (tank !== null && (!Number.isFinite(tank) || tank <= 0))
      return setError(t('carEditor.errTank'));
    const budget = form.monthly_budget.trim() ? Number(form.monthly_budget) : null;
    if (budget !== null && (!Number.isFinite(budget) || budget <= 0))
      return setError(t('carEditor.errBudget'));

    const payload = {
      brand: form.brand.trim(),
      model: form.model.trim(),
      generation: form.generation.trim() || null,
      engine: form.engine.trim() || null,
      year,
      fuel_type: form.fuel_type,
      // Entered in display units; store metric.
      current_odometer: Math.round(kmFromDistance(odometer, currentUnits())),
      tank_liters: tank == null ? null : litresFromVolume(tank, currentUnits()),
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
      setError(extractError(err, t('carEditor.errSaveFailed')));
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
            label={t('carEditor.plate')}
            containerClassName={`flex-1 ${autoClass('plate')}`}
            value={form.plate}
            onChange={set('plate')}
            enterKeyHint="search"
            onKeyDown={onLookupEnter}
          />
          <Button
            type="button"
            variant={
              !lookupLocked && (form.plate.trim().length > 3 || form.vin.trim().length > 3)
                ? 'primary'
                : 'secondary'
            }
            onClick={handleLookup}
            disabled={looking || lookupLocked || (!form.plate.trim() && !form.vin.trim())}
            className="h-14 flex-shrink-0 px-4"
          >
            {looking ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <span className="flex items-center gap-1.5">
                <Search className="h-4 w-4" />
                {t('carEditor.find')}
              </span>
            )}
          </Button>
        </div>
        <p className={`mt-2 text-xs ${lookupLocked ? 'text-amber' : 'text-mist'}`}>
          {lookupLocked ? t('carEditor.lookupNeedsVerify') : t('carEditor.lookupHint')}
        </p>
        {lookupNote && <p className="mt-1.5 text-xs text-mist">{lookupNote}</p>}
        {stolen === true && (
          <p className="rounded-xl border border-crit/40 bg-crit/10 px-3 py-2 text-sm text-crit">
            {t('carEditor.stolenWarning')}
          </p>
        )}
        {stolen === false && (
          <p className="mt-1.5 text-xs text-ok">{t('carEditor.notStolen')}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <TextField
          key={autoKey('brand')}
          label={t('carEditor.brand')}
          required
          containerClassName={autoClass('brand')}
          value={form.brand}
          onChange={set('brand')}
        />
        <TextField
          key={autoKey('model')}
          label={t('carEditor.model')}
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
        <TextField label={t('carEditor.generation')} value={form.generation} onChange={set('generation')} />
        <TextField
          key={autoKey('engine')}
          label={t('carEditor.engine')}
          containerClassName={autoClass('engine')}
          value={form.engine}
          onChange={set('engine')}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <TextField
          key={autoKey('year')}
          label={t('carEditor.year')}
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
          label={t('carEditor.fuel')}
          containerClassName={autoClass('fuel_type')}
          value={form.fuel_type}
          onChange={set('fuel_type')}
          options={fuelOptions}
        />
      </div>
      <TextField
        ref={odometerRef}
        label={t('carEditor.odometer', { unit: distanceUnitLabel() })}
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
          label={t('carEditor.tankLiters', { unit: volumeUnitLabel() })}
          hint={t('carEditor.hintTank')}
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
          label={t('carEditor.monthlyBudget', { currency: currentCurrencySymbol() })}
          hint={t('carEditor.hintBudget')}
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
          {t('carEditor.driverNotes')}
        </label>
        <textarea
          id="scratchpad"
          rows={3}
          maxLength={2000}
          value={form.scratchpad}
          onChange={set('scratchpad')}
          placeholder={t('carEditor.notesPlaceholder')}
          className="w-full resize-none rounded-xl border border-edge bg-panel px-3.5 py-2.5 text-sm text-fg placeholder:text-mist/50 focus:border-amber focus:outline-none"
        />
        <p className="mt-1 px-1 text-xs text-mist/70">
          {t('carEditor.telegramNote')}
        </p>
      </div>

      <div className="rounded-xl border border-edge bg-raised/40 p-3">
        <p className="mb-1 text-sm font-medium text-fg">{t('carEditor.qrPassport')}</p>
        <p className="mb-3 text-xs text-mist">
          {t('carEditor.qrHint')}
        </p>
        <div className="space-y-3">
          <TextField
            label={t('carEditor.contactPhone')}
            type="tel"
            inputMode="tel"
            hint={t('carEditor.hintPhone')}
            value={form.contact_phone}
            onChange={set('contact_phone')}
          />
          <div className="grid grid-cols-2 gap-3">
            <TextField
              label={t('carEditor.insuranceNumber')}
              value={form.insurance_number}
              onChange={set('insurance_number')}
            />
            <DateField
              label={t('carEditor.insuranceUntil')}
              clearable
              value={form.insurance_until}
              onChange={(v) => setForm((f) => ({ ...f, insurance_until: v }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <TextField
              label={t('carEditor.tirePressure')}
              hint={t('carEditor.hintTirePressure')}
              value={form.tire_pressure}
              onChange={set('tire_pressure')}
            />
            <TextField
              label={t('carEditor.fuelApproval')}
              hint={t('carEditor.hintFuelApproval')}
              value={form.fuel_approval}
              onChange={set('fuel_approval')}
            />
          </div>
        </div>
      </div>

      {/* Sticky action bar: always in reach just above the bottom nav. Its own
          black background carries a generous bottom pad (pb-9) so the buttons
          clear both the nav and the round «Add» button that juts up over it —
          without that gap the round button overlapped «Save». The ::after fills
          the strip between the bar and the nav with the same solid background,
          so scrolling form text never shows through beneath the buttons. */}
      <div className="sticky bottom-[calc(env(safe-area-inset-bottom)+3.75rem)] z-20 -mx-4 border-t border-edge bg-garage px-4 pt-3 pb-9 after:pointer-events-none after:absolute after:inset-x-0 after:top-full after:h-24 after:bg-garage">
        {error && <ErrorMessage className="mb-3">{error}</ErrorMessage>}
        <div className="flex gap-2">
          <Button type="submit" disabled={submitting} className="flex-1">
            {submitting ? t('common.saving') : t('common.save')}
          </Button>
          <Button variant="secondary" onClick={onCancel}>
            {t('common.cancel')}
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
  const { t } = useTranslation();
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
        <p className="text-sm text-mist">{t('carEditor.loadingCar')}</p>
      </Card>
    );
  }

  const handleSubmit = async (payload) => {
    if (editing) {
      await editCar(car.id, payload);
    } else {
      await addCar(payload);
    }
    navigate('/garage', { state: { toast: editing ? t('carEditor.toastUpdated') : t('carEditor.toastAdded') } });
  };

  return (
    <div className="stagger space-y-4">
      <BackLink to="/garage">{editing ? t('carEditor.editTitle') : t('carEditor.newTitle')}</BackLink>
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
