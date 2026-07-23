import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Fuel, Wrench, Hammer, Receipt, Plus, Camera, Loader2, AlertTriangle, Lock } from 'lucide-react';
import { extractError } from '../api/client';
import { scanReceipt, scanWorkOrder } from '../api/ocr';
import { getRefuelContext } from '../api/logs';
import { useAuthStore } from '../store/authStore';
import { num, deriveRefuel } from '../utils/refuelMath';
import { formatDate, distanceUnitLabel, volumeUnitLabel } from '../utils/format';
import { isImperial, LITRES_PER_US_GALLON } from '../units';
import { currentUnits } from '../store/unitStore';
import { currentCurrencySymbol } from '../store/currencyStore';
import { expenseCategoryFrom } from '../utils/expenseCategory';
import { describeWorkOrder, workOrderToFormValues } from '../utils/workOrder';
import {
  COMMON_MAINTENANCE_ITEMS,
  REPAIR_CATEGORIES,
  EXPENSE_CATEGORIES,
  emptyFormValues,
  formValuesToPayload,
} from '../utils/entryForm';
import { entryWarnings, lastEntryHint } from '../utils/entryWarnings';
import { FUEL_KIND_OPTIONS, fuelKindLabel, shouldShowFuelKind } from '../utils/fuelKind';
import { maintenanceItemLabel, repairCategoryLabel, expenseCategoryLabel } from '../i18n/domain';
import { Button, TextField, DateField, SelectField, Card, Toggle, ErrorMessage } from './UI';
import Toast from './Toast';

// `labelKey` is an entryForm i18n key; the display label is resolved with t()
// at render time. Consumers that only need the code use `value`.
export const ENTRY_TYPES = [
  { value: 'refuel', labelKey: 'typeRefuel', icon: Fuel },
  { value: 'maintenance', labelKey: 'typeMaintenance', icon: Wrench },
  { value: 'repair', labelKey: 'typeRepair', icon: Hammer },
  { value: 'expense', labelKey: 'typeExpense', icon: Receipt },
];

const NO_TOAST = { message: '', variant: 'ok' };

function ScanButton({ scanning, onFile, idle, busy, locked, lockedLabel }) {
  // Locked = the account's email isn't verified. Scanning is a paid feature
  // (Gemini OCR), so it stays behind a verified email — show a hint, no picker.
  if (locked) {
    return (
      <div
        data-tour="add-scan"
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-edge-soft px-3.5 py-3.5 text-sm font-medium text-mist/70"
      >
        <Lock className="h-4 w-4" />
        {lockedLabel}
      </div>
    );
  }
  return (
    <label
      data-tour="add-scan"
      className={`relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-xl border border-dashed px-3.5 py-3.5 text-sm font-semibold transition-colors ${
        scanning
          ? 'pointer-events-none border-amber/50 text-amber'
          : 'cursor-pointer border-edge-soft text-mist hover:border-amber hover:text-amber'
      }`}
    >
      {/* No `capture`: on iOS that forced the camera. Without it Safari offers
          «Photo Library / Take Photo / Choose File», so a gallery photo works. */}
      <input
        type="file"
        accept="image/*"
        className="hidden"
        disabled={scanning}
        onChange={onFile}
      />
      {scanning ? (
        <>
          <Loader2 className="h-4 w-4 animate-spin" />
          {busy}
          <span className="scan-beam" aria-hidden="true" />
        </>
      ) : (
        <>
          <Camera className="h-4 w-4" />
          {idle}
        </>
      )}
    </label>
  );
}

