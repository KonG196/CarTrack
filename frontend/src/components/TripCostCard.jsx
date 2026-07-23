import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Minus, Plus, Route, Share2, Sparkles } from 'lucide-react';

import { buildTripShareText, computeTripCost, tripInputsFrom } from '../utils/tripCost';
import { formatMoney, distanceUnitLabel, volumeUnitLabel, consumptionUnitLabel } from '../utils/format';
import {
  isImperial,
  kmFromDistance,
  consumptionFromL100,
  KM_PER_MILE,
  LITRES_PER_US_GALLON,
} from '../units';
import { useUnitStore } from '../store/unitStore';
import { currentCurrencySymbol } from '../store/currencyStore';
import { Card, TextField } from './UI';

// mpg -> l/100km (the inverse of consumptionFromL100).
const l100FromMpg = (mpg) => (mpg > 0 ? 235.214583 / mpg : null);

export default function TripCostCard({ analytics, refuelContext, carName }) {
  const { t } = useTranslation();
  const units = useUnitStore((s) => s.units);
  const imperial = isImperial(units);
  // Fields are entered in the user's display units; the calculator works in
  // metric, so convert on the way into computeTripCost and on the way out of
  // the history prefills.
  const distToKm = (d) => (imperial ? Number(d) * KM_PER_MILE : Number(d));
  const consToL100 = (c) => (imperial ? l100FromMpg(Number(c)) : Number(c));
  const priceToPerL = (p) => (imperial ? Number(p) / LITRES_PER_US_GALLON : Number(p));
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
      const shown = imperial ? consumptionFromL100(known.consumption, units) : known.consumption;
      return shown == null ? current : String(+shown.toFixed(1));
    });
    setPrice((current) => {
      if (current || !known.pricePerLiter) return current;
      setAuto((a) => ({ ...a, price: true }));
      const shown = imperial ? known.pricePerLiter * LITRES_PER_US_GALLON : known.pricePerLiter;
      return String(+shown.toFixed(2));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [known.consumption, known.pricePerLiter]);

  const result = computeTripCost({
    distanceKm: distToKm(distance),
    consumption: consToL100(Number(String(consumption).replace(',', '.'))) || null,
    pricePerLiter: priceToPerL(Number(String(price).replace(',', '.'))) || null,
    people,
  });

  const [shared, setShared] = useState(false);
  const handleShare = async () => {
    const text = buildTripShareText({
      carName,
      distanceKm: distance,
      consumption,
      pricePerLiter: price,
      result,
    });
    if (!text) return;
    try {
      if (navigator.share) {
        await navigator.share({ text });
      } else {
        await navigator.clipboard.writeText(text);
        setShared(true);
        setTimeout(() => setShared(false), 1800);
      }
    } catch {
      /* the user dismissed the share sheet — nothing to do */
    }
  };

  const autoClass = 'border-ok/60 text-ok';

  return (
    <Card>
      <div className="mb-3 flex items-center gap-2">
        <Route className="h-5 w-5 text-amber" />
        <h2 className="font-display text-base font-semibold text-fg">{t('tripCostCard.title')}</h2>
      </div>

      {(auto.consumption || auto.price) && (
        <p className="mb-3 flex items-center gap-1.5 text-xs text-ok">
          <Sparkles className="h-3.5 w-3.5" />
          {t('tripCostCard.filledFromHistory')}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <TextField
          label={t('tripCostCard.distanceLabel', { unit: distanceUnitLabel() })}
          inputMode="decimal"
          numeric
          value={distance}
          onChange={(e) => setDistance(e.target.value)}
        />
        <div className="flex items-end justify-end gap-1.5 pb-1">
          <button
            type="button"
            aria-label={t('tripCostCard.fewerPeople')}
            onClick={() => setPeople((n) => Math.max(1, n - 1))}
            className="rounded-lg border border-edge p-2 text-mist transition-colors hover:text-fg"
          >
            <Minus className="h-3.5 w-3.5" />
          </button>
          <span className="w-12 text-center text-sm text-fg">
            {people} <span className="text-mist">{t('tripCostCard.peopleUnit')}</span>
          </span>
          <button
            type="button"
            aria-label={t('tripCostCard.morePeople')}
            onClick={() => setPeople((n) => n + 1)}
            className="rounded-lg border border-edge p-2 text-mist transition-colors hover:text-fg"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <TextField
          label={t('tripCostCard.consumptionLabel', { unit: consumptionUnitLabel() })}
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
          label={t('tripCostCard.pricePerLiterLabel', {
            unit: volumeUnitLabel(),
            currency: currentCurrencySymbol(),
          })}
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
            <span className="text-sm text-mist">{t('tripCostCard.oneWay', { liters: result.liters })}</span>
            <span className="font-display text-lg font-semibold text-fg">
              {formatMoney(result.cost)}
            </span>
          </div>
          <div className="flex items-baseline justify-between border-t border-edge pt-2">
            <span className="text-sm text-mist">{t('tripCostCard.roundTrip')}</span>
            <span className="text-sm text-fg">{formatMoney(result.roundTripCost)}</span>
          </div>
          {result.people > 1 && (
            <div className="flex items-baseline justify-between border-t border-edge pt-2">
              <span className="text-sm text-mist">{t('tripCostCard.perPersonRoundTrip')}</span>
              <span className="font-display text-base font-semibold text-amber">
                {formatMoney(result.roundTripPerPerson)}
              </span>
            </div>
          )}
          <button
            type="button"
            onClick={handleShare}
            className="mt-1 flex w-full items-center justify-center gap-2 rounded-xl border border-edge bg-panel py-2.5 text-sm font-semibold text-fg transition active:scale-[0.98] hover:border-edge-soft motion-reduce:active:scale-100"
          >
            {shared ? (
              <>
                <Check className="h-4 w-4 text-ok" />
                {t('tripCostCard.copied')}
              </>
            ) : (
              <>
                <Share2 className="h-4 w-4 text-amber" />
                {t('tripCostCard.share')}
              </>
            )}
          </button>
        </div>
      ) : (
        <p className="mt-3 text-xs text-mist">
          {t('tripCostCard.emptyHint')}
        </p>
      )}
    </Card>
  );
}
