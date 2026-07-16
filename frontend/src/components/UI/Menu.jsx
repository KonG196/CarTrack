import { useCallback, useEffect, useRef, useState } from 'react';
import { Check } from 'lucide-react';
import useAnimatedPresence from '../../hooks/useAnimatedPresence';

const CLOSE_MS = 150;

export default function Menu({
  button,
  items = [],
  value,
  onSelect,
  align = 'right',
  ariaLabel,
  buttonClassName = '',
  // An action to offer under the choices — «add one» belongs next to the list
  // of what there is. It renders outside the listbox on purpose: a screen
  // reader is told these options are values one of which is selected, and an
  // action is neither.
  footer,
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const triggerRef = useRef(null);
  const close = useCallback(() => setOpen(false), []);
  const { mounted, closing, requestClose } = useAnimatedPresence(open, close, CLOSE_MS);

  useEffect(() => {
    if (!mounted) return undefined;

    const onPointerDown = (e) => {
      if (!wrapRef.current?.contains(e.target)) requestClose();
    };
    const onKeyDown = (e) => {
      if (e.key !== 'Escape') return;
      requestClose();
      triggerRef.current?.focus();
    };

    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [mounted, requestClose]);

  return (
    <div ref={wrapRef} className="relative min-w-0">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={mounted && !closing}
        aria-label={ariaLabel}
        onClick={() => (mounted && !closing ? requestClose() : setOpen(true))}
        className={buttonClassName}
      >
        {button}
      </button>

      {mounted && (
        <div
          data-closing={closing ? 'true' : undefined}
          className={`menu-pop absolute z-50 mt-2 max-h-72 min-w-[12rem] origin-top overflow-y-auto rounded-xl border border-edge bg-panel p-1 shadow-xl shadow-black/50 ${
            align === 'right' ? 'right-0' : 'left-0'
          }`}
        >
          <div role="listbox" aria-label={ariaLabel}>
            {items.map((item) => {
              const selected = item.value === value;
              return (
                <button
                  key={item.value}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => {
                    onSelect?.(item.value);
                    requestClose();
                  }}
                  className={`flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                    selected ? 'bg-raised text-amber' : 'text-fg hover:bg-raised'
                  }`}
                >
                  <span className="truncate">{item.label}</span>
                  {selected && <Check className="h-4 w-4 flex-shrink-0" />}
                </button>
              );
            })}
          </div>

          {footer && (
            // Closes on any click inside: the footer navigates within this same
            // layout, so nothing else would ever dismiss the menu.
            <div onClick={requestClose} className="mt-1 border-t border-edge pt-1">
              {footer}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
