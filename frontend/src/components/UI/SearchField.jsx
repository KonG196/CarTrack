import { forwardRef, useId } from 'react';
import { Search, X } from 'lucide-react';

const SearchField = forwardRef(function SearchField(
  { value, onChange, onClear, label = 'Пошук', placeholder = 'Пошук…', className = '', ...props },
  ref,
) {
  const id = useId();

  return (
    <div className={`relative ${className}`}>
      <Search
        className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-mist"
        aria-hidden="true"
      />
      <input
        id={id}
        ref={ref}
        type="search"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        aria-label={label}
        className="w-full rounded-xl border border-edge-soft bg-raised py-3 pl-10 pr-10 text-sm text-fg outline-none transition-colors placeholder:text-mist focus:border-amber"
        {...props}
      />
      {value ? (
        <button
          type="button"
          onClick={onClear}
          aria-label="Очистити пошук"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-mist transition-colors hover:bg-panel hover:text-fg"
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}
    </div>
  );
});

export default SearchField;
