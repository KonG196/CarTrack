import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Pencil, CopyPlus, Trash2, Plus, Loader2, Check, X } from 'lucide-react';
import { useCarStore } from '../store/carStore';
import { extractError } from '../api/client';
import { getLog } from '../api/logs';
import { uploadPhoto, getPhotoBlob, deletePhoto } from '../api/photos';
import { entryToFormValues } from '../utils/entryForm';
import { canDo, carIsShared } from '../utils/permissions';
import EntryForm from '../components/EntryForm';
import { LOG_TYPE_META, AuthorChip, authorLabel } from '../components/LogTimelineItem';
import { formatMoney, formatKm, formatDate } from '../utils/format';
import { maintenanceItemLabel, repairCategoryLabel } from '../i18n/domain';
import { warrantyStatus } from '../utils/warranty';
import { Button, Card, Spinner, ErrorMessage, Modal, ConfirmDialog } from '../components/UI';
import Toast from '../components/Toast';

// Entry type → logDetail translation key for the plain display label.
const TYPE_LABEL_KEYS = {
  refuel: 'typeRefuel',
  maintenance: 'typeMaintenance',
  repair: 'typeRepair',
  expense: 'typeExpense',
};

function DetailRow({ label, value }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <span className="flex-shrink-0 text-sm text-mist">{label}</span>
      <span className="min-w-0 text-right text-sm text-fg">{value}</span>
    </div>
  );
}

