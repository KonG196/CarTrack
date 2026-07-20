export const num = (v) => {
  const n = parseFloat(String(v).replace(',', '.'));
  return Number.isFinite(n) ? n : null;
};

const FIELDS = ['liters', 'pricePerLiter', 'totalCost'];

// Fill in the one derivable refuel field from the other two. Called when the
// user pauses / leaves a field — NOT on every keystroke, so the three numbers
// stop fighting each other while you type.
//
// `order` is the fields the user edited, most-recent first. With two values
// present the empty one is computed; with all three, the field the user touched
// LEAST recently is the one recomputed (the two you just typed win). Returns a
// patch (subset of {liters,pricePerLiter,totalCost} as strings) or null.
export function deriveRefuel({ liters, pricePerLiter, totalCost }, order = []) {
  const v = {
    liters: num(liters),
    pricePerLiter: num(pricePerLiter),
    totalCost: num(totalCost),
  };
  const present = FIELDS.filter((k) => v[k] != null && v[k] > 0);

  let target;
  if (present.length === 2) {
    target = FIELDS.find((k) => !present.includes(k));
  } else if (present.length === 3) {
    const recent = order.filter((k) => present.includes(k)).slice(0, 2);
    target = FIELDS.find((k) => !recent.includes(k));
  } else {
    return null;
  }

  const { liters: l, pricePerLiter: p, totalCost: t } = v;
  if (target === 'liters' && p && t) return { liters: (t / p).toFixed(2) };
  if (target === 'pricePerLiter' && l && t) return { pricePerLiter: (t / l).toFixed(2) };
  if (target === 'totalCost' && l && p) return { totalCost: (l * p).toFixed(2) };
  return null;
}
