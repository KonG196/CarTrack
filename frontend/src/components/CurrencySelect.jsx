import { ChevronDown } from 'lucide-react';
import Menu from './UI/Menu';
import { CURRENCIES, currencyInfo } from '../currency';
import { useCurrencyStore } from '../store/currencyStore';

// Display-currency picker. Changing it is instant (the whole tree re-renders via
// the currency store subscribed in App); the choice is persisted and mirrored to
// the backend so the report PDF, bot and notifications use the same symbol.
//
// Built on the app's own Menu listbox rather than a native <select>: a browser
// draws the native option list itself, in the OS font with no way to style it,
// which clashed with the rest of the UI. Menu gives us the Kapot panel — our
// font, the amber-highlighted selected row, mono symbols and codes.
export default function CurrencySelect({ label, className = '' }) {
  const currency = useCurrencyStore((s) => s.currency);
  const setCurrency = useCurrencyStore((s) => s.setCurrency);
  const active = currencyInfo(currency);

  return (
    <div className={`field ${className}`}>
      <Menu
        ariaLabel={label}
        value={currency}
        onSelect={setCurrency}
        align="left"
        matchWidth
        items={CURRENCIES.map((c) => ({
          value: c.code,
          label: (
            <span className="flex min-w-0 items-baseline gap-2.5">
              <span className="w-6 flex-shrink-0 font-mono tabular-nums">{c.symbol}</span>
              <span className="font-mono tabular-nums">{c.code}</span>
              <span className="truncate text-mist">— {c.name}</span>
            </span>
          ),
        }))}
        buttonClassName="field-input field-select flex w-full items-center text-left"
        button={
          <span className="flex min-w-0 items-baseline gap-2.5">
            <span className="w-6 flex-shrink-0 font-mono tabular-nums">{active.symbol}</span>
            <span className="font-mono tabular-nums">{active.code}</span>
            <span className="truncate text-mist">— {active.name}</span>
          </span>
        }
      />
      <span className="field-label is-static">{label}</span>
      <ChevronDown className="field-chevron" aria-hidden="true" />
    </div>
  );
}
