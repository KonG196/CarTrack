export const num = (v) => {
  const n = parseFloat(String(v).replace(',', '.'));
  return Number.isFinite(n) ? n : null;
};

const FIELDS = ['liters', 'pricePerLiter', 'totalCost'];

// Fill in the ONE field the user never entered, from the two they did — and
// only that field. A value the user typed themselves (or is typing right now)
// is never touched; if the user has filled all three, nothing is computed.
//
// `owned` = the fields the user provided (typed or accepted from a scan). The
// single field NOT in `owned` is the app's to compute; it needs both owned
// values to be positive numbers. Returns a one-key patch (string) or null.
export function deriveRefuel({ liters, pricePerLiter, totalCost }, owned = []) {
  const free = FIELDS.filter((k) => !owned.includes(k));
  if (free.length !== 1) return null; // need exactly two owned inputs, one gap
  const target = free[0];

  const v = {
    liters: num(liters),
    pricePerLiter: num(pricePerLiter),
    totalCost: num(totalCost),
  };
  const inputs = FIELDS.filter((k) => k !== target);
  if (!inputs.every((k) => v[k] != null && v[k] > 0)) return null;

  const { liters: l, pricePerLiter: p, totalCost: t } = v;
  if (target === 'liters') return { liters: (t / p).toFixed(2) };
  if (target === 'pricePerLiter') return { pricePerLiter: (t / l).toFixed(2) };
  return { totalCost: (l * p).toFixed(2) };
}
