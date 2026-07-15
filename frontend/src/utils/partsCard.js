// What a parts shop actually asks for, in the order they ask. Everything here
// already lives in the car and its spec sheet — the point is that ordering
// filters should not mean hunting through the app for a VIN and an oil
// approval, then retyping them into Viber.

// Spec names worth sending to a shop, by the words they are stored under. The
// sheet is free-form (the owner writes it), so matching is by substring rather
// than an exact key.
const SHOP_RELEVANT = [
  { match: ['допуск оливи', 'допуск масла'], label: 'Олива' },
  { match: ['олива двигуна', 'обʼєм оливи', "об'єм оливи"], label: 'Обʼєм оливи' },
  { match: ['антифриз', 'охолоджуюча'], label: 'Антифриз' },
  { match: ['код двигуна'], label: 'Двигун' },
  { match: ['код кпп', 'кпп'], label: 'КПП' },
  { match: ['код фарби', 'фарба'], label: 'Фарба' },
];

export function carTitle(car) {
  if (!car) return '';
  const parts = [car.brand, car.model, car.generation, car.year && `${car.year} р.`];
  return parts.filter(Boolean).join(' ');
}

function pickShopSpecs(specs) {
  const found = [];
  for (const rule of SHOP_RELEVANT) {
    const spec = (specs || []).find((item) =>
      rule.match.some((needle) => (item.name || '').toLowerCase().includes(needle)),
    );
    if (spec?.value) found.push(`${rule.label}: ${spec.value}`);
  }
  return found;
}

// A single message a shop can read: what the car is, what identifies it, and
// the numbers that decide which part fits. Anything unknown is simply absent —
// a line saying «Двигун: —» would waste the reader's attention.
export function buildSpecsMessage(car, specs) {
  if (!car) return '';
  const lines = [carTitle(car)];
  if (car.engine) lines[0] += `, двигун ${car.engine}`;
  if (car.vin) lines.push(`VIN: ${car.vin}`);
  if (car.plate) lines.push(`Номер: ${car.plate}`);
  const shopSpecs = pickShopSpecs(specs);
  if (shopSpecs.length) lines.push(...shopSpecs);
  if (car.current_odometer != null) {
    lines.push(`Пробіг: ${Math.round(car.current_odometer)} км`);
  }
  return lines.join('\n');
}

export function hasSomethingToShare(car) {
  return Boolean(car && (car.vin || car.plate || car.engine));
}
