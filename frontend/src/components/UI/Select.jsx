export default function Select({ label, options = [], className = '', id, ...props }) {
  const selectId = id || (label ? `select-${label.replace(/\s+/g, '-').toLowerCase()}` : undefined);
  return (
    <label className={`block ${className}`} htmlFor={selectId}>
      {label && <span className="mb-1.5 block text-sm text-slate-400">{label}</span>}
      <select
        id={selectId}
        className="w-full appearance-none rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-2.5 text-sm text-slate-100 outline-none transition-colors focus:border-blue-500"
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}