export default function LogDetail() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const cars = useCarStore((s) => s.cars);
  const members = useCarStore((s) => s.members);
  const membersCarId = useCarStore((s) => s.membersCarId);
  const editLog = useCarStore((s) => s.editLog);
  const removeLog = useCarStore((s) => s.removeLog);

  const [log, setLog] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [toast, setToast] = useState('');

  const [editing, setEditing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  // photos: id -> object URL (created here, revoked on unmount / delete)
  const [photoUrls, setPhotoUrls] = useState({});
  const urlsRef = useRef({});
  const [lightboxPhoto, setLightboxPhoto] = useState(null);
  const [confirmingPhotoDelete, setConfirmingPhotoDelete] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    getLog(id)
      .then((data) => {
        if (!cancelled) setLog(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err?.response?.status === 404
              ? t('logDetail.notFound')
              : t('logDetail.loadFailed')
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const photos = log?.photos || [];

  const car = log ? cars.find((c) => String(c.id) === String(log.car_id)) : null;
  const canWrite = canDo(car?.your_role, 'log:edit');
  const canManagePhotos = canDo(car?.your_role, 'photo:manage');
  const showAuthor =
    log != null && String(membersCarId) === String(log.car_id) && carIsShared(members);
  const author = showAuthor ? authorLabel(log) : null;

  useEffect(() => {
    let cancelled = false;
    photos.forEach((photo) => {
      if (urlsRef.current[photo.id]) return;
      getPhotoBlob(photo.id)
        .then((blob) => {
          if (cancelled) return;
          const url = URL.createObjectURL(blob);
          urlsRef.current[photo.id] = url;
          setPhotoUrls((prev) => ({ ...prev, [photo.id]: url }));
        })
        .catch(() => {});
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [log]);

  useEffect(
    () => () => {
      Object.values(urlsRef.current).forEach((url) => URL.revokeObjectURL(url));
    },
    []
  );

  const handleEditSubmit = async (payload) => {
    setSubmitting(true);
    try {
      const updated = await editLog(log.id, payload);
      setLog(updated);
      setEditing(false);
      setToast(t('logDetail.changesSaved'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    setConfirmingDelete(false);
    setActionError('');
    try {
      await removeLog(log.id);
      navigate('/logbook', { state: { toast: t('logDetail.entryDeleted') } });
    } catch (err) {
      setActionError(extractError(err, t('logDetail.deleteFailed')));
    }
  };

  const handleUploadPhoto = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file || uploading) return;
    setActionError('');
    setUploading(true);
    try {
      await uploadPhoto(log.id, file);
      const updated = await getLog(log.id);
      setLog(updated);
      setToast(t('logDetail.photoAdded'));
    } catch (err) {
      setActionError(extractError(err, t('logDetail.photoAddFailed')));
    } finally {
      setUploading(false);
    }
  };

  const handleDeletePhoto = async () => {
    const photo = lightboxPhoto;
    setConfirmingPhotoDelete(false);
    setLightboxPhoto(null);
    if (!photo) return;
    setActionError('');
    try {
      await deletePhoto(photo.id);
      const url = urlsRef.current[photo.id];
      if (url) {
        URL.revokeObjectURL(url);
        delete urlsRef.current[photo.id];
        setPhotoUrls((prev) => {
          const next = { ...prev };
          delete next[photo.id];
          return next;
        });
      }
      setLog((prev) =>
        prev ? { ...prev, photos: (prev.photos || []).filter((p) => p.id !== photo.id) } : prev
      );
      setToast(t('logDetail.photoDeleted'));
    } catch (err) {
      setActionError(extractError(err, t('logDetail.photoDeleteFailed')));
    }
  };

  if (loading) return <Spinner />;

  if (error || !log) {
    return (
      <div className="stagger space-y-4">
        <ErrorMessage>{error || t('logDetail.notFound')}</ErrorMessage>
        <Link
          to="/logbook"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-amber hover:text-amber-deep"
        >
          <ArrowLeft className="h-4 w-4" />
          {t('logDetail.toLogbook')}
        </Link>
      </div>
    );
  }

  const meta = LOG_TYPE_META[log.type] || LOG_TYPE_META.expense;
  const Icon = meta.icon;
  const typeLabel = t(`logDetail.${TYPE_LABEL_KEYS[log.type] || TYPE_LABEL_KEYS.expense}`);

  const warranty =
    log.type === 'repair' && log.repair
      ? warrantyStatus(log.repair, {
          repairDate: log.date,
          repairOdometer: log.odometer,
          currentOdometer: cars.find((c) => c.id === log.car_id)?.current_odometer,
        })
      : null;

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />

      <ConfirmDialog
        open={confirmingDelete}
        title={t('logDetail.deleteEntryTitle')}
        message={t('logDetail.deleteEntryMessage')}
        onConfirm={handleDelete}
        onCancel={() => setConfirmingDelete(false)}
      />

      <div className="flex items-center justify-between gap-2 px-1">
        <Link
          to="/logbook"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-mist transition-colors hover:text-fg"
        >
          <ArrowLeft className="h-4 w-4" />
          {t('logDetail.logbook')}
        </Link>
        <span className="text-xs text-mist/70">{t('logDetail.entryNumber', { id: log.id })}</span>
      </div>

      {actionError && <ErrorMessage>{actionError}</ErrorMessage>}

      {editing ? (
        <>
          <div className="flex items-center gap-2 px-1">
            <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${meta.bg}`}>
              <Icon className={`h-4 w-4 ${meta.color}`} />
            </span>
            <h1 className="font-display text-base font-semibold text-fg">{t('common.edit')} · {typeLabel}</h1>
          </div>
          <EntryForm
            mode="edit"
            car={car}
            type={log.type}
            lockedType
            initialValues={entryToFormValues(log)}
            submitting={submitting}
            onSubmit={handleEditSubmit}
            onCancel={() => setEditing(false)}
          />
        </>
      ) : (
        <>
          <Card data-tour="log-detail">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <span
                  className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${meta.bg}`}
                >
                  <Icon className={`h-5 w-5 ${meta.color}`} />
                </span>
                <div>
                  <p className="text-base font-semibold text-fg">{typeLabel}</p>
                  <p className="mt-0.5 text-xs text-mist">
                    {formatDate(log.date)} · {formatKm(log.odometer)}
                  </p>
                </div>
              </div>
              <span className="whitespace-nowrap text-lg font-semibold text-fg">
                {formatMoney(log.total_cost)}
              </span>
            </div>

            <div className="mt-3 divide-y divide-edge border-t border-edge pt-1">
              {log.type === 'refuel' && log.refuel && (
                <>
                  <DetailRow
                    label={t('logDetail.liters')}
                    value={t('logDetail.litersValue', {
                      value: Number(log.refuel.liters).toFixed(2),
                    })}
                  />
                  <DetailRow
                    label={t('logDetail.pricePerLiter')}
                    value={formatMoney(log.refuel.price_per_liter)}
                  />
                  <DetailRow
                    label={t('logDetail.fullTank')}
                    value={
                      log.refuel.is_full_tank ? (
                        <span className="inline-flex items-center gap-1 text-ok">
                          <Check className="h-3.5 w-3.5" /> {t('common.yes')}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-mist">
                          <X className="h-3.5 w-3.5" /> {t('common.no')}
                        </span>
                      )
                    }
                  />
                  {log.refuel.gas_station && (
                    <DetailRow label={t('logDetail.gasStation')} value={log.refuel.gas_station} />
                  )}
                </>
              )}

              {log.type === 'maintenance' && log.maintenance && (
                <>
                  <div className="py-1.5">
                    <span className="text-sm text-mist">{t('logDetail.whatReplaced')}</span>
                    {(log.maintenance.items || []).length > 0 ? (
                      <ul className="mt-1.5 space-y-1">
                        {log.maintenance.items.map((item) => (
                          <li
                            key={item}
                            className="flex items-center gap-2 text-sm text-fg"
                          >
                            <Check className="h-3.5 w-3.5 flex-shrink-0 text-ok" />
                            {maintenanceItemLabel(item)}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-1 text-sm text-mist">—</p>
                    )}
                  </div>
                  <DetailRow label={t('logDetail.parts')} value={formatMoney(log.maintenance.parts_cost)} />
                  <DetailRow label={t('logDetail.labor')} value={formatMoney(log.maintenance.labor_cost)} />
                </>
              )}

              {log.type === 'repair' && log.repair && (
                <>
                  <DetailRow label={t('logDetail.category')} value={repairCategoryLabel(log.repair.category)} />
                  {log.repair.part_name && (
                    <DetailRow label={t('logDetail.part')} value={log.repair.part_name} />
                  )}
                  {log.repair.warranty_months != null && (
                    <DetailRow
                      label={t('logDetail.warranty')}
                      value={t('logDetail.warrantyMonths', { months: log.repair.warranty_months })}
                    />
                  )}
                  {log.repair.warranty_km != null && (
                    <DetailRow label={t('logDetail.warrantyKm')} value={formatKm(log.repair.warranty_km)} />
                  )}
                  {warranty && (
                    <DetailRow
                      label={t('logDetail.warrantyStatus')}
                      value={
                        warranty.active ? (
                          <span className="font-medium text-ok">
                            {t('logDetail.warrantyActive')}
                            {warranty.expiry
                              ? t('logDetail.warrantyUntil', {
                                  date: formatDate(warranty.expiry.toISOString()),
                                })
                              : ''}
                            {warranty.kmLeft != null
                              ? t('logDetail.warrantyKmLeft', { km: formatKm(warranty.kmLeft) })
                              : ''}
                          </span>
                        ) : (
                          <span className="text-mist">{t('logDetail.warrantyExpired')}</span>
                        )
                      }
                    />
                  )}
                </>
              )}

              {log.notes && (
                <div className="py-1.5">
                  <span className="text-sm text-mist">{t('logDetail.notes')}</span>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-fg">{log.notes}</p>
                </div>
              )}

              <DetailRow label={t('logDetail.created')} value={formatDate(log.created_at)} />

              {author && (
                <div className="flex items-baseline justify-between gap-3 py-1.5">
                  <span className="flex-shrink-0 text-sm text-mist">{t('logDetail.author')}</span>
                  <AuthorChip label={author} />
                </div>
              )}
            </div>
          </Card>

          <Card>
            <h2 className="mb-2 font-display text-sm font-semibold text-fg">{t('logDetail.photos')}</h2>
            <div className="grid grid-cols-3 gap-2">
              {photos.length === 0 && !canManagePhotos && (
                <p className="col-span-3 py-2 text-sm text-mist">{t('logDetail.noPhotos')}</p>
              )}
              {photos.map((photo) => (
                <button
                  key={photo.id}
                  type="button"
                  onClick={() => setLightboxPhoto(photo)}
                  aria-label={t('logDetail.openPhoto', { name: photo.filename })}
                  className="h-24 overflow-hidden rounded-xl border border-edge bg-garage"
                >
                  {photoUrls[photo.id] ? (
                    <img
                      src={photoUrls[photo.id]}
                      alt={photo.filename}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <span className="flex h-full w-full items-center justify-center">
                      <Loader2 className="h-4 w-4 animate-spin text-mist/70" />
                    </span>
                  )}
                </button>
              ))}
              {canManagePhotos && (
                <label
                  className={`flex h-24 flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-edge-soft text-xs font-medium transition-colors ${
                    uploading
                      ? 'pointer-events-none text-mist'
                      : 'cursor-pointer text-mist hover:border-amber hover:text-amber-deep'
                  }`}
                >
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    disabled={uploading}
                    onChange={handleUploadPhoto}
                  />
                  {uploading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4" />
                  )}
                  {t('logDetail.addPhoto')}
                </label>
              )}
            </div>
          </Card>

          {canWrite && (
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => setEditing(true)} className="flex-1">
                <Pencil className="h-4 w-4" />
                {t('common.edit')}
              </Button>
              <Button
                variant="secondary"
                onClick={() => navigate(`/add?from=${log.id}`)}
                className="flex-1"
              >
                <CopyPlus className="h-4 w-4" />
                {t('logDetail.repeat')}
              </Button>
              <Button
                variant="danger"
                onClick={() => setConfirmingDelete(true)}
                aria-label={t('logDetail.deleteEntry')}
                className="px-3"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          )}
        </>
      )}

      <Modal
        open={lightboxPhoto !== null}
        onClose={() => setLightboxPhoto(null)}
        title={lightboxPhoto?.filename}
        footer={
          canManagePhotos ? (
            <Button
              variant="danger"
              onClick={() => setConfirmingPhotoDelete(true)}
              className="flex-1"
            >
              <Trash2 className="h-4 w-4" />
              {t('logDetail.deletePhoto')}
            </Button>
          ) : null
        }
      >
        {lightboxPhoto && photoUrls[lightboxPhoto.id] ? (
          <img
            src={photoUrls[lightboxPhoto.id]}
            alt={lightboxPhoto.filename}
            className="max-h-[70vh] w-full rounded-xl object-contain"
          />
        ) : (
          <Spinner className="py-8" />
        )}
      </Modal>

      <ConfirmDialog
        open={confirmingPhotoDelete}
        title={t('logDetail.deletePhotoTitle')}
        message={t('logDetail.deletePhotoMessage')}
        onConfirm={handleDeletePhoto}
        onCancel={() => setConfirmingPhotoDelete(false)}
      />
    </div>
  );
}
