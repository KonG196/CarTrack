import { useEffect, useRef, useState } from 'react';
import {
  Car,
  Plus,
  ChevronRight,
  FileDown,
  Loader2,
  Database,
  Upload,
  Activity,
  Wrench,
  UserCircle,
  FileText,
  CircleDot,
  LogOut,
  Sparkles,
  SlidersHorizontal,
  ShieldCheck,
} from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../store/authStore';
import { useTour } from '../tour/TourContext';
import { TOURS, TOUR_ORDER } from '../tour/tourSteps';
import { useCarStore } from '../store/carStore';
import { extractError } from '../api/client';
import { downloadCarReport } from '../api/reports';
import * as backupApi from '../api/backup';
import { canDo } from '../utils/permissions';
import { Button, Card, Spinner, ErrorMessage, ConfirmDialog } from '../components/UI';
import PassportDialog from '../components/PassportDialog';
import Toast from '../components/Toast';
import SharingCard from '../components/SharingCard';
import InstallAppCard from '../components/InstallAppCard';
import GarageCarCard from '../components/GarageCarCard';

// How many cars the settings page previews before offering "view all".
const GARAGE_PREVIEW_COUNT = 2;

const FUEL_TYPES = [
  { value: 'petrol', labelKey: 'fuelPetrol' },
  { value: 'diesel', labelKey: 'fuelDiesel' },
  { value: 'lpg', labelKey: 'fuelLpg' },
  { value: 'electric', labelKey: 'fuelElectric' },
  { value: 'hybrid', labelKey: 'fuelHybrid' },
];

