import Modal from './Modal';
import Button from './Button';

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Видалити',
  danger = true,
  onConfirm,
  onCancel,
}) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm} className="flex-1">
            {confirmLabel}
          </Button>
          <Button variant="secondary" onClick={onCancel} className="flex-1">
            Скасувати
          </Button>
        </>
      }
    >
      <p className="text-sm text-mist">{message}</p>
    </Modal>
  );
}
