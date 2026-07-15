import { useMemo, useState } from 'react';
import { Minus, Plus, Route } from 'lucide-react';

import { computeTripCost, tripInputsFrom } from '../utils/tripCost';
import { formatMoney } from '../utils/format';
import { Card, TextField } from './UI';

export default function TripCostCard({ analytics, refuelContext }) {
  const [distance, setDistance] = useState('');
  const [people, setPeople] = useState(1);

  const { consumption, pricePerLiter } = useMemo(
    () => tripInputsFrom(analytics, refuelContext),
    [analytics, refuelContext],
  );

  // Without a measured consumption there is nothing to count with, and a
  // brochure figure would be a different car's number.
  if (!consumption || !pricePerLiter) return null;

  const result = computeTripCost({ distanceKm: distance, consumption, pricePerLiter, people });

  return (
    <Card>
      <div className="mb-3 flex items-center gap-2">
        <Route className="h-5 w-5 text-amber" />
        <h2 className="font-display text-base font-semibold text-fg">Скільки коштує поїздка</h2>
      </div>
      <p className="mb-3 text-sm text-mist">
        За вашими цифрами: {consumption} л/100 км · {formatMoney(pricePerLiter)}/л
      </p>

      <div className="flex items-end gap-3">
        <TextField
          label="Відстань, км"
          inputMode="decimal"
          numeric
          value={distance}
          onChange={(e) => setDistance(e.target.value)}
          containerClassName="flex-1"
        />
        <div className="mb-1 flex items-center gap-1.5">
          <button
            type="button"
            aria-label="Менше людей"
            onClick={() => setPeople((n) => Math.max(1, n - 1))}
            className="rounded-lg border border-edge p-2 text-mist transition-colors hover:text-fg"
          >
            <Minus className="h-3.5 w-3.5" />
          </button>
          <span className="w-10 text-center text-sm text-fg">
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

      {result && (
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
      )}
    </Card>
  );
}
