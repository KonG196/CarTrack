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
  // Disables the trigger — the panel can't be opened.
  disabled = false,
  // Stretch the panel to the trigger's width instead of the default min-width.
  // Used when the menu stands in for a full-width form field.
  matchWidth = false,
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
    // While open, lift the whole trigger+popup above later siblings. The popup
    // is `absolute z-50`, but z-index only ranks within a stacking context — a
    // following card (Card has an opaque bg, no z) would otherwise paint over
    // the options. Raising the wrapper's z when mounted makes the popup win.
    <div ref={wrapRef} className={`relative min-w-0 ${mounted ? 'z-50' : ''}`}>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={mounted && !closing}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => (mounted && !closing ? requestClose() : setOpen(true))}
        className={buttonClassName}
      >
        {button}
      </button>

      {mounted && (
        <div
          data-closing={closing ? 'true' : undefined}
          style={{ backgroundColor: '#1B2636' }}
          className={`menu-pop absolute z-50 max-h-72 origin-top overflow-y-auto rounded-xl border border-edge-soft p-1 shadow-2xl shadow-black/70 ring-1 ring-black/50 ${
            // A field-width menu reads as one control with its trigger, so it
            // sits snug beneath it; the floating pill menu keeps a small gap.
            matchWidth ? 'mt-1 w-full' : 'mt-2 min-w-[12rem]'
          } ${align === 'right' ? 'right-0' : 'left-0'}`}
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
