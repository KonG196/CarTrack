import { useTranslation } from 'react-i18next';
import Modal from './Modal';
import Button from './Button';

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  danger = true,
  onConfirm,
  onCancel,
}) {
  const { t } = useTranslation();
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm} className="flex-1">
            {confirmLabel || t('common.delete')}
          </Button>
          <Button variant="secondary" onClick={onCancel} className="flex-1">
            {t('common.cancel')}
          </Button>
        </>
      }
    >
      <p className="text-sm text-mist">{message}</p>
    </Modal>
  );
}
