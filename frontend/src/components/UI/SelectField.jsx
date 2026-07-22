import { Children, useId } from 'react';
import { ChevronDown } from 'lucide-react';
import Menu from './Menu';

// A select that keeps the native <select>'s public API — `value`, `onChange`
// (given an event whose target.value is the choice), `options` or <option>
// children, `label`, `hint`, `error`, `required`, `disabled` — but renders the
// app's own dropdown panel (see Menu) instead of the browser's. The native
// option list is drawn by the OS, in the OS font, with no way to style it; this
// gives every select the Kapot panel: our font, the amber-selected row, a check.
//
// Callers pass `onChange={(e) => ...(e.target.value)}`, so on pick we hand them a
// minimal synthetic event with that exact shape — no call site had to change.
function optionsFromChildren(children) {
  const out = [];
  Children.forEach(children, (child) => {
    if (!child || typeof child !== 'object') return;
    // Only <option> is supported as a child (no <optgroup> in use); flatten its
    // text so the trigger and list render plain labels.
    if (child.type === 'option') {
      out.push({ value: child.props.value ?? '', label: child.props.children });
    }
  });
  return out;
}

export default function SelectField({
  label,
  options,
  error,
  hint,
  required = false,
  disabled = false,
  value,
  onChange,
  id,
  className = '',
  containerClassName = '',
  children,
  ...rest
}) {
  const generatedId = useId();
  const selectId = id || generatedId;
  const messageId = error || hint ? `${selectId}-message` : undefined;

  const items = (options && options.length ? options : optionsFromChildren(children)).map((o) => ({
    value: String(o.value ?? ''),
    label: o.label,
    // An empty value is a placeholder ("— choose —"): show it muted, like one.
    placeholder: (o.value ?? '') === '',
  }));

  const current = items.find((it) => it.value === String(value ?? '')) || items[0];
  const isPlaceholder = current?.placeholder;

  const handleSelect = (v) => {
    // Mirror the native event shape the call sites read.
    onChange?.({ target: { value: v, id: selectId } });
  };

  return (
    <div
      className={`field ${error ? 'field-error' : ''} ${containerClassName}`}
      {...rest}
    >
      <Menu
        ariaLabel={typeof label === 'string' ? label : undefined}
        value={current?.value}
        onSelect={handleSelect}
        align="left"
        disabled={disabled}
        matchWidth
        items={items.map((it) => ({ value: it.value, label: it.label }))}
        buttonClassName={`field-input field-select flex w-full items-center text-left ${
          disabled ? 'cursor-not-allowed opacity-60' : ''
        } ${className}`}
        button={
          <span className={`min-w-0 truncate ${isPlaceholder ? 'text-mist' : ''}`}>
            {current?.label}
          </span>
        }
      />
      <span id={`${selectId}-label`} className="field-label is-static">
        {label}
        {required ? <span aria-hidden="true" className="text-crit"> *</span> : null}
      </span>
      <ChevronDown className="field-chevron" aria-hidden="true" />
      {error ? (
        <span id={messageId} className="field-message" role="alert">
          {error}
        </span>
      ) : hint ? (
        <span id={messageId} className="field-hint">
          {hint}
        </span>
      ) : null}
    </div>
  );
}
