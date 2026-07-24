import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Gauge } from 'lucide-react';
import Modal from './UI/Modal';
import { Button, TextField, ErrorMessage } from './UI';
import { useCarStore } from '../store/carStore';
import { currentUnits } from '../store/unitStore';
import { isImperial, kmFromDistance, KM_PER_MILE } from '../units';
import { distanceUnitLabel } from '../utils/format';

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
  const inputRef = useRef(null);

  // Seed with the current reading (in display units) each time it opens, then
  // focus with the caret at the END — the reading is pre-filled and the user
  // appends to it, so a caret at position 0 (the old autoFocus behaviour) meant
  // typing landed before the first digit. Focus AFTER the seed paints.
  useEffect(() => {
    if (open && car) {
      const km = car.current_odometer ?? '';
      const shown =
        km === '' ? '' : isImperial(currentUnits()) ? Math.round(km / KM_PER_MILE) : km;
      setValue(String(shown));
      setError('');
      requestAnimationFrame(() => {
        const el = inputRef.current;
        if (!el) return;
        el.focus();
        const end = el.value.length;
        el.setSelectionRange(end, end);
      });
    }
  }, [open, car]);

  const save = async () => {
    const entered = parseInt(value, 10);
    if (!Number.isFinite(entered) || entered < 0) return setError(t('carEditor.errOdometer'));
    // Entered in display units; store metric.
    const next = Math.round(kmFromDistance(entered, currentUnits()));
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
        ref={inputRef}
        label={t('carEditor.odometer', { unit: distanceUnitLabel() })}
        type="number"
        inputMode="numeric"
        enterKeyHint="done"
        min="0"
        numeric
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
