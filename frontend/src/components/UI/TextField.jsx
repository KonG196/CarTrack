import { forwardRef, useId } from 'react';

const TextField = forwardRef(function TextField(
  {
    label,
    error,
    hint,
    required = false,
    numeric = false,
    trailing,
    staticLabel = false,
    multiline = false,
    rows = 3,
    id,
    type = 'text',
    className = '',
    containerClassName = '',
    ...props
  },
  ref,
) {
  const generatedId = useId();
  const inputId = id || generatedId;
  const messageId = error || hint ? `${inputId}-message` : undefined;
  const labelPinned = staticLabel || type === 'date' || type === 'time';

  // A numeric field renders as type="text", not type="number": number inputs
  // can't be caret-managed (setSelectionRange throws) and browsers drop the
  // caret to position 0 mid-edit, which is the "курсор на початку набраного
  // числа" complaint. Every numeric caller already passes inputMode="numeric"
  // or "decimal", so the mobile keypad is unaffected. Non-digit input is
  // rejected by each caller's own parse/validation on save.
  const resolvedType = numeric && type === 'number' ? 'text' : type;

  const controlClassName = `field-input ${multiline ? 'field-textarea' : ''} ${
    numeric ? 'is-numeric' : ''
  } ${trailing ? 'has-trailing' : ''} ${className}`;

  return (
    <div className={`field ${error ? 'field-error' : ''} ${containerClassName}`}>
      {multiline ? (
        <textarea
          id={inputId}
          ref={ref}
          rows={rows}
          placeholder=" "
          aria-invalid={error ? true : undefined}
          aria-describedby={messageId}
          className={controlClassName}
          {...props}
        />
      ) : (
        <input
          id={inputId}
          ref={ref}
          type={resolvedType}
          placeholder=" "
          aria-invalid={error ? true : undefined}
          aria-describedby={messageId}
          className={controlClassName}
          {...props}
        />
      )}
      <label htmlFor={inputId} className={`field-label ${labelPinned ? 'is-static' : ''}`}>
        {label}
        {required ? <span aria-hidden="true" className="text-crit"> *</span> : null}
      </label>
      {trailing ? <span className="field-trailing">{trailing}</span> : null}
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
});

export default TextField;
