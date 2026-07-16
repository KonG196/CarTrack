import { useEffect, useRef, useState } from 'react';
import {
  Car,
  Plus,
  ChevronRight,
  Pencil,
  Trash2,
  Check,
  Gauge,
  FileDown,
  FileSpreadsheet,
  Loader2,
  Database,
  Upload,
  Activity,
  Wrench,
  UserCircle,
  FileText,
  CircleDot,
  LogOut,
  Bell,
  Sparkles,
  QrCode,
} from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { useTour } from '../tour/TourContext';
import { TOURS, TOUR_ORDER } from '../tour/tourSteps';
import { useCarStore } from '../store/carStore';
import { extractError } from '../api/client';
import { downloadCarReport } from '../api/reports';
import * as backupApi from '../api/backup';
import { formatKm } from '../utils/format';
import { canDo, roleLabel } from '../utils/permissions';
import { Button, Card, Spinner, ErrorMessage, ConfirmDialog } from '../components/UI';
import CopyCarName from '../components/CopyCarName';
import PassportDialog from '../components/PassportDialog';
import Toast from '../components/Toast';
import SharingCard from '../components/SharingCard';

const FUEL_TYPES = [
  { value: 'petrol', label: 'Бензин' },
  { value: 'diesel', label: 'Дизель' },
  { value: 'lpg', label: 'ГБО' },
  { value: 'electric', label: 'Електро' },
  { value: 'hybrid', label: 'Гібрид' },
];

const fuelLabel = (value) => FUEL_TYPES.find((f) => f.value === value)?.label || value;