function DataCard({ onToast, onImported }) {
  const { t } = useTranslation();
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
      onToast(t('garage.dataExportDone'));
    } catch (err) {
      setError(extractError(err, t('garage.dataExportError')));
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
          ? t('garage.importNotJson')
          : err.message || t('garage.importNotBackup')
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
        t('garage.importDone', {
          cars: result.cars_created,
          logs: result.logs_created,
          intervals: result.intervals_created,
        })
      );
      await onImported();
    } catch (err) {
      setError(extractError(err, t('garage.dataImportError')));
    } finally {
      setImporting(false);
    }
  };

  return (
    <Card data-tour="settings-more">
      <div>
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
          <Database className="h-4 w-4 text-mist" />
          {t('garage.dataTitle')}
        </h2>
        <p className="mt-1 text-xs text-mist">
          {t('garage.dataDesc')}
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
          {exporting ? t('garage.exporting') : t('garage.exportAll')}
        </Button>
        <Button
          variant="secondary"
          onClick={() => fileInputRef.current?.click()}
          disabled={exporting || importing}
          className="w-full"
        >
          {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {importing ? t('garage.importing') : t('garage.importFromFile')}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json,.json"
          onChange={handleFileChange}
          className="hidden"
          aria-label={t('garage.exportFileLabel')}
        />
      </div>

      <ConfirmDialog
        open={pendingImport !== null}
        title={t('garage.importConfirmTitle')}
        message={
          pendingImport
            ? t('garage.importConfirmMessage', {
                cars: pendingImport.counts.cars,
                logs: pendingImport.counts.logs,
                intervals: pendingImport.counts.intervals,
              })
            : ''
        }
        confirmLabel={t('garage.importConfirmLabel')}
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
  const { t } = useTranslation();

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
            <Activity className="h-4 w-4 text-amber" />
            {t('garage.diagnosticsTitle')}
          </h2>
          <p className="mt-1 text-xs text-mist">
            {t('garage.diagnosticsDesc')}
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => navigate('/diagnostics')}
          className="flex-shrink-0 px-3 py-1.5"
        >
          {t('garage.open')}
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
  const { t } = useTranslation();
  const fuelLabel = (value) => {
    const item = FUEL_TYPES.find((f) => f.value === value);
    return item ? t(`garage.${item.labelKey}`) : value;
  };
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
  const user = useAuthStore((s) => s.user);
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
      setToast(t('garage.carDeleted'));
    } catch (err) {
      setActionError(extractError(err, t('garage.carDeleteError')));
    }
  };




  const handleDownloadReport = async (car) => {
    if (reportingCarId != null) return;
    setActionError('');
    setReportingCarId(car.id);
    try {
      await downloadCarReport(car.id);
      setToast(t('garage.reportDone'));
    } catch (err) {
      setActionError(extractError(err, t('garage.reportError')));
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
      setToast(t('garage.csvDone'));
    } catch (err) {
      setActionError(extractError(err, t('garage.csvError')));
    } finally {
      setCsvCarId(null);
    }
  };


  if (carsLoading && !carsLoaded) return <Spinner />;

  return (
    // Extra bottom padding: the last control («Вийти») otherwise ends level with
    // the nav, where the round «Add» button juts up and covers it with no way to
    // scroll it clear. This lifts the page's scroll end above the «+».
    <div className="stagger space-y-4 pb-12">
      <Toast message={toast} onDone={clearToast} />

      <ConfirmDialog
        open={deletingCar !== null}
        title={t('garage.deleteCarTitle')}
        message={
          deletingCar
            ? t('garage.deleteCarMessage', {
                brand: deletingCar.brand,
                model: deletingCar.model,
              })
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
        <h1 className="font-display text-lg font-semibold text-fg">{t('garage.title')}</h1>
        <Button
          variant="secondary"
          onClick={() => navigate('/garage/new')}
          className="px-3 py-1.5"
        >
          <Plus className="h-4 w-4" />
          {t('garage.addCar')}
        </Button>
      </div>

      {carsError && <ErrorMessage>{carsError}</ErrorMessage>}
      {actionError && <ErrorMessage>{actionError}</ErrorMessage>}

      {carsLoaded && cars.length === 0 && (
        <Card className="flex flex-col items-center gap-3 p-8 text-center">
          <Car className="h-8 w-8 text-mist/70" />
          <p className="text-sm text-mist">{t('garage.emptyGarage')}</p>
        </Card>
      )}

      {/* Only the first couple of cars live on the settings page — a long garage
          gets its own page (below) so this one stays scannable. The active car is
          floated to the front so it's always one of the two shown. */}
      {[...cars]
        .sort((a, b) => (String(b.id) === String(activeCarId)) - (String(a.id) === String(activeCarId)))
        .slice(0, GARAGE_PREVIEW_COUNT)
        .map((car, ci) => {
          const isActive = String(car.id) === String(activeCarId);
          const isOwner = canDo(car.your_role, 'car:edit');
          return (
            <GarageCarCard
              key={car.id}
              car={car}
              isActive={isActive}
              isOwner={isOwner}
              tourId={ci === 0 ? 'settings-cars' : undefined}
              fuelLabel={fuelLabel}
              reporting={String(reportingCarId) === String(car.id)}
              csvBusy={String(csvCarId) === String(car.id)}
              anyBusy={reportingCarId != null || csvCarId != null}
              onSetActive={() => setActiveCar(car.id)}
              onEdit={() => navigate(`/garage/${car.id}/edit`)}
              onSpecs={() => navigate(`/garage/${car.id}/specs`)}
              onReport={() => handleDownloadReport(car)}
              onCsv={() => handleDownloadCsv(car)}
              onPassport={() => setPassportCar(car)}
              onDelete={() => setDeletingCar(car)}
              onCopied={setToast}
            />
          );
        })}

      {cars.length > GARAGE_PREVIEW_COUNT && (
        <Link
          to="/garage/cars"
          className="flex items-center justify-center gap-1.5 rounded-2xl border border-edge py-3 text-sm font-medium text-mist transition-colors hover:border-edge-soft hover:text-fg"
        >
          {t('garage.viewAllCars', { count: cars.length })}
          <ChevronRight className="h-4 w-4" />
        </Link>
      )}

      {/* Cars end here; what follows is the account and per-car tools. The
          divider is the seam the user asked for: garage above, settings below. */}
      {cars.length > 0 && <div className="border-t border-edge" />}

      <SettingsRow
        to="/preferences"
        icon={SlidersHorizontal}
        title={t('garage.preferencesTitle')}
        subtitle={t('garage.preferencesSubtitle')}
      />

      <SettingsRow
        to="/profile"
        icon={UserCircle}
        tone="signal"
        title={t('garage.profileTitle')}
        subtitle={t('garage.profileSubtitle')}
        tourId="settings-profile"
      />

      {user?.is_superadmin && (
        <SettingsRow
          to="/admin"
          icon={ShieldCheck}
          title={t('admin.entryPoint')}
          subtitle={t('admin.entryPointDesc')}
        />
      )}

      <InstallAppCard />

      {activeCar && (
        <SettingsRow
          to="/intervals"
          icon={Wrench}
          title={t('garage.intervalsTitle')}
          subtitle={
            intervals.length
              ? t('garage.intervalsSummary', { count: intervals.length })
              : t('garage.intervalsNotSet')
          }
        />
      )}

      {activeCar && (
        <SettingsRow
          to="/documents"
          icon={FileText}
          title={t('garage.documentsTitle')}
          subtitle={t('garage.documentsSubtitle')}
        />
      )}

      {activeCar && (
        <SettingsRow
          to="/tires"
          icon={CircleDot}
          title={t('garage.tiresTitle')}
          subtitle={t('garage.tiresSubtitle')}
        />
      )}

      {activeCar && <SharingCard key={`sharing-${activeCar.id}`} car={activeCar} onToast={setToast} />}

      {activeCar && <DiagnosticsCard />}

      <DataCard onToast={setToast} onImported={() => fetchCars().catch(() => {})} />

      <Card>
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
          <Sparkles className="h-4 w-4 text-amber" />
          {t('garage.toursTitle')}
        </h2>
        <p className="mt-1 text-xs text-mist">
          {t('garage.toursDesc')}
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
        {t('garage.logout')}
      </Button>
    </div>
  );
}
