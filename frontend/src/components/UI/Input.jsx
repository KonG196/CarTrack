export default function Input({ label, hint, className = '', id, ...props }) {
  const inputId = id || (label ? `input-${label.replace(/\s+/g, '-').toLowerCase()}` : undefined);
  return (
    <label className={`block ${className}`} htmlFor={inputId}>
      {label && <span className="mb-1.5 block text-sm text-slate-400">{label}</span>}
      <input
        id={inputId}
        className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none transition-colors focus:border-blue-500"
        {...props}
      />
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}
