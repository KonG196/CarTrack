export default function Toggle({ label, checked, onChange, className = '' }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`flex w-full items-center justify-between gap-3 rounded-xl border border-edge bg-raised px-3.5 py-3.5 text-left transition-colors hover:border-edge-soft ${className}`}
    >
      <span className="text-sm text-fg">{label}</span>
      <span
        className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors ${
          checked ? 'bg-amber' : 'bg-edge-soft'
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform motion-reduce:transition-none ${
            checked ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </span>
    </button>
  );
}
