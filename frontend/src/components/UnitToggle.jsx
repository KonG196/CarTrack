import { useTranslation } from 'react-i18next';
import { UNIT_SYSTEMS } from '../units';
import { useUnitStore } from '../store/unitStore';

// Metric / Imperial switcher. Changing it is instant (the store is subscribed
// at the App root); the choice is persisted to localStorage and mirrored to the
// backend so the report PDF and Telegram digest use the same units.
export default function UnitToggle({ className = '' }) {
  const { t } = useTranslation();
  const units = useUnitStore((s) => s.units);
  const setUnits = useUnitStore((s) => s.setUnits);

  return (
    <div role="group" aria-label={t('units.label')} className={`flex gap-2 ${className}`}>
      {UNIT_SYSTEMS.map((u) => {
        const active = u.code === units;
        return (
          <button
            key={u.code}
            type="button"
            onClick={() => setUnits(u.code)}
            aria-pressed={active}
            className={`flex-1 rounded-xl border px-3 py-2 text-sm transition-colors ${
              active ? 'border-amber bg-amber/10 text-amber' : 'border-edge text-mist hover:text-fg'
            }`}
          >
            <span className="block">{t(`units.${u.code}`)}</span>
            <span className="mt-0.5 block text-[11px] text-mist">
              {u.distance} · {u.volume} · {u.consumption}
            </span>
          </button>
        );
      })}
    </div>
  );
}
