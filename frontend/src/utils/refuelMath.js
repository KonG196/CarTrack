export const num = (v) => {
  const n = parseFloat(String(v).replace(',', '.'));
  return Number.isFinite(n) ? n : null;
};

// The field the user just edited wins: it is kept and one of the other two is
// recomputed, never the edited one itself.
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
