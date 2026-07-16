// A наряд from the shop, mapped onto the maintenance form.
//
// The shop writes «Олива моторна 5W-30 5л»; the form has a checkbox called
// «Олива двигуна». Same thing, and the point of scanning is that the user does
// not restate it — so a scanned line that clearly names a common item ticks
// that box, and only the rest stay as free-text chips.

// Each canonical item and what a shop actually prints for it. Both halves must
// hit: a filter line names a filter AND says which one, and «Фільтр масляний»
// must not read as engine oil just because it says «масл».
const CANONICAL_SIGNS = [
  { item: 'Масляний фільтр', needs: [/фільтр|фильтр/, /масл|олив/] },
  { item: 'Повітряний фільтр', needs: [/фільтр|фильтр/, /повітр|воздуш/] },
  { item: 'Салонний фільтр', needs: [/фільтр|фильтр/, /салон|кондиц|пилк/] },
  { item: 'Паливний фільтр', needs: [/фільтр|фильтр/, /палив|топлив|дизел|соляр/] },
  { item: 'Гальмівна рідина', needs: [/рідин|жидк/, /гальм|тормоз/] },
  { item: 'Олива двигуна', needs: [/олив|мастил|масло/, /мотор|двигун|двигат|\d\dw-?\d\d/] },
];

const MAX_ITEM_NAME = 80;

export function matchCanonicalItem(rawName) {
  const name = String(rawName || '').toLowerCase();
  if (!name) return null;
  // Filters are tested before oil: «Фільтр масляний» is a filter, and the oil
  // rule would otherwise claim it on the word «масляний».
  for (const { item, needs } of CANONICAL_SIGNS) {
    if (needs.every((sign) => sign.test(name))) return item;
  }
  return null;
}

// A line the shop printed but the form has no box for — kept verbatim, only
// trimmed, because «Гвинт різьбовий М14» is the whole point of a free chip.
function asCustomItem(rawName) {
  return String(rawName).trim().slice(0, MAX_ITEM_NAME);
}

/**
 * workOrderToFormValues(scan) -> the maintenance fields a scan can fill.
 *
 * Every field is null when the scan did not read it, so the caller can leave
 * whatever the user already typed alone instead of blanking it.
 */
export function workOrderToFormValues(scan) {
  const canonical = [];
  const custom = [];

  for (const raw of scan?.items ?? []) {
    const hit = matchCanonicalItem(raw);
    if (hit) {
      if (!canonical.includes(hit)) canonical.push(hit);
      continue;
    }
    const kept = asCustomItem(raw);
    if (kept && !custom.includes(kept)) custom.push(kept);
  }

  const money = (value) => (value != null ? Number(value).toFixed(2) : null);

  return {
    date: scan?.date ?? null,
    partsCost: money(scan?.parts_cost),
    laborCost: money(scan?.labor_cost),
    totalCost: money(scan?.total_cost),
    // Order follows the form: the boxes first, then the chips it will create.
    checkedItems: [...canonical, ...custom],
    customItems: custom,
  };
}

/** What to tell the user was read, so a wrong scan is obvious before saving. */
export function describeWorkOrder(scan) {
  const values = workOrderToFormValues(scan);
  const parts = [];
  if (values.checkedItems.length) parts.push(`${values.checkedItems.length} позицій`);
  if (values.totalCost != null) parts.push(`${values.totalCost} грн`);
  return parts.join(', ');
}
