// «Скільки скидаємось на солярку?» answered from this car's own numbers: the
// consumption it actually shows and the price actually paid last time — not a
// brochure figure and not today's average at the pumps.

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

export function tripInputsFrom(analytics, refuelContext) {
  // Consumption comes from full-to-full segments, so it exists only once the
  // car has two full tanks logged. Without it there is nothing honest to show.
  const consumption = analytics?.fuel?.avg_consumption_l_100km ?? null;
  const price =
    refuelContext?.last_price_per_liter ??
    analytics?.fuel?.last_price_per_liter ??
    null;
  return { consumption, pricePerLiter: price };
}
