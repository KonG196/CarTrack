import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Fuel, Wrench, Hammer, Receipt, Plus, Camera, Loader2 } from 'lucide-react';
import { useCarStore } from '../store/carStore';
import { extractError } from '../api/client';
import { scanReceipt } from '../api/ocr';
import { num, computeRefuelUpdate } from '../utils/refuelMath';
import { formatDate } from '../utils/format';
import { Button, Input, Select, Card, Toggle, ErrorMessage } from '../components/UI';
import Toast from '../components/Toast';

const TYPES = [
  { value: 'refuel', label: 'Заправка', icon: Fuel },
  { value: 'maintenance', label: 'ТО', icon: Wrench },
  { value: 'repair', label: 'Ремонт', icon: Hammer },
  { value: 'expense', label: 'Витрата', icon: Receipt },
];

const COMMON_MAINTENANCE_ITEMS = [
  'Олива двигуна',
  'Масляний фільтр',
  'Повітряний фільтр',
  'Салонний фільтр',
  'Паливний фільтр',
  'Гальмівна рідина',
];

const REPAIR_CATEGORIES = [
  'Підвіска',
  'Гальма',
  'Двигун',
  'Електрика',
  'Трансмісія',
  'Кузов',
  'Інше',
];

const todayIso = () => new Date().toISOString().slice(0, 10);

