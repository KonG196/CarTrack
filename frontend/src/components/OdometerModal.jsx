import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Gauge } from 'lucide-react';
import Modal from './UI/Modal';
import { Button, TextField, ErrorMessage } from './UI';
import { useCarStore } from '../store/carStore';

// Quick odometer update, right on the dashboard. The whole odometer chip opens
// this instead of navigating to the full car editor: bumping the reading is the
// one thing done often, and a modal keeps you where you are. It only writes
// current_odometer — nothing else about the car.
export default function OdometerModal({ open, onClose, car, onSaved }) {
  const { t } = useTranslation();
  const editCar = useCarStore((s) => s.editCar);
  const [value, setValue] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  // Seed with the current reading each time it opens, ready to overwrite.
  useEffect(() => {
    if (open && car) {
      setValue(String(car.current_odometer ?? ''));
      setError('');
    }
  }, [open, car]);

  const save = async () => {
    const next = parseInt(value, 10);
    if (!Number.isFinite(next) || next < 0) return setError(t('carEditor.errOdometer'));
    setError('');
    setSaving(true);
    try {
      await editCar(car.id, { current_odometer: next });
      onSaved?.();
      onClose();
    } catch {
      setError(t('odometerModal.errSave'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t('odometerModal.title')}
      size="sm"
      footer={
        <Button onClick={save} disabled={saving} className="w-full">
          {saving ? t('common.saving') : t('common.save')}
        </Button>
      }
    >
      <div className="mb-3 flex items-center gap-3">
        <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-amber/15">
          <Gauge className="h-5 w-5 text-amber" />
        </span>
        <p className="text-sm text-mist">{t('odometerModal.subtitle')}</p>
      </div>
      <TextField
        label={t('carEditor.odometer')}
        type="number"
        inputMode="numeric"
        enterKeyHint="done"
        min="0"
        numeric
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            save();
          }
        }}
      />
      <ErrorMessage>{error}</ErrorMessage>
    </Modal>
  );
}
