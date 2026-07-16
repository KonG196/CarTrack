import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useCarStore } from '../store/carStore';
import { isNetworkError } from '../api/client';
import { getLog } from '../api/logs';
import { uploadPhoto } from '../api/photos';
import { emptyFormValues, entryToFormValues, todayIso } from '../utils/entryForm';
import { canDo } from '../utils/permissions';
import EntryForm, { ENTRY_TYPES } from '../components/EntryForm';
import { Card, Spinner, ErrorMessage } from '../components/UI';

export default function AddEntry() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const cars = useCarStore((s) => s.cars);
  const carsLoaded = useCarStore((s) => s.carsLoaded);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const addLog = useCarStore((s) => s.addLog);
  const enqueueLog = useCarStore((s) => s.enqueueLog);
  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;

  const fromId = searchParams.get('from');

  // duplication source: taken from the store when present, otherwise fetched
  const [source, setSource] = useState(null);
  const [sourceLoading, setSourceLoading] = useState(Boolean(fromId));
  const [sourceError, setSourceError] = useState('');

  const paramType = searchParams.get('type');
  const type = ENTRY_TYPES.some((t) => t.value === paramType)
    ? paramType
    : source?.type || 'refuel';
  const setType = (t) => {
    const params = { type: t };
    if (fromId) params.from = fromId;
    setSearchParams(params, { replace: true });
  };

  useEffect(() => {
    if (!fromId) {
      setSource(null);
      setSourceLoading(false);
      return undefined;
    }
    let cancelled = false;
    setSourceLoading(true);
    setSourceError('');
    const cached = useCarStore
      .getState()
      .logs.items.find((l) => String(l.id) === String(fromId));
    (cached ? Promise.resolve(cached) : getLog(fromId))
      .then((log) => {
        if (!cancelled) setSource(log);
      })
      .catch(() => {
        if (!cancelled) setSourceError('Не вдалося завантажити запис для дублювання');
      })
      .finally(() => {
        if (!cancelled) setSourceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fromId]);

  // Duplicate: everything from the source entry, but date = today,
  // odometer = the car's current one, photos are not copied.
  const initialValues = useMemo(() => {
    const values = source ? entryToFormValues(source) : emptyFormValues();
    values.date = todayIso();
    if (activeCar) values.odometer = String(activeCar.current_odometer);
    return values;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, activeCar?.id]);

  const [submitting, setSubmitting] = useState(false);
  const [scannedFile, setScannedFile] = useState(null);

  const handleSubmit = async (payload) => {
    setSubmitting(true);
    let toast = 'Запис додано';
    try {
      const log = await addLog(payload);
      if (scannedFile && payload.type === 'refuel') {
        try {
          await uploadPhoto(log.id, scannedFile);
        } catch {
          toast = 'Запис додано, але фото не додалось';
        }
      }
      navigate('/logbook', { state: { toast } });
    } catch (err) {
      if (isNetworkError(err)) {
        try {
          await enqueueLog(payload);
        } catch {
          setSubmitting(false);
          throw err;
        }
        navigate('/logbook', {
          state: {
            toast: 'Немає звʼязку — запис збережено локально і відправиться пізніше',
            toastVariant: 'warn',
          },
        });
        return;
      }
      setSubmitting(false);
      throw err;
    }
  };

  if (carsLoaded && !activeCar) {
    return (
      <Card className="rise-in mt-8 p-8 text-center">
        <p className="text-sm text-mist">
          Щоб додати запис, спершу створіть авто в розділі{' '}
          <Link to="/garage" className="text-amber hover:text-amber-deep">
            «Налаштування»
          </Link>
          .
        </p>
      </Card>
    );
  }

  if (carsLoaded && activeCar && !canDo(activeCar.your_role, 'log:create')) {
    return (
      <Card className="rise-in mt-8 p-8 text-center">
        <p className="text-sm text-mist">
          Ви маєте доступ до {activeCar.brand} {activeCar.model} лише для перегляду, тож додавати
          записи не можна. Попросіть власника змінити вашу роль на «Редактор».
        </p>
        <Link
          to="/logbook"
          className="mt-3 inline-block text-sm font-medium text-amber hover:text-amber-deep"
        >
          До журналу
        </Link>
      </Card>
    );
  }

  if (!carsLoaded || sourceLoading) return <Spinner />;

  return (
    <div className="stagger space-y-4">
      {sourceError && <ErrorMessage>{sourceError}</ErrorMessage>}
      <EntryForm
        key={`car-${activeCar.id}-${source ? `from-${source.id}` : 'new'}`}
        mode="create"
        carId={activeCar.id}
        car={activeCar}
        type={type}
        onTypeChange={setType}
        initialValues={initialValues}
        submitting={submitting}
        onSubmit={handleSubmit}
        scannedFile={scannedFile}
        onScanFile={setScannedFile}
      />
    </div>
  );
}
