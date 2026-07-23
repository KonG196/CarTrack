import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check } from 'lucide-react';
import Modal from './UI/Modal';
import { Button } from './UI';
import { CURRENCIES, DEFAULT_CURRENCY } from '../currency';
import { useCurrencyStore } from '../store/currencyStore';
import UnitToggle from './UnitToggle';

// First-run currency picker. Shown once, on the first authenticated visit that
// has no explicit currency choice yet — so a new account picks its symbol up
// front instead of hunting for it in Settings. Purely display: the choice only
// changes the symbol shown, never converts any amount.
export default function CurrencyPromptModal({ open, onClose }) {
  const { t } = useTranslation();
  const current = useCurrencyStore((s) => s.currency);
  const setCurrency = useCurrencyStore((s) => s.setCurrency);
  const [picked, setPicked] = useState(current || DEFAULT_CURRENCY);

  const confirm = () => {
    setCurrency(picked);
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      hideClose
      size="md"
      ariaLabel={t('currencyPrompt.title')}
      footer={
        <Button onClick={confirm} className="w-full">
          {t('currencyPrompt.confirm')}
        </Button>
      }
    >
      <div className="text-center">
        <h2 className="font-display text-lg font-semibold text-fg">{t('currencyPrompt.title')}</h2>
        <p className="mt-1.5 text-sm text-mist">{t('currencyPrompt.subtitle')}</p>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        {CURRENCIES.map((c) => {
          const selected = c.code === picked;
          return (
            <button
              key={c.code}
              type="button"
              onClick={() => setPicked(c.code)}
              aria-pressed={selected}
              className={`flex items-center gap-3 rounded-xl border p-3 text-left transition-colors ${
                selected
                  ? 'border-amber bg-amber/10'
                  : 'border-edge bg-raised/40 hover:border-edge-soft'
              }`}
            >
              <span
                className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg font-mono text-base tabular-nums ${
                  selected ? 'bg-amber/20 text-amber' : 'bg-raised text-fg'
                }`}
              >
                {c.symbol}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-mono text-sm tabular-nums text-fg">{c.code}</span>
                <span className="block truncate text-xs text-mist">{c.name}</span>
              </span>
              {selected && <Check className="h-4 w-4 flex-shrink-0 text-amber" />}
            </button>
          );
        })}
      </div>

      <div className="mt-4">
        <span className="text-xs text-mist">{t('currencyPrompt.unitsLabel')}</span>
        <UnitToggle className="mt-1.5" />
      </div>

      <p className="mt-3 text-center text-xs text-mist">{t('currencyPrompt.note')}</p>
    </Modal>
  );
}
