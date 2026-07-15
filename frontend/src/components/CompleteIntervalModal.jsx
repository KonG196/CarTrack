import { useEffect, useState } from 'react';
import { extractError } from '../api/client';
import {
  emptyCompleteValues,
  sumCostTotal,
  validateCompleteValues,
  completeValuesToPayload,
} from '../utils/completeForm';
import { Modal, Button, TextField, ErrorMessage } from './UI';

export default function CompleteIntervalModal({ interval, car, onComplete, onClose, onToast }) {
  const open = interval != null;
  const [values, setValues] = useState(() => emptyCompleteValues({ car, interval }));
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setValues(emptyCompleteValues({ car, interval }));
    setError('');
    setSubmitting(false);
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
      onToast('Записано ТО і оновлено інтервал');
      onClose();
    } catch (err) {
      setError(extractError(err, 'Не вдалося записати ТО'));
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={interval ? `Виконано: ${interval.title}` : ''} size="sm">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <TextField
            label="Пробіг, км"
            type="number"
            inputMode="numeric"
            enterKeyHint="next"
            min="0"
            numeric
            required
            value={values.odometer}
            onChange={set('odometer')}
          />
          <TextField label="Дата" type="date" required value={values.date} onChange={set('date')} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <TextField
            label="Запчастини, ₴"
            type="text"
            inputMode="decimal"
            enterKeyHint="next"
            numeric
            value={values.partsCost}
            onChange={setPartsCost}
          />
          <TextField
            label="Робота, ₴"
            type="text"
            inputMode="decimal"
            enterKeyHint="next"
            numeric
            value={values.laborCost}
            onChange={setLaborCost}
          />
        </div>
        <TextField
          label="Вартість, ₴"
          type="text"
          inputMode="decimal"
          enterKeyHint="next"
          numeric
          value={values.totalCost}
          onChange={set('totalCost')}
        />
        <TextField
          label="Нотатка"
          enterKeyHint="done"
          value={values.notes}
          onChange={set('notes')}
        />
        <ErrorMessage>{error}</ErrorMessage>
        <div className="flex gap-2">
          <Button type="submit" disabled={submitting} className="flex-1">
            {submitting ? 'Збереження…' : 'Записати ТО'}
          </Button>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Скасувати
          </Button>
        </div>
      </form>
    </Modal>
  );
}
