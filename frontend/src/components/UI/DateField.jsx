import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import useAnimatedPresence from '../../hooks/useAnimatedPresence';

const CLOSE_MS = 150;

// Parsed and formatted by hand, never through `new Date('2026-07-16')`: that
// reads the string as UTC midnight and can land on the day before in a western
// timezone. Local components in, local components out.
function parseISO(value) {
  if (typeof value !== 'string') return null;
  const [y, m, d] = value.split('-').map(Number);
  if (!y || !m || !d) return null;
  const date = new Date(y, m - 1, d);
  return Number.isNaN(date.getTime()) ? null : date;
}

function toISO(date) {
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${m}-${d}`;
}

function sameDay(a, b) {
  return (
    a && b &&
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function displayValue(date) {
  if (!date) return '';
  const d = String(date.getDate()).padStart(2, '0');
  const m = String(date.getMonth() + 1).padStart(2, '0');
  return `${d}.${m}.${date.getFullYear()}`;
}

export default function DateField({
  label,
  value,
  onChange,
  required = false,
  clearable = false,
  hint,
  containerClassName = '',
}) {
  const { t } = useTranslation();
  // Monday first, as a Ukrainian calendar prints it — not the browser's Sunday.
  const WEEKDAYS = t('uiDateField.weekdays', { returnObjects: true });
  const MONTHS = t('uiDateField.months', { returnObjects: true });
  const fieldId = useId();
  const selected = parseISO(value);
  const [open, setOpen] = useState(false);
  const [view, setView] = useState(() => selected || new Date());
  const wrapRef = useRef(null);
  const triggerRef = useRef(null);
  const close = useCallback(() => setOpen(false), []);
  const { mounted, closing, requestClose } = useAnimatedPresence(open, close, CLOSE_MS);

  // Reopen on the month of the current value, so editing a date does not start
  // the user in whatever month they last browsed to.
  useEffect(() => {
    if (open && selected) setView(selected);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

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

  const cells = useMemo(() => {
    const year = view.getFullYear();
    const month = view.getMonth();
    // Monday-based offset: JS getDay() is Sunday=0, so shift.
    const leading = (new Date(year, month, 1).getDay() + 6) % 7;
    const days = new Date(year, month + 1, 0).getDate();
    const out = [];
    for (let i = 0; i < leading; i += 1) out.push(null);
    for (let d = 1; d <= days; d += 1) out.push(new Date(year, month, d));
    return out;
  }, [view]);

  const pick = (date) => {
    onChange?.(toISO(date));
    requestClose();
    triggerRef.current?.focus();
  };

  const shiftMonth = (delta) =>
    setView((v) => new Date(v.getFullYear(), v.getMonth() + delta, 1));

  const today = new Date();

  return (
    <div ref={wrapRef} className={`field ${containerClassName}`}>
      <button
        ref={triggerRef}
        type="button"
        id={fieldId}
        aria-haspopup="dialog"
        aria-expanded={mounted && !closing}
        onClick={() => (mounted && !closing ? requestClose() : setOpen(true))}
        className="field-input flex items-center justify-between text-left"
      >
        <span className={selected ? 'text-fg' : 'text-mist'}>
          {selected ? displayValue(selected) : t('uiDateField.placeholder')}
        </span>
        <CalendarDays className="h-4 w-4 flex-shrink-0 text-mist" aria-hidden="true" />
      </button>
      <label htmlFor={fieldId} className="field-label is-static">
        {label}
        {required ? <span aria-hidden="true" className="text-crit"> *</span> : null}
      </label>
      {hint ? <span className="field-hint">{hint}</span> : null}

      {mounted && (
        <div
          role="dialog"
          aria-label={label}
          data-closing={closing ? 'true' : undefined}
          className="menu-pop absolute left-0 top-full z-50 mt-2 w-72 origin-top rounded-xl border border-edge bg-panel p-3 shadow-xl shadow-black/50"
        >
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              onClick={() => shiftMonth(-1)}
              aria-label={t('uiDateField.prevMonth')}
              className="rounded-lg p-1.5 text-mist transition-colors hover:bg-raised hover:text-fg"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-sm font-semibold text-fg">
              {MONTHS[view.getMonth()]} {view.getFullYear()}
            </span>
            <button
              type="button"
              onClick={() => shiftMonth(1)}
              aria-label={t('uiDateField.nextMonth')}
              className="rounded-lg p-1.5 text-mist transition-colors hover:bg-raised hover:text-fg"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-7 gap-0.5">
            {WEEKDAYS.map((w) => (
              <div key={w} className="py-1 text-center text-[10px] font-medium text-mist">
                {w}
              </div>
            ))}
            {cells.map((date, i) =>
              date === null ? (
                <div key={`b${i}`} />
              ) : (
                <button
                  key={toISO(date)}
                  type="button"
                  onClick={() => pick(date)}
                  className={`flex h-8 items-center justify-center rounded-lg text-sm tabular-nums transition-colors ${
                    sameDay(date, selected)
                      ? 'bg-amber font-semibold text-amber-ink'
                      : sameDay(date, today)
                        ? 'text-amber hover:bg-raised'
                        : 'text-fg hover:bg-raised'
                  }`}
                >
                  {date.getDate()}
                </button>
              ),
            )}
          </div>

          <div className="mt-2 flex items-center justify-between border-t border-edge pt-2">
            <button
              type="button"
              onClick={() => pick(new Date())}
              className="rounded-lg px-2 py-1 text-xs font-medium text-amber transition-colors hover:bg-raised"
            >
              {t('uiDateField.today')}
            </button>
            {clearable && (
              <button
                type="button"
                onClick={() => {
                  onChange?.('');
                  requestClose();
                }}
                className="rounded-lg px-2 py-1 text-xs text-mist transition-colors hover:bg-raised hover:text-fg"
              >
                {t('uiDateField.clear')}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
