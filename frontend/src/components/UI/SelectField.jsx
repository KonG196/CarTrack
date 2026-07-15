import { forwardRef, useId } from 'react';
import { ChevronDown } from 'lucide-react';

const SelectField = forwardRef(function SelectField(
  {
    label,
    options = [],
    error,
    hint,
    required = false,
    id,
    className = '',
    containerClassName = '',
    children,
    ...props
  },
  ref,
) {
  const generatedId = useId();
  const selectId = id || generatedId;
  const messageId = error || hint ? `${selectId}-message` : undefined;

  return (
    <div className={`field ${error ? 'field-error' : ''} ${containerClassName}`}>
      <select
        id={selectId}
        ref={ref}
        aria-invalid={error ? true : undefined}
        aria-describedby={messageId}
        className={`field-input field-select ${className}`}
        {...props}
      >
        {children ||
          options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
      </select>
      <label htmlFor={selectId} className="field-label is-static">
        {label}
        {required ? <span aria-hidden="true" className="text-crit"> *</span> : null}
      </label>
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
});

export default SelectField;
