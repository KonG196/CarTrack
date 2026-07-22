import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Info, Sparkles } from 'lucide-react';
import { extractError } from '../api/client';
import {
  costEstimateSource,
  emptyCompleteValues,
  sumCostTotal,
  validateCompleteValues,
  completeValuesToPayload,
} from '../utils/completeForm';
import { Modal, Button, TextField, DateField, ErrorMessage } from './UI';

export default function CompleteIntervalModal({ interval, car, onComplete, onClose, onToast }) {
  const { t } = useTranslation();
  const open = interval != null;
  const [values, setValues] = useState(() => emptyCompleteValues({ car, interval }));
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // The note under the field promises where the number came from; the moment
  // the user types their own, it stops being true.
  const [costEdited, setCostEdited] = useState(false);

  const estimateSource = costEstimateSource(interval);
  const estimateClass = estimateSource === 'history' ? 'border-ok/60 text-ok' : '';

  useEffect(() => {
    if (!open) return;
    setValues(emptyCompleteValues({ car, interval }));
    setError('');
    setSubmitting(false);
    setCostEdited(false);
  }, [open, interval?.id, car?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (key) => (e) => setValues((v) => ({ ...v, [key]: e.target.value }));

  const setPartsCost = (e) => {
    const partsCost = e.target.value;
    setValues((v) => ({ ...v, partsCost, totalCost: sumCostTotal(partsCost, v.laborCost) }));
  };

  const setLaborCost = (e) => {
    const laborCost = e.target.value;
    setValues((v) => ({ ...v, laborCost, totalCost: sumCostTotal(v.partsCost, laborCost) }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const message = validateCompleteValues(values);
    if (message) return setError(message);
    setError('');
    setSubmitting(true);
    try {
      await onComplete(interval.id, completeValuesToPayload(values));
      onToast(t('completeInterval.savedToast'));
      onClose();
    } catch (err) {
      setError(extractError(err, t('completeInterval.saveError')));
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={interval ? t('completeInterval.title', { title: interval.title }) : ''} size="sm">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <TextField
            label={t('completeInterval.odometer')}
            type="number"
            inputMode="numeric"
            enterKeyHint="next"
            min="0"
            numeric
            required
            value={values.odometer}
            onChange={set('odometer')}
          />
          <DateField
          label={t('completeInterval.date')}
          required
          value={values.date}
          onChange={(v) => setValues((prev) => ({ ...prev, date: v }))}
        />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <TextField
            label={t('completeInterval.partsCost')}
            type="text"
            inputMode="decimal"
            enterKeyHint="next"
            numeric
            value={values.partsCost}
            onChange={setPartsCost}
          />
          <TextField
            label={t('completeInterval.laborCost')}
            type="text"
            inputMode="decimal"
            enterKeyHint="next"
            numeric
            value={values.laborCost}
            onChange={setLaborCost}
          />
        </div>
        <TextField
          label={t('completeInterval.totalCost')}
          type="text"
          inputMode="decimal"
          enterKeyHint="next"
          numeric
          className={estimateSource && !costEdited ? estimateClass : ''}
          value={values.totalCost}
          onChange={(e) => {
            setCostEdited(true);
            set('totalCost')(e);
          }}
        />
        {estimateSource && !costEdited && (
          // Two different claims, so two different looks. Green means «this is
          // what you paid» and carries the weight of the user's own records; the
          // market ballpark must never borrow that weight, or there is no reason
          // left to check it.
          <p
            className={`-mt-1 flex items-center gap-1.5 text-xs ${
              estimateSource === 'history' ? 'text-ok' : 'text-mist'
            }`}
          >
            {estimateSource === 'history' ? (
              <>
                <Sparkles className="h-3.5 w-3.5 flex-shrink-0" />
                {t('completeInterval.historyHint')}
              </>
            ) : (
              <>
                <Info className="h-3.5 w-3.5 flex-shrink-0" />
                {t('completeInterval.marketHint')}
              </>
            )}
          </p>
        )}
        <TextField
          label={t('completeInterval.notes')}
          enterKeyHint="done"
          value={values.notes}
          onChange={set('notes')}
        />
        <ErrorMessage>{error}</ErrorMessage>
        <div className="flex gap-2">
          <Button type="submit" disabled={submitting} className="flex-1">
            {submitting ? t('common.saving') : t('completeInterval.submit')}
          </Button>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
