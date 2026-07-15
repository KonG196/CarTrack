import { useEffect, useMemo, useState } from 'react';
import { Minus, Plus, Route, Sparkles } from 'lucide-react';

import { computeTripCost, tripInputsFrom } from '../utils/tripCost';
import { formatMoney } from '../utils/format';
import { Card, TextField } from './UI';

export default function TripCostCard({ analytics, refuelContext }) {
  const [distance, setDistance] = useState('');
  const [people, setPeople] = useState(1);
  const [consumption, setConsumption] = useState('');
  const [price, setPrice] = useState('');
  // What the car's own history filled in. Cleared per field the moment the
  // user types over it: the green mark promises the number came from their
  // data, so it must stop claiming that the instant it did not.
  const [auto, setAuto] = useState({ consumption: false, price: false });

  const known = useMemo(
    () => tripInputsFrom(analytics, refuelContext),
    [analytics, refuelContext],
  );

  useEffect(() => {
    // Only fills empty fields: a number the user typed outranks history.
    setConsumption((current) => {
      if (current || !known.consumption) return current;
      setAuto((a) => ({ ...a, consumption: true }));
      return String(known.consumption);
    });
    setPrice((current) => {
      if (current || !known.pricePerLiter) return current;
      setAuto((a) => ({ ...a, price: true }));
      return String(known.pricePerLiter);
    });
  }, [known.consumption, known.pricePerLiter]);

  const result = computeTripCost({
    distanceKm: distance,
    consumption: Number(String(consumption).replace(',', '.')) || null,
    pricePerLiter: Number(String(price).replace(',', '.')) || null,
    people,
  });

  const autoClass = 'border-ok/60 text-ok';

  return (
    <Card>
      <div className="mb-3 flex items-center gap-2">
        <Route className="h-5 w-5 text-amber" />
        <h2 className="font-display text-base font-semibold text-fg">Скільки коштує поїздка</h2>
      </div>

      {(auto.consumption || auto.price) && (
        <p className="mb-3 flex items-center gap-1.5 text-xs text-ok">
          <Sparkles className="h-3.5 w-3.5" />
          Заповнено з вашої історії — можна змінити
        </p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <TextField
          label="Відстань, км"
          inputMode="decimal"
          numeric
          value={distance}
          onChange={(e) => setDistance(e.target.value)}
        />
        <div className="flex items-end justify-end gap-1.5 pb-1">
          <button
            type="button"
            aria-label="Менше людей"
            onClick={() => setPeople((n) => Math.max(1, n - 1))}
            className="rounded-lg border border-edge p-2 text-mist transition-colors hover:text-fg"
          >
            <Minus className="h-3.5 w-3.5" />
          </button>
          <span className="w-12 text-center text-sm text-fg">
            {people} <span className="text-mist">ос.</span>
          </span>
          <button
            type="button"
            aria-label="Більше людей"
            onClick={() => setPeople((n) => n + 1)}
            className="rounded-lg border border-edge p-2 text-mist transition-colors hover:text-fg"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <TextField
          label="Розхід, л/100 км"
          inputMode="decimal"
          numeric
          value={consumption}
          className={auto.consumption ? autoClass : ''}
          onChange={(e) => {
            setConsumption(e.target.value);
            setAuto((a) => ({ ...a, consumption: false }));
          }}
        />
        <TextField
          label="Ціна за літр, ₴"
          inputMode="decimal"
          numeric
          value={price}
          className={auto.price ? autoClass : ''}
          onChange={(e) => {
            setPrice(e.target.value);
            setAuto((a) => ({ ...a, price: false }));
          }}
        />
      </div>

      {result ? (
        <div className="mt-3 space-y-2 rounded-xl bg-garage/60 px-3.5 py-3">
          <div className="flex items-baseline justify-between">
            <span className="text-sm text-mist">В один бік · {result.liters} л</span>
            <span className="font-display text-lg font-semibold text-fg">
              {formatMoney(result.cost)}
            </span>
          </div>
          <div className="flex items-baseline justify-between border-t border-edge pt-2">
            <span className="text-sm text-mist">Туди й назад</span>
            <span className="text-sm text-fg">{formatMoney(result.roundTripCost)}</span>
          </div>
          {result.people > 1 && (
            <div className="flex items-baseline justify-between border-t border-edge pt-2">
              <span className="text-sm text-mist">З кожного (туди й назад)</span>
              <span className="font-display text-base font-semibold text-amber">
                {formatMoney(result.roundTripPerPerson)}
              </span>
            </div>
          )}
        </div>
      ) : (
        <p className="mt-3 text-xs text-mist">
          Вкажіть відстань, розхід і ціну — порахую вартість і скільки з кожного.
        </p>
      )}
    </Card>
  );
}
