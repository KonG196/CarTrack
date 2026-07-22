import { SelectField } from './UI';
import { CURRENCIES } from '../currency';
import { useCurrencyStore } from '../store/currencyStore';

// Display-currency picker. Changing it is instant (the whole tree re-renders via
// the currency store subscribed in App); the choice is persisted and mirrored to
// the backend so the report PDF, bot and notifications use the same symbol.
export default function CurrencySelect({ label, className = '' }) {
  const currency = useCurrencyStore((s) => s.currency);
  const setCurrency = useCurrencyStore((s) => s.setCurrency);

  return (
    <SelectField
      label={label}
      value={currency}
      onChange={(e) => setCurrency(e.target.value)}
      options={CURRENCIES.map((c) => ({
        value: c.code,
        label: `${c.symbol}  ${c.code} — ${c.name}`,
      }))}
      className={className}
    />
  );
}