export default function AddEntry() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const cars = useCarStore((s) => s.cars);
  const carsLoaded = useCarStore((s) => s.carsLoaded);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const addLog = useCarStore((s) => s.addLog);
  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;

  const paramType = searchParams.get('type');
  const type = TYPES.some((t) => t.value === paramType) ? paramType : 'refuel';
  const setType = (t) => setSearchParams({ type: t }, { replace: true });

  // shared fields
  const [date, setDate] = useState(todayIso());
  const [odometer, setOdometer] = useState('');
  const [totalCost, setTotalCost] = useState('');
  const [notes, setNotes] = useState('');

  // refuel fields
  const [liters, setLiters] = useState('');
  const [pricePerLiter, setPricePerLiter] = useState('');
  const [isFullTank, setIsFullTank] = useState(true);
  const [gasStation, setGasStation] = useState('');

  // maintenance fields
  const [checkedItems, setCheckedItems] = useState([]);
  const [customItem, setCustomItem] = useState('');
  const [customItems, setCustomItems] = useState([]);
  const [partsCost, setPartsCost] = useState('');
  const [laborCost, setLaborCost] = useState('');

  // repair fields
  const [category, setCategory] = useState(REPAIR_CATEGORIES[0]);
  const [partName, setPartName] = useState('');
  const [warrantyMonths, setWarrantyMonths] = useState('');
  const [warrantyKm, setWarrantyKm] = useState('');

  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState('');

  // receipt scanning
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
    if (activeCar && odometer === '') {
      setOdometer(String(activeCar.current_odometer));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCar?.id]);

  // --- refuel auto-math: editing any two of (liters, price, total) computes the third ---
  const applyRefuelUpdate = (update) => {
    if (!update) return;
    if (update.liters !== undefined) setLiters(update.liters);
    if (update.pricePerLiter !== undefined) setPricePerLiter(update.pricePerLiter);
    if (update.totalCost !== undefined) setTotalCost(update.totalCost);
    markEdited(...Object.keys(update));
  };

  const onLitersChange = (v) => {
    setLiters(v);
    markEdited('liters');
    applyRefuelUpdate(computeRefuelUpdate('liters', { liters: v, pricePerLiter, totalCost }));
  };

  const onPriceChange = (v) => {
    setPricePerLiter(v);
    markEdited('pricePerLiter');
    applyRefuelUpdate(
      computeRefuelUpdate('pricePerLiter', { liters, pricePerLiter: v, totalCost })
    );
  };

  const onTotalChange = (v) => {
    setTotalCost(v);
    markEdited('totalCost');
    if (type !== 'refuel') return;
    applyRefuelUpdate(computeRefuelUpdate('totalCost', { liters, pricePerLiter, totalCost: v }));
  };

  // --- receipt scanning ---
  const handleReceiptFile = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file || scanning) return;

    editedDuringScanRef.current = new Set();
    scanningRef.current = true;
    setScanning(true);
    try {
      const data = await scanReceipt(file);
      const edited = editedDuringScanRef.current;
      const parts = [];

      if (data.liters != null) {
        if (!edited.has('liters')) setLiters(String(data.liters));
        parts.push(`${data.liters} л`);
      }
      if (data.price_per_liter != null) {
        if (!edited.has('pricePerLiter')) setPricePerLiter(String(data.price_per_liter));
        parts.push(`${data.price_per_liter} грн/л`);
      }
      if (data.total_cost != null) {
        if (!edited.has('totalCost')) setTotalCost(Number(data.total_cost).toFixed(2));
        parts.push(`${Number(data.total_cost).toFixed(2)} грн`);
      }
      if (data.date) {
        if (!edited.has('date')) setDate(data.date);
        parts.push(formatDate(data.date));
      }
      if (data.gas_station) {
        if (!edited.has('gasStation')) setGasStation(data.gas_station);
        parts.push(data.gas_station);
      }

      setToast(
        parts.length > 0
          ? `Розпізнано: ${parts.join(', ')}`
          : 'Не вдалося розпізнати дані з чека'
      );
    } catch (err) {
      if (err?.response?.status === 503) {
        setToast('Розпізнавання недоступне на сервері');
      } else {
        setToast('Не вдалося розпізнати чек. Спробуйте інше фото.');
      }
    } finally {
      scanningRef.current = false;
      setScanning(false);
    }
  };

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

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    const odo = parseInt(odometer, 10);
    const cost = num(totalCost);

    if (!date) return setError('Вкажіть дату');
    if (!Number.isFinite(odo) || odo < 0) return setError('Вкажіть коректний пробіг');
    if (cost === null || cost < 0) return setError('Вкажіть загальну вартість');

    const payload = {
      type,
      odometer: odo,
      date,
      total_cost: cost,
    };
    if (notes.trim()) payload.notes = notes.trim();

    if (type === 'refuel') {
      const l = num(liters);
      const p = num(pricePerLiter);
      if (!l || l <= 0) return setError('Вкажіть кількість літрів');
      if (!p || p <= 0) return setError('Вкажіть ціну за літр');
      payload.refuel = {
        liters: l,
        price_per_liter: p,
        is_full_tank: isFullTank,
      };
      if (gasStation.trim()) payload.refuel.gas_station = gasStation.trim();
    }

    if (type === 'maintenance') {
      payload.maintenance = {
        parts_cost: num(partsCost) ?? 0,
        labor_cost: num(laborCost) ?? 0,
        items: checkedItems,
      };
    }

    if (type === 'repair') {
      payload.repair = { category };
      if (partName.trim()) payload.repair.part_name = partName.trim();
      const wm = parseInt(warrantyMonths, 10);
      const wk = parseInt(warrantyKm, 10);
      if (Number.isFinite(wm) && wm > 0) payload.repair.warranty_months = wm;
      if (Number.isFinite(wk) && wk > 0) payload.repair.warranty_km = wk;
    }

    setSubmitting(true);
    try {
      await addLog(payload);
      navigate('/logbook', { state: { toast: 'Запис додано' } });
    } catch (err) {
      setError(extractError(err, 'Не вдалося зберегти запис'));
      setSubmitting(false);
    }
  };

  if (carsLoaded && !activeCar) {
    return (
      <Card className="mt-8 p-8 text-center">
        <p className="text-sm text-slate-400">
          Щоб додати запис, спершу створіть авто в розділі{' '}
          <Link to="/garage" className="text-blue-500 hover:text-blue-400">
            «Гараж»
          </Link>
          .
        </p>
      </Card>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />

      <div className="grid grid-cols-4 gap-1 rounded-2xl border border-slate-800 bg-slate-900 p-1">
        {TYPES.map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            onClick={() => setType(value)}
            className={`flex flex-col items-center gap-1 rounded-xl px-1 py-2 text-[11px] font-medium transition-colors ${
              type === value ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      <Card className="space-y-3.5">
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Дата"
            type="date"
            required
            value={date}
            onChange={(e) => {
              markEdited('date');
              setDate(e.target.value);
            }}
          />
          <Input
            label="Пробіг, км"
            type="number"
            inputMode="numeric"
            min="0"
            required
            value={odometer}
            onChange={(e) => setOdometer(e.target.value)}
            placeholder="123456"
          />
        </div>

        {type === 'refuel' && (
          <>
            <label
              className={`flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-slate-700 bg-slate-800/40 px-3.5 py-3 text-sm font-medium transition-colors ${
                scanning
                  ? 'pointer-events-none text-slate-500'
                  : 'cursor-pointer text-slate-300 hover:border-blue-500 hover:text-blue-400'
              }`}
            >
              <input
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                disabled={scanning}
                onChange={handleReceiptFile}
              />
              {scanning ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Розпізнаю чек…
                </>
              ) : (
                <>
                  <Camera className="h-4 w-4" />
                  Сканувати чек
                </>
              )}
            </label>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Літри"
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                value={liters}
                onChange={(e) => onLitersChange(e.target.value)}
                placeholder="40.5"
              />
              <Input
                label="Ціна за літр, ₴"
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                value={pricePerLiter}
                onChange={(e) => onPriceChange(e.target.value)}
                placeholder="54.99"
              />
            </div>
            <Toggle label="Повний бак" checked={isFullTank} onChange={setIsFullTank} />
            <Input
              label="АЗС (необов'язково)"
              type="text"
              value={gasStation}
              onChange={(e) => {
                markEdited('gasStation');
                setGasStation(e.target.value);
              }}
              placeholder="OKKO, WOG…"
            />
          </>
        )}

        {type === 'maintenance' && (
          <>
            <div>
              <span className="mb-1.5 block text-sm text-slate-400">Що замінено</span>
              <div className="space-y-1.5">
                {allMaintenanceItems.map((item) => (
                  <label
                    key={item}
                    className="flex cursor-pointer items-center gap-2.5 rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-2.5"
                  >
                    <input
                      type="checkbox"
                      checked={checkedItems.includes(item)}
                      onChange={() => toggleItem(item)}
                      className="h-4 w-4 rounded border-slate-600 bg-slate-700 accent-blue-600"
                    />
                    <span className="text-sm text-slate-200">{item}</span>
                  </label>
                ))}
              </div>
              <div className="mt-2 flex gap-2">
                <Input
                  type="text"
                  value={customItem}
                  onChange={(e) => setCustomItem(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      addCustomItem();
                    }
                  }}
                  placeholder="Інша позиція…"
                  className="flex-1"
                />
                <Button variant="secondary" onClick={addCustomItem} aria-label="Додати позицію">
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Запчастини, ₴"
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                value={partsCost}
                onChange={(e) => onPartsChange(e.target.value)}
                placeholder="0"
              />
              <Input
                label="Робота, ₴"
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                value={laborCost}
                onChange={(e) => onLaborChange(e.target.value)}
                placeholder="0"
              />
            </div>
          </>
        )}

        {type === 'repair' && (
          <>
            <Select
              label="Категорія"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              options={REPAIR_CATEGORIES.map((c) => ({ value: c, label: c }))}
            />
            <Input
              label="Деталь (необов'язково)"
              type="text"
              value={partName}
              onChange={(e) => setPartName(e.target.value)}
              placeholder="Амортизатор передній…"
            />
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Гарантія, міс."
                type="number"
                inputMode="numeric"
                min="0"
                value={warrantyMonths}
                onChange={(e) => setWarrantyMonths(e.target.value)}
                placeholder="12"
              />
              <Input
                label="Гарантія, км"
                type="number"
                inputMode="numeric"
                min="0"
                value={warrantyKm}
                onChange={(e) => setWarrantyKm(e.target.value)}
                placeholder="20000"
              />
            </div>
          </>
        )}

        <Input
          label="Загальна вартість, ₴"
          type="number"
          inputMode="decimal"
          step="0.01"
          min="0"
          required
          value={totalCost}
          onChange={(e) => onTotalChange(e.target.value)}
          placeholder="0.00"
        />

        <Input
          label="Нотатки (необов'язково)"
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Коментар…"
        />

        <ErrorMessage>{error}</ErrorMessage>

        <Button type="submit" disabled={submitting} className="w-full">
          {submitting ? 'Збереження…' : 'Зберегти запис'}
        </Button>
      </Card>
    </form>
  );
}
