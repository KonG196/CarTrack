/**
 * Pure helpers for the refuel form auto-math: editing any one of
 * (liters, price per liter, total cost) computes the dependent value
 * from the other two. Extracted verbatim from AddEntry.
 */

export const num = (v) => {
  const n = parseFloat(String(v).replace(',', '.'));
  return Number.isFinite(n) ? n : null;
};

/**
 * computeRefuelUpdate('liters', { liters: '40', pricePerLiter: '50', totalCost: '' })
 *   -> { totalCost: '2000.00' }
 *
 * `changed` is the field the user just edited; the values object holds the raw
 * input strings (decimal comma tolerated) AFTER the edit. Returns an object with
 * the single field to update, or null when nothing can be computed.
 *
 * Precedence mirrors the original form behavior (last-edited value wins):
 *  - edit liters:  liters+price -> total, else liters+total -> price
 *  - edit price:   price+liters -> total, else price+total  -> liters
 *  - edit total:   total+liters -> price, else total+price  -> liters
 * Zero/empty/invalid values never trigger a computation.
 */
export function computeRefuelUpdate(changed, { liters, pricePerLiter, totalCost }) {
  const l = num(liters);
  const p = num(pricePerLiter);
  const t = num(totalCost);

  if (changed === 'liters') {
    if (l && p) return { totalCost: (l * p).toFixed(2) };
    if (l && t) return { pricePerLiter: (t / l).toFixed(2) };
  }
  if (changed === 'pricePerLiter') {
    if (p && l) return { totalCost: (l * p).toFixed(2) };
    if (p && t) return { liters: (t / p).toFixed(2) };
  }
  if (changed === 'totalCost') {
    if (t && l) return { pricePerLiter: (t / l).toFixed(2) };
    if (t && p) return { liters: (t / p).toFixed(2) };
  }
  return null;
}
