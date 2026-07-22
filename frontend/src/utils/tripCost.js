// «Скільки скидаємось на солярку?» answered from this car's own numbers: the
// consumption it actually shows and the price actually paid last time — not a
// brochure figure and not today's average at the pumps.

import i18n from '../i18n';

export function computeTripCost({ distanceKm, consumption, pricePerLiter, people = 1 }) {
  const distance = Number(String(distanceKm).replace(',', '.'));
  if (!Number.isFinite(distance) || distance <= 0) return null;
  if (!consumption || !pricePerLiter) return null;

  const liters = (distance * consumption) / 100;
  const cost = liters * pricePerLiter;
  const heads = Math.max(1, Math.floor(Number(people) || 1));

  return {
    liters: Math.round(liters * 100) / 100,
    cost: Math.round(cost * 100) / 100,
    people: heads,
    perPerson: Math.round((cost / heads) * 100) / 100,
    // Round trips are the common case for a weekend drive, and doubling in the
    // head is exactly the arithmetic this exists to remove.
    roundTripCost: Math.round(cost * 2 * 100) / 100,
    roundTripPerPerson: Math.round(((cost * 2) / heads) * 100) / 100,
  };
}

function tidy(value) {
  const n = Number(String(value).replace(',', '.'));
  if (!Number.isFinite(n)) return String(value ?? '');
  return Number.isInteger(n) ? String(n) : String(Math.round(n * 100) / 100);
}

// A one-line summary for navigator.share / clipboard — the number the driver
// wants to send to the group chat, in plain words.
export function buildTripShareText({ carName, distanceKm, consumption, pricePerLiter, result }) {
  if (!result) return '';
  const on = carName ? i18n.t('tripCostUtil.onCar', { name: carName }) : '';
  const parts = [
    i18n.t('tripCostUtil.tripLine', {
      on,
      distance: tidy(distanceKm),
      consumption: tidy(consumption),
      price: tidy(pricePerLiter),
    }),
    i18n.t('tripCostUtil.total', { amount: tidy(Math.round(result.cost)) }),
  ];
  if (result.people > 1) {
    parts.push(
      i18n.t('tripCostUtil.perPerson', {
        people: result.people,
        amount: tidy(Math.round(result.perPerson)),
      }),
    );
  }
  return parts.join(' ');
}

// Both numbers are prefills, not requirements: the card works on typed values
// alone, and history only saves the typing when it has something to say.
// Consumption exists once two full tanks are logged; the price is simply the
// last one paid, which needs no measurement at all.
export function tripInputsFrom(analytics, refuelContext) {
  const consumption = analytics?.fuel?.avg_consumption_l_100km ?? null;
  const history = analytics?.price_history ?? [];
  const lastPriced = history.length ? history[history.length - 1] : null;
  const price =
    refuelContext?.last_price_per_liter ?? lastPriced?.price_per_liter ?? null;
  return { consumption, pricePerLiter: price };
}