function Chip({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-xl border px-3 py-1.5 text-xs font-medium transition-colors ${
        active
          ? 'border-amber bg-amber text-amber-ink'
          : 'border-edge bg-raised text-mist hover:border-edge-soft hover:text-fg'
      }`}
    >
      {children}
    </button>
  );
}

export default function EntryForm({
  mode = 'create',
  carId,
  car,
  type,
  lockedType = false,
  onTypeChange,
  initialValues,
  submitting,
  onSubmit,
  onCancel,
  scannedFile,
  onScanFile,
}) {
  const { t } = useTranslation();
  const [init] = useState(() => ({ ...emptyFormValues(), ...initialValues }));

  // Scan results and OCR previews arrive in metric (litres, price/litre); the
  // form works in the user's display units, so convert on the way in.
  const imperialUnits = isImperial(currentUnits());
  const displayVolume = (litres) =>
    imperialUnits ? +(Number(litres) / LITRES_PER_US_GALLON).toFixed(2) : litres;
  const displayPricePerVol = (perLitre) =>
    imperialUnits ? +(Number(perLitre) * LITRES_PER_US_GALLON).toFixed(2) : perLitre;

  // shared fields
  const [date, setDate] = useState(init.date);
  const [odometer, setOdometer] = useState(init.odometer);
  const [totalCost, setTotalCost] = useState(init.totalCost);
  const [notes, setNotes] = useState(init.notes);

  // refuel fields
  const [liters, setLiters] = useState(init.liters);
  const [pricePerLiter, setPricePerLiter] = useState(init.pricePerLiter);
  const [isFullTank, setIsFullTank] = useState(init.isFullTank);
  const [gasStation, setGasStation] = useState(init.gasStation);
  const [fuelKind, setFuelKind] = useState(init.fuelKind);

  // maintenance fields
  const [checkedItems, setCheckedItems] = useState(init.checkedItems);
  const [customItem, setCustomItem] = useState('');
  const [customItems, setCustomItems] = useState(init.customItems);
  const [partsCost, setPartsCost] = useState(init.partsCost);
  const [laborCost, setLaborCost] = useState(init.laborCost);

  // repair fields
  const [category, setCategory] = useState(init.category);
  const [partName, setPartName] = useState(init.partName);
  const [warrantyMonths, setWarrantyMonths] = useState(init.warrantyMonths);
  const [warrantyKm, setWarrantyKm] = useState(init.warrantyKm);

  // expense fields
  const [expenseCategory, setExpenseCategory] = useState(init.expenseCategory);

  const [context, setContext] = useState(null);

  const [error, setError] = useState('');
  const [toast, setToast] = useState(NO_TOAST);

  // receipt scanning — locked until the email is verified (paid Gemini OCR).
  // false only for a genuinely unverified account; undefined must not lock.
  const scanLocked = useAuthStore((s) => s.user?.email_verified) === false;
  const [scanning, setScanning] = useState(false);
  const scanningRef = useRef(false);
  const editedDuringScanRef = useRef(new Set());

  // While a scan is in flight, remember which fields the user touched so the
  // recognized values never overwrite manual input.
  const markEdited = (...fields) => {
    if (!scanningRef.current) return;
    fields.forEach((f) => editedDuringScanRef.current.add(f));
  };

  useEffect(() => {
    if (!carId) return undefined;
    let cancelled = false;
    getRefuelContext(carId)
      .then((data) => {
        if (cancelled) return;
        setContext(data);
        if (data.last_price_per_liter != null) {
          setPricePerLiter((prev) =>
            prev === '' ? String(displayPricePerVol(data.last_price_per_liter)) : prev,
          );
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [carId]);

  // --- refuel auto-math: compute the ONE field the user never entered, from
  //     the two they did — never a field they typed themselves or are typing
  //     right now, and only after they pause or leave the field. ---
  // Fields the user provided. When editing an existing refuel, everything that
  // arrived populated was already entered by a human — seed it as owned so a
  // later edit to one field never re-derives (and overwrites) a total_cost the
  // owner set by hand.
  const refuelOwnedRef = useRef(
    new Set(
      ['liters', 'pricePerLiter', 'totalCost'].filter(
        (f) => init[f] !== '' && init[f] != null,
      ),
    ),
  );
  const refuelValsRef = useRef({ liters, pricePerLiter, totalCost });
  const refuelIdleRef = useRef(null);
  const REFUEL_IDLE_MS = 1400; // «більша затримка» — well after the last keystroke

  useEffect(() => {
    refuelValsRef.current = { liters, pricePerLiter, totalCost };
  }, [liters, pricePerLiter, totalCost]);

  useEffect(() => () => clearTimeout(refuelIdleRef.current), []);

  const runRefuelDerive = () => {
    if (type !== 'refuel') return;
    const patch = deriveRefuel(refuelValsRef.current, [...refuelOwnedRef.current]);
    if (!patch) return;
    // Only ever a single non-user field; a value the user owns is never in here.
    if (patch.liters !== undefined) setLiters(patch.liters);
    if (patch.pricePerLiter !== undefined) setPricePerLiter(patch.pricePerLiter);
    if (patch.totalCost !== undefined) setTotalCost(patch.totalCost);
  };

  const noteRefuelEdit = (field) => {
    refuelOwnedRef.current.add(field); // the user now owns this field
    markEdited(field);
    // Derive only well after the last keystroke, so it never fires mid-typing.
    clearTimeout(refuelIdleRef.current);
    refuelIdleRef.current = setTimeout(runRefuelDerive, REFUEL_IDLE_MS);
  };

  // Leaving a field (tap elsewhere / scroll away) derives right away.
  const onRefuelBlur = () => {
    clearTimeout(refuelIdleRef.current);
    runRefuelDerive();
  };

  const onLitersChange = (v) => {
    setLiters(v);
    noteRefuelEdit('liters');
  };

  const onPriceChange = (v) => {
    setPricePerLiter(v);
    noteRefuelEdit('pricePerLiter');
  };

  const onTotalChange = (v) => {
    setTotalCost(v);
    if (type === 'refuel') noteRefuelEdit('totalCost');
    else markEdited('totalCost');
  };

  // --- scanning ---
  // One frame for every tab: pick the file, hold the loader, keep whatever the
  // user typed while it was in flight, report what came back. Only `read`
  // differs — which endpoint, and which fields it can fill.
  const runScan = async (e, { read, apply, describe, failure }) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file || scanning) return;

    editedDuringScanRef.current = new Set();
    scanningRef.current = true;
    setScanning(true);
    try {
      const data = await read(file);
      if (onScanFile) onScanFile(file);
      apply(data, editedDuringScanRef.current);
      const summary = describe(data);
      setToast(
        summary
          ? { message: t('entryForm.scanRecognized', { summary }), variant: 'ok' }
          : { message: failure, variant: 'warn' }
      );
    } catch (err) {
      const status = err?.response?.status;
      setToast({
        message:
          status === 403
            ? t('entryForm.scanNeedsVerify')
            : status === 503
              ? t('entryForm.scanUnavailable')
              : failure,
        variant: 'warn',
      });
    } finally {
      scanningRef.current = false;
      setScanning(false);
    }
  };

  const handleReceiptFile = (e) =>
    runScan(e, {
      read: scanReceipt,
      failure: t('entryForm.scanReceiptFailed'),
      apply: (data, edited) => {
        // Scanned numbers are the user's inputs too — mark them owned so the
        // one field the receipt didn't carry still gets computed.
        if (data.liters != null && !edited.has('liters')) {
          setLiters(String(displayVolume(data.liters)));
          refuelOwnedRef.current.add('liters');
        }
        if (data.price_per_liter != null && !edited.has('pricePerLiter')) {
          setPricePerLiter(String(displayPricePerVol(data.price_per_liter)));
          refuelOwnedRef.current.add('pricePerLiter');
        }
        if (data.total_cost != null && !edited.has('totalCost')) {
          setTotalCost(Number(data.total_cost).toFixed(2));
          refuelOwnedRef.current.add('totalCost');
        }
        if (data.date && !edited.has('date')) setDate(data.date);
        if (data.gas_station && !edited.has('gasStation')) setGasStation(data.gas_station);
      },
      describe: (data) => {
        const parts = [];
        if (data.liters != null)
          parts.push(
            t('entryForm.unitLiters', {
              value: displayVolume(data.liters),
              unit: volumeUnitLabel(),
            }),
          );
        if (data.price_per_liter != null)
          parts.push(
            t('entryForm.unitPricePerLiter', {
              value: displayPricePerVol(data.price_per_liter),
              currency: currentCurrencySymbol(),
              unit: volumeUnitLabel(),
            }),
          );
        if (data.total_cost != null)
          parts.push(
            t('entryForm.unitUah', {
              value: Number(data.total_cost).toFixed(2),
              currency: currentCurrencySymbol(),
            }),
          );
        if (data.date) parts.push(formatDate(data.date));
        if (data.gas_station) parts.push(data.gas_station);
        return parts.join(', ');
      },
    });

  const handleWorkOrderFile = (e) =>
    runScan(e, {
      read: scanWorkOrder,
      failure: t('entryForm.scanWorkOrderFailed'),
      describe: describeWorkOrder,
      apply: (data, edited) => {
        const scanned = workOrderToFormValues(data);
        if (scanned.date && !edited.has('date')) setDate(scanned.date);
        if (scanned.partsCost != null && !edited.has('partsCost')) setPartsCost(scanned.partsCost);
        if (scanned.laborCost != null && !edited.has('laborCost')) setLaborCost(scanned.laborCost);
        // The bill the shop printed, not parts + labour: when the two halves
        // disagreed with it the parser dropped them, and the total is what was
        // actually paid.
        if (scanned.totalCost != null && !edited.has('totalCost')) setTotalCost(scanned.totalCost);
        if (scanned.checkedItems.length && !edited.has('checkedItems')) {
          setCustomItems((current) => [
            ...current,
            ...scanned.customItems.filter((item) => !current.includes(item)),
          ]);
          setCheckedItems((current) => [
            ...current,
            ...scanned.checkedItems.filter((item) => !current.includes(item)),
          ]);
        }
      },
    });

  // A repair is billed on the same наряд as a service — the shop does not know
  // which tab it will be filed under. What differs is where the work lands: a
  // repair has no item list, so what was done goes in the notes.
  const handleRepairOrderFile = (e) =>
    runScan(e, {
      read: scanWorkOrder,
      failure: t('entryForm.scanWorkOrderFailed'),
      describe: describeWorkOrder,
      apply: (data, edited) => {
        if (data.date && !edited.has('date')) setDate(data.date);
        if (data.total_cost != null && !edited.has('totalCost'))
          setTotalCost(Number(data.total_cost).toFixed(2));
        // Never over notes the user already wrote: theirs say why, the shop's
        // only say what.
        if (data.items?.length) setNotes((current) => current || data.items.join(', '));
      },
    });

  // Any till receipt: a car wash, a parking barrier, a service fee. The sum and
  // the date are read; the category only when the paper names it. «АВТОМИЙКА»
  // on a slip is not a guess, it is the receipt saying what it is for — but a
  // slip that says nothing gets nothing, because a wrong category is silent: it
  // files the money where the user will never look for it.
  const handleExpenseReceiptFile = (e) =>
    runScan(e, {
      read: scanReceipt,
      failure: t('entryForm.scanReceiptFailed'),
      apply: (data, edited) => {
        if (data.total_cost != null && !edited.has('totalCost'))
          setTotalCost(Number(data.total_cost).toFixed(2));
        if (data.date && !edited.has('date')) setDate(data.date);
        if (data.gas_station) setNotes((current) => current || data.gas_station);
        const category = expenseCategoryFrom(data.raw_text);
        if (category && !edited.has('expenseCategory')) setExpenseCategory(category);
      },
      describe: (data) => {
        const parts = [];
        if (data.total_cost != null)
          parts.push(
            t('entryForm.unitUah', {
              value: Number(data.total_cost).toFixed(2),
              currency: currentCurrencySymbol(),
            }),
          );
        if (data.date) parts.push(formatDate(data.date));
        const category = expenseCategoryFrom(data.raw_text);
        if (category) parts.push(expenseCategoryLabel(category).toLowerCase());
        return parts.join(', ');
      },
    });

  // --- maintenance: total = parts + labor ---
  const onPartsChange = (v) => {
    setPartsCost(v);
    const parts = num(v) ?? 0;
    const labor = num(laborCost) ?? 0;
    setTotalCost(String(Math.round((parts + labor) * 100) / 100));
  };

  const onLaborChange = (v) => {
    setLaborCost(v);
    const parts = num(partsCost) ?? 0;
    const labor = num(v) ?? 0;
    setTotalCost(String(Math.round((parts + labor) * 100) / 100));
  };

  const allMaintenanceItems = useMemo(
    () => [...COMMON_MAINTENANCE_ITEMS, ...customItems],
    [customItems]
  );

  const toggleItem = (item) => {
    setCheckedItems((prev) =>
      prev.includes(item) ? prev.filter((i) => i !== item) : [...prev, item]
    );
  };

  const addCustomItem = () => {
    const item = customItem.trim();
    if (!item) return;
    if (!allMaintenanceItems.includes(item)) {
      setCustomItems((prev) => [...prev, item]);
    }
    setCheckedItems((prev) => (prev.includes(item) ? prev : [...prev, item]));
    setCustomItem('');
  };

  // An entry may carry a category outside the fixed list (e.g. created via bot).
  // Keep the memo to the (value) list; labels are localized at render time so a
  // language switch relabels the options.
  const categoryValues = useMemo(() => {
    return REPAIR_CATEGORIES.includes(category)
      ? REPAIR_CATEGORIES
      : [category, ...REPAIR_CATEGORIES];
  }, [category]);
  const categoryOptions = categoryValues.map((c) => ({ value: c, label: repairCategoryLabel(c) }));

  const warnings = useMemo(
    () => entryWarnings({ type, odometer, date, context }),
    [type, odometer, date, context]
  );

  const odometerHint = lastEntryHint(context);

  const showFuelKind = shouldShowFuelKind(car) || Boolean(init.fuelKind);

  const recentStations = context?.recent_stations || [];

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    const odo = parseInt(odometer, 10);
    const cost = num(totalCost);

    if (!date) return setError(t('entryForm.errDate'));
    if (!Number.isFinite(odo) || odo < 0) return setError(t('entryForm.errOdometer'));
    if (cost === null || cost < 0) return setError(t('entryForm.errTotalCost'));

    if (type === 'refuel') {
      const l = num(liters);
      const p = num(pricePerLiter);
      if (!l || l <= 0) return setError(t('entryForm.errLiters'));
      if (!p || p <= 0) return setError(t('entryForm.errPricePerLiter'));
    }

    const payload = formValuesToPayload(type, {
      date,
      odometer,
      totalCost,
      notes,
      liters,
      pricePerLiter,
      isFullTank,
      gasStation,
      fuelKind,
      checkedItems,
      customItems,
      partsCost,
      laborCost,
      category,
      partName,
      warrantyMonths,
      warrantyKm,
      expenseCategory,
    });

    try {
      await onSubmit(payload);
    } catch (err) {
      setError(extractError(err, t('entryForm.saveFailed')));
    }
  };

  return (
    <form onSubmit={handleSubmit} className="stagger-pass stagger flex flex-col gap-4">
      <Toast message={toast.message} variant={toast.variant} onDone={() => setToast(NO_TOAST)} />

      {!lockedType && (
        <div
          data-tour="add-type"
          className="grid grid-cols-4 gap-1 rounded-2xl border border-edge bg-panel p-1"
        >
          {ENTRY_TYPES.map(({ value, labelKey, icon: Icon }) => (
            <button
              key={value}
              type="button"
              onClick={() => onTypeChange(value)}
              aria-pressed={type === value}
              className={`flex flex-col items-center gap-1 rounded-xl px-1 py-2 text-[11px] font-semibold transition-colors ${
                type === value ? 'bg-amber text-amber-ink' : 'text-mist hover:text-fg'
              }`}
            >
              <Icon className="h-4 w-4" />
              {t(`entryForm.${labelKey}`)}
            </button>
          ))}
        </div>
      )}

      <Card data-tour="add-form" className="flex flex-col gap-3.5">
        <div className="grid grid-cols-2 gap-3">
          <DateField
            label={t('entryForm.date')}
            required
            value={date}
            onChange={(v) => {
              markEdited('date');
              setDate(v);
            }}
          />
          <TextField
            label={t('entryForm.odometerKm', { unit: distanceUnitLabel() })}
            type="number"
            inputMode="numeric"
            enterKeyHint="next"
            min="0"
            numeric
            required
            value={odometer}
            onChange={(e) => setOdometer(e.target.value)}
          />
        </div>

        {/* Full-width, not tucked into the half-width odometer column, where it
            wrapped to two cramped lines. */}
        {odometerHint && <p className="-mt-1 text-xs text-mist">{odometerHint}</p>}

        {warnings.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {warnings.map((warning) => (
              <p key={warning} className="flex items-start gap-1.5 text-xs text-amber">
                <AlertTriangle className="mt-px h-3.5 w-3.5 flex-shrink-0" />
                {warning}
              </p>
            ))}
          </div>
        )}

        {type === 'refuel' && (
          <>
            <ScanButton
              scanning={scanning}
              locked={scanLocked}
              lockedLabel={t('entryForm.scanNeedsVerify')}
              onFile={handleReceiptFile}
              idle={t('entryForm.scanReceipt')}
              busy={t('entryForm.scanningReceipt')}
            />
            {mode === 'create' && scannedFile && (
              <p className="text-xs text-mist">{t('entryForm.receiptAttached')}</p>
            )}
            <div className="grid grid-cols-2 gap-3">
              <TextField
                label={t('entryForm.liters', { unit: volumeUnitLabel() })}
                type="text"
                inputMode="decimal"
                enterKeyHint="next"
                numeric
                value={liters}
                onChange={(e) => onLitersChange(e.target.value)}
                onBlur={onRefuelBlur}
              />
              <TextField
                label={t('entryForm.pricePerLiter', { unit: volumeUnitLabel() })}
                type="text"
                inputMode="decimal"
                enterKeyHint="next"
                numeric
                value={pricePerLiter}
                onChange={(e) => onPriceChange(e.target.value)}
                onBlur={onRefuelBlur}
              />
            </div>
            <TextField
              label={t('entryForm.totalCost')}
              type="text"
              inputMode="decimal"
              enterKeyHint="next"
              numeric
              required
              value={totalCost}
              onChange={(e) => onTotalChange(e.target.value)}
              onBlur={onRefuelBlur}
            />
            {showFuelKind && (
              <SelectField
                label={t('entryForm.fuelKind')}
                value={fuelKind}
                onChange={(e) => setFuelKind(e.target.value)}
                hint={t('entryForm.fuelKindHint')}
              >
                <option value="">
                  {t('entryForm.fuelKindDefault', { fuel: fuelKindLabel(car?.fuel_type) })}
                </option>
                {FUEL_KIND_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {fuelKindLabel(opt.value)}
                  </option>
                ))}
              </SelectField>
            )}
            <Toggle label={t('entryForm.fullTank')} checked={isFullTank} onChange={setIsFullTank} />
            <TextField
              label={t('entryForm.gasStation')}
              type="text"
              value={gasStation}
              onChange={(e) => {
                markEdited('gasStation');
                setGasStation(e.target.value);
              }}
            />
            {recentStations.length > 0 && (
              <div className="-mt-1.5 flex flex-wrap gap-1.5">
                {recentStations.map((station) => (
                  <Chip
                    key={station}
                    active={gasStation === station}
                    onClick={() => {
                      markEdited('gasStation');
                      setGasStation(station);
                    }}
                  >
                    {station}
                  </Chip>
                ))}
              </div>
            )}
          </>
        )}

        {type === 'maintenance' && (
          <>
            <ScanButton
              scanning={scanning}
              locked={scanLocked}
              lockedLabel={t('entryForm.scanNeedsVerify')}
              onFile={handleWorkOrderFile}
              idle={t('entryForm.scanWorkOrder')}
              busy={t('entryForm.scanningWorkOrder')}
            />
            {mode === 'create' && scannedFile && (
              <p className="text-xs text-mist">{t('entryForm.workOrderAttached')}</p>
            )}
            <div>
              <span className="mb-1.5 block text-sm text-mist">{t('entryForm.whatReplaced')}</span>
              <div className="flex flex-col gap-1.5">
                {allMaintenanceItems.map((item) => (
                  <label
                    key={item}
                    className="flex cursor-pointer items-center gap-2.5 rounded-xl border border-edge bg-raised px-3.5 py-2.5 transition-colors hover:border-edge-soft"
                  >
                    <input
                      type="checkbox"
                      checked={checkedItems.includes(item)}
                      onChange={() => toggleItem(item)}
                      className="h-4 w-4 rounded border-edge-soft bg-panel accent-amber"
                    />
                    <span className="text-sm text-fg">{maintenanceItemLabel(item)}</span>
                  </label>
                ))}
              </div>
              <div className="mt-2 flex items-start gap-2">
                <TextField
                  label={t('entryForm.customItem')}
                  type="text"
                  value={customItem}
                  onChange={(e) => setCustomItem(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      addCustomItem();
                    }
                  }}
                  containerClassName="flex-1"
                />
                <Button
                  variant="secondary"
                  onClick={addCustomItem}
                  aria-label={t('entryForm.addItem')}
                  className="h-14 w-14 flex-shrink-0"
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <TextField
                label={t('entryForm.parts')}
                type="text"
                inputMode="decimal"
                enterKeyHint="next"
                numeric
                value={partsCost}
                onChange={(e) => onPartsChange(e.target.value)}
              />
              <TextField
                label={t('entryForm.labor')}
                type="text"
                inputMode="decimal"
                enterKeyHint="next"
                numeric
                value={laborCost}
                onChange={(e) => onLaborChange(e.target.value)}
              />
            </div>
          </>
        )}

        {type === 'repair' && (
          <>
            <ScanButton
              scanning={scanning}
              locked={scanLocked}
              lockedLabel={t('entryForm.scanNeedsVerify')}
              onFile={handleRepairOrderFile}
              idle={t('entryForm.scanWorkOrder')}
              busy={t('entryForm.scanningWorkOrder')}
            />
            {mode === 'create' && scannedFile && (
              <p className="text-xs text-mist">{t('entryForm.workOrderAttached')}</p>
            )}
            <SelectField
              label={t('entryForm.category')}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              options={categoryOptions}
            />
            <TextField
              label={t('entryForm.partName')}
              type="text"
              value={partName}
              onChange={(e) => setPartName(e.target.value)}
            />
            <div className="grid grid-cols-2 gap-3">
              <TextField
                label={t('entryForm.warrantyMonths')}
                type="number"
                inputMode="numeric"
                enterKeyHint="next"
                min="0"
                numeric
                value={warrantyMonths}
                onChange={(e) => setWarrantyMonths(e.target.value)}
              />
              <TextField
                label={t('entryForm.warrantyKm', { unit: distanceUnitLabel() })}
                type="number"
                inputMode="numeric"
                enterKeyHint="next"
                min="0"
                numeric
                value={warrantyKm}
                onChange={(e) => setWarrantyKm(e.target.value)}
              />
            </div>
          </>
        )}

        {type === 'expense' && (
          <>
            <ScanButton
              scanning={scanning}
              locked={scanLocked}
              lockedLabel={t('entryForm.scanNeedsVerify')}
              onFile={handleExpenseReceiptFile}
              idle={t('entryForm.scanReceipt')}
              busy={t('entryForm.scanningReceipt')}
            />
            {mode === 'create' && scannedFile && (
              <p className="text-xs text-mist">{t('entryForm.receiptAttached')}</p>
            )}
          </>
        )}

        {type === 'expense' && (
          <div>
            <span className="mb-1.5 block text-sm text-mist">{t('entryForm.category')}</span>
            <div className="flex flex-wrap gap-1.5">
              {EXPENSE_CATEGORIES.map((c) => (
                <Chip
                  key={c}
                  active={expenseCategory === c}
                  onClick={() => {
                    setExpenseCategory(c);
                    markEdited('expenseCategory');
                  }}
                >
                  {expenseCategoryLabel(c)}
                </Chip>
              ))}
            </div>
          </div>
        )}

        {/* Refuel shows it above «Повний бак» (inside the refuel block); the
            other types keep it here in the shared position. */}
        {type !== 'refuel' && (
          <TextField
            label={t('entryForm.totalCost')}
            type="text"
            inputMode="decimal"
            enterKeyHint="next"
            numeric
            required
            value={totalCost}
            onChange={(e) => onTotalChange(e.target.value)}
          />
        )}

        <TextField
          label={t('entryForm.notes')}
          multiline
          enterKeyHint="done"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />

      </Card>

      {/* Sticky action bar above the bottom nav — save without scrolling to the
          end of a long entry form. */}
      <div className="sticky bottom-0 z-20 -mx-4 border-t border-edge bg-garage px-4 pt-3 pb-[calc(env(safe-area-inset-bottom)+4.75rem)]">
        {error && <ErrorMessage className="mb-3">{error}</ErrorMessage>}
        <div className="flex gap-2">
          <Button type="submit" disabled={submitting} className="flex-1">
            {submitting
              ? t('common.saving')
              : mode === 'edit'
                ? t('common.saveChanges')
                : t('entryForm.saveEntry')}
          </Button>
          {onCancel && (
            <Button variant="secondary" onClick={onCancel}>
              {t('common.cancel')}
            </Button>
          )}
        </div>
      </div>
    </form>
  );
}
