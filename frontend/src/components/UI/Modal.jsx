import { useCallback, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import useAnimatedPresence from '../../hooks/useAnimatedPresence';

const CLOSE_MS = 200;

const SIZES = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
};

export default function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  size = 'md',
  hideClose = false,
  ariaLabel,
  bodyClassName = '',
}) {
  const backdropRef = useRef(null);
  const pressedBackdrop = useRef(false);
  const { mounted, closing, requestClose } = useAnimatedPresence(open, onClose, CLOSE_MS);

  useEffect(() => {
    if (!mounted) return undefined;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') requestClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [mounted, requestClose]);

  useEffect(() => {
    if (!mounted) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [mounted]);

  const onBackdropMouseUp = useCallback(
    (e) => {
      if (pressedBackdrop.current && e.target === backdropRef.current) requestClose();
      pressedBackdrop.current = false;
    },
    [requestClose],
  );

  if (!mounted) return null;

  const titleId = title ? 'modal-title' : undefined;

  return createPortal(
    <div
      ref={backdropRef}
      className="modal-backdrop"
      data-closing={closing ? 'true' : undefined}
      onMouseDown={(e) => {
        pressedBackdrop.current = e.target === backdropRef.current;
      }}
      onMouseUp={onBackdropMouseUp}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-label={title ? undefined : ariaLabel}
        className={`modal-dialog ${SIZES[size] || SIZES.md}`}
      >
        {(title || !hideClose) && (
          <header className="flex flex-shrink-0 items-center justify-between gap-3 border-b border-edge px-4 py-3">
            {title ? (
              <h2 id={titleId} className="font-display text-sm font-semibold text-fg">
                {title}
              </h2>
            ) : (
              <span />
            )}
            {!hideClose && (
              <button
                type="button"
                onClick={requestClose}
                aria-label="Закрити"
                className="-mr-1 rounded-lg p-1.5 text-mist transition-colors hover:bg-raised hover:text-fg"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </header>
        )}

        <div className={`min-h-0 flex-1 overflow-y-auto p-4 ${bodyClassName}`}>{children}</div>

        {footer && (
          <footer className="flex flex-shrink-0 gap-2 border-t border-edge p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body,
  );
}
