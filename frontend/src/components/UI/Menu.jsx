import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
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
  // Extra classes for the dropdown panel (e.g. a wider min-width).
  panelClassName = '',
  // An action to offer under the choices — «add one» belongs next to the list
  // of what there is. It renders outside the listbox on purpose: a screen
  // reader is told these options are values one of which is selected, and an
  // action is neither.
  footer,
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const triggerRef = useRef(null);
  const popRef = useRef(null);
  const close = useCallback(() => setOpen(false), []);
  const { mounted, closing, requestClose } = useAnimatedPresence(open, close, CLOSE_MS);

  // The panel renders in a portal at <body>, so no ancestor's stacking context
  // or overflow can clip or cover it (a following opaque card used to paint over
  // the options). Because it's detached from the trigger, we position it by the
  // trigger's on-screen box, recomputed on open / scroll / resize.
  const [rect, setRect] = useState(null);
  const measure = useCallback(() => {
    const el = triggerRef.current;
    if (el) setRect(el.getBoundingClientRect());
  }, []);

  useLayoutEffect(() => {
    if (!mounted) return undefined;
    measure();
    window.addEventListener('scroll', measure, true); // capture: catch scrolls in any ancestor
    window.addEventListener('resize', measure);
    return () => {
      window.removeEventListener('scroll', measure, true);
      window.removeEventListener('resize', measure);
    };
  }, [mounted, measure]);

  useEffect(() => {
    if (!mounted) return undefined;

    const onPointerDown = (e) => {
      // The panel now lives outside wrapRef (portal), so check both.
      if (wrapRef.current?.contains(e.target) || popRef.current?.contains(e.target)) return;
      requestClose();
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

  const panelStyle = rect
    ? {
        position: 'fixed',
        top: rect.bottom + (matchWidth ? 4 : 8),
        // matchWidth pins both edges to the trigger; otherwise anchor to the
        // requested side and let the panel size to its content.
        ...(matchWidth
          ? { left: rect.left, width: rect.width }
          : align === 'right'
            ? { right: window.innerWidth - rect.right }
            : { left: rect.left }),
        backgroundColor: '#1B2636',
      }
    : { position: 'fixed', top: -9999, left: -9999, backgroundColor: '#1B2636' };

  return (
    <div ref={wrapRef} className="relative min-w-0">
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

      {mounted &&
        createPortal(
          <div
            ref={popRef}
            data-closing={closing ? 'true' : undefined}
            style={panelStyle}
            className={`menu-pop z-[1000] max-h-72 origin-top overflow-y-auto overscroll-contain rounded-xl border border-edge-soft p-1 shadow-2xl shadow-black/70 ring-1 ring-black/50 ${
              matchWidth ? '' : 'min-w-[12rem]'
            } ${panelClassName}`}
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
          </div>,
          document.body,
        )}
    </div>
  );
}
