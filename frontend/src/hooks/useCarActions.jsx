import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useCarStore } from '../store/carStore';
import { extractError } from '../api/client';
import { downloadCarReport } from '../api/reports';
import * as backupApi from '../api/backup';
import { ConfirmDialog, ErrorMessage } from '../components/UI';
import PassportDialog from '../components/PassportDialog';
import Toast from '../components/Toast';

// The per-car actions shared by the Garage page and the "all cars" page: make
// active, edit, specs, report/CSV download (with busy state), QR passport, and
// delete (with a confirm dialog). Returns the props to spread onto a
// GarageCarCard, plus an <Overlays/> element to render the modals/toast once.
export default function useCarActions() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const setActiveCar = useCarStore((s) => s.setActiveCar);
  const removeCar = useCarStore((s) => s.removeCar);

  const [deletingCar, setDeletingCar] = useState(null);
  const [passportCar, setPassportCar] = useState(null);
  const [reportingCarId, setReportingCarId] = useState(null);
  const [csvCarId, setCsvCarId] = useState(null);
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');

  const anyBusy = reportingCarId != null || csvCarId != null;

  const handleReport = async (car) => {
    if (anyBusy) return;
    setError('');
    setReportingCarId(car.id);
    try {
      await downloadCarReport(car.id);
      setToast(t('garage.reportDone'));
    } catch (err) {
      setError(extractError(err, t('garage.reportError')));
    } finally {
      setReportingCarId(null);
    }
  };

  const handleCsv = async (car) => {
    if (anyBusy) return;
    setError('');
    setCsvCarId(car.id);
    try {
      await backupApi.downloadCarCsv(car.id);
      setToast(t('garage.csvDone'));
    } catch (err) {
      setError(extractError(err, t('garage.csvError')));
    } finally {
      setCsvCarId(null);
    }
  };

  const confirmDelete = async () => {
    const car = deletingCar;
    setDeletingCar(null);
    if (!car) return;
    setError('');
    try {
      await removeCar(car.id);
      setToast(t('garage.carDeleted'));
    } catch (err) {
      setError(extractError(err, t('garage.carDeleteError')));
    }
  };

  // Build the props a GarageCarCard needs for a given car.
  const cardProps = (car, activeCarId) => ({
    reporting: String(reportingCarId) === String(car.id),
    csvBusy: String(csvCarId) === String(car.id),
    anyBusy,
    onSetActive: () => setActiveCar(car.id),
    onEdit: () => navigate(`/garage/${car.id}/edit`),
    onSpecs: () => navigate(`/garage/${car.id}/specs`),
    onReport: () => handleReport(car),
    onCsv: () => handleCsv(car),
    onPassport: () => setPassportCar(car),
    onDelete: () => setDeletingCar(car),
    onCopied: setToast,
  });

  const Overlays = () => (
    <>
      {error ? <ErrorMessage>{error}</ErrorMessage> : null}
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
        onConfirm={confirmDelete}
        onCancel={() => setDeletingCar(null)}
      />
      <PassportDialog
        car={passportCar}
        open={passportCar !== null}
        onClose={() => setPassportCar(null)}
        onToast={setToast}
      />
      <Toast message={toast} onDone={() => setToast('')} />
    </>
  );

  return { cardProps, Overlays, setToast };
}