function intervalsPlural(n) {
  const tens = n % 100;
  const ones = n % 10;
  if (ones === 1 && tens !== 11) return 'інтервал';
  if (ones >= 2 && ones <= 4 && (tens < 12 || tens > 14)) return 'інтервали';
  return 'інтервалів';
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
    <Card data-tour="settings-more">
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

// One row in the settings list: an icon, a title, a subtitle, and the whole
// card navigates. The pattern repeated four times, so it is one component now.
function SettingsRow({ to, icon: Icon, tone = 'amber', title, subtitle, tourId }) {
  return (
    <Link
      to={to}
      data-tour={tourId}
      className="block transition active:scale-[0.99] motion-reduce:active:scale-100"
    >
      <Card className="flex items-center gap-3 transition-colors hover:border-edge-soft">
        <span
          className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${
            tone === 'signal' ? 'bg-signal/15' : 'bg-amber/15'
          }`}
        >
          <Icon className={`h-5 w-5 ${tone === 'signal' ? 'text-signal' : 'text-amber'}`} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-fg">{title}</p>
          <p className="truncate text-xs text-mist">{subtitle}</p>
        </div>
        <ChevronRight className="h-4 w-4 flex-shrink-0 text-mist" />
      </Card>
    </Link>
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
  const removeCar = useCarStore((s) => s.removeCar);
  const resetCars = useCarStore((s) => s.reset);
  const logout = useAuthStore((s) => s.logout);
  const { start: startTour } = useTour();

  const handleLogout = () => {
    resetCars();
    logout();
  };

  // A tour whose first step has a static path can be launched from anywhere; the
  // overlay drives the rest. The home tour targets header/dashboard elements, so
  // it starts on «/». Navigate first, then hand control to the overlay.
  const openTour = (name) => {
    const first = TOURS[name].steps[0];
    navigate(typeof first.path === 'string' ? first.path : '/');
    startTour(name);
  };

  const intervals = useCarStore((s) => s.intervals);
  const intervalsLoading = useCarStore((s) => s.intervalsLoading);
  const intervalsError = useCarStore((s) => s.intervalsError);
  const fetchIntervals = useCarStore((s) => s.fetchIntervals);
  const addInterval = useCarStore((s) => s.addInterval);
  const editInterval = useCarStore((s) => s.editInterval);
  const removeInterval = useCarStore((s) => s.removeInterval);
  const addIntervalPresets = useCarStore((s) => s.addIntervalPresets);
  const completeInterval = useCarStore((s) => s.completeInterval);

  const [deletingCar, setDeletingCar] = useState(null);
  const [passportCar, setPassportCar] = useState(null);
  const [reportingCarId, setReportingCarId] = useState(null);
  const [csvCarId, setCsvCarId] = useState(null);
  const location = useLocation();
  const navigate = useNavigate();
  const [toast, setToast] = useState(location.state?.toast || '');
  const [actionError, setActionError] = useState('');

  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;
  // Intervals are the owner's regimen; an editor may still close a completed one.


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

      <PassportDialog
        car={passportCar}
        open={passportCar !== null}
        onClose={() => setPassportCar(null)}
        onToast={setToast}
      />


      <div className="flex items-center justify-between px-1">
        <h1 className="font-display text-lg font-semibold text-fg">Налаштування</h1>
        <Button
          variant="secondary"
          onClick={() => navigate('/garage/new')}
          className="px-3 py-1.5"
        >
          <Plus className="h-4 w-4" />
          Додати авто
        </Button>
      </div>

      {carsError && <ErrorMessage>{carsError}</ErrorMessage>}
      {actionError && <ErrorMessage>{actionError}</ErrorMessage>}

      {carsLoaded && cars.length === 0 && (
        <Card className="flex flex-col items-center gap-3 p-8 text-center">
          <Car className="h-8 w-8 text-mist/70" />
          <p className="text-sm text-mist">У гаражі поки порожньо. Додайте своє перше авто.</p>
        </Card>
      )}

      {cars.map((car, ci) => {
        const isActive = String(car.id) === String(activeCarId);
        const isOwner = canDo(car.your_role, 'car:edit');
        return (
          <Card
            key={car.id}
            data-tour={ci === 0 ? 'settings-cars' : undefined}
            className={isActive ? 'border-amber/50 ring-1 ring-amber/30' : ''}
          >
            <>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-base font-semibold text-fg">
                      <CopyCarName car={car} onCopied={setToast}>
                        {car.brand} {car.model}
                        {car.generation ? ` ${car.generation}` : ''}
                      </CopyCarName>
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
                        onClick={() => setPassportCar(car)}
                        aria-label="QR-паспорт авто"
                        title="QR-паспорт"
                        className="px-3 py-2"
                      >
                        <QrCode className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={() => navigate(`/garage/${car.id}/edit`)}
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
          </Card>
        );
      })}

      {/* Cars end here; what follows is the account and per-car tools. The
          divider is the seam the user asked for: garage above, settings below. */}
      {cars.length > 0 && <div className="border-t border-edge" />}

      <SettingsRow
        to="/profile"
        icon={UserCircle}
        tone="signal"
        title="Профіль"
        subtitle="Імʼя, пошта, пароль і Telegram"
        tourId="settings-profile"
      />

      <SettingsRow
        to="/notifications"
        icon={Bell}
        tone="signal"
        title="Сповіщення"
        subtitle="Нагадування про ТО, щотижневий підсумок"
      />

      {activeCar && (
        <SettingsRow
          to="/intervals"
          icon={Wrench}
          title="Інтервали ТО"
          subtitle={
            intervals.length
              ? `${intervals.length} ${intervalsPlural(intervals.length)} · олива, фільтри, ГРМ`
              : 'Ще не налаштовані'
          }
        />
      )}

      {activeCar && (
        <SettingsRow
          to="/documents"
          icon={FileText}
          title="Документи"
          subtitle="Техпаспорт, поліс, чеки"
        />
      )}

      {activeCar && (
        <SettingsRow to="/tires" icon={CircleDot} title="Шини" subtitle="Зимові, літні, всесезонні" />
      )}

      {activeCar && <SharingCard key={`sharing-${activeCar.id}`} car={activeCar} onToast={setToast} />}

      {activeCar && <DiagnosticsCard />}

      <DataCard onToast={setToast} onImported={() => fetchCars().catch(() => {})} />

      <Card>
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
          <Sparkles className="h-4 w-4 text-amber" />
          Тури застосунком
        </h2>
        <p className="mt-1 text-xs text-mist">
          Короткі екскурсії розділами — покажуть, що де і як працює.
        </p>
        <div className="mt-3 divide-y divide-edge">
          {TOUR_ORDER.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => openTour(name)}
              className="flex w-full items-center justify-between gap-2 py-2.5 text-left transition active:scale-[0.99] first:pt-0 last:pb-0 motion-reduce:active:scale-100"
            >
              <span className="text-sm font-medium text-fg">{TOURS[name].label}</span>
              <ChevronRight className="h-4 w-4 flex-shrink-0 text-mist" />
            </button>
          ))}
        </div>
      </Card>

      <Button variant="ghost" onClick={handleLogout} className="w-full text-mist">
        <LogOut className="h-4 w-4" />
        Вийти
      </Button>
    </div>
  );
}
