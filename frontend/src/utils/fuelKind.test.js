import { describe, it, expect } from 'vitest';
import {
  FUEL_KIND_OPTIONS,
  fuelKindLabel,
  shouldShowFuelKind,
  shouldShowPriceChart,
  priceChartKinds,
  priceChartRows,
  PRICE_CHART_MIN_POINTS,
  consumptionKinds,
  consumptionChartRows,
  hasMixedKinds,
} from './fuelKind';

const priced = (date, fuel_kind, price_per_liter, gas_station = null) => ({
  date,
  fuel_kind,
  price_per_liter,
  gas_station,
});

describe('shouldShowFuelKind', () => {
  it('shows the selector for a gas car — it is the whole point of the feature', () => {
    expect(shouldShowFuelKind({ fuel_type: 'lpg', fuel_kinds_used: [] })).toBe(true);
  });

  it('hides it for a single-fuel car: 95% of users never chose a fuel', () => {
    expect(shouldShowFuelKind({ fuel_type: 'petrol', fuel_kinds_used: ['petrol'] })).toBe(
      false
    );
    expect(shouldShowFuelKind({ fuel_type: 'diesel', fuel_kinds_used: [] })).toBe(false);
  });

  it('shows it once a car already has refuels of different kinds', () => {
    // A car whose fuel_type was corrected away from lpg still holds mixed
    // history; hiding the selector would strand it.
    expect(
      shouldShowFuelKind({ fuel_type: 'petrol', fuel_kinds_used: ['lpg', 'petrol'] })
    ).toBe(true);
  });

  it('is false for a missing or half-loaded car rather than throwing', () => {
    expect(shouldShowFuelKind(null)).toBe(false);
    expect(shouldShowFuelKind(undefined)).toBe(false);
    expect(shouldShowFuelKind({})).toBe(false);
  });
});

describe('fuelKindLabel', () => {
  it('names every kind the API can send', () => {
    expect(FUEL_KIND_OPTIONS.map((o) => o.value)).toEqual([
      'petrol',
      'diesel',
      'lpg',
      'electric',
    ]);
    expect(fuelKindLabel('lpg')).toBe('Газ (ГБО)');
    expect(fuelKindLabel('petrol')).toBe('Бензин');
  });

  it('falls back to the raw kind rather than showing nothing', () => {
    // 'hybrid' is a car's fuel_type, so it can reach a chart legend by way of
    // an unset fuel_kind even though no refuel may be recorded as one.
    expect(fuelKindLabel('hybrid')).toBe('hybrid');
  });
});

describe('shouldShowPriceChart', () => {
  it('needs three refuels before a trend means anything', () => {
    expect(PRICE_CHART_MIN_POINTS).toBe(3);
    expect(shouldShowPriceChart([])).toBe(false);
    expect(shouldShowPriceChart([priced('2026-01-01', 'petrol', 50)])).toBe(false);
    expect(
      shouldShowPriceChart([
        priced('2026-01-01', 'petrol', 50),
        priced('2026-02-01', 'petrol', 51),
      ])
    ).toBe(false);
    expect(
      shouldShowPriceChart([
        priced('2026-01-01', 'petrol', 50),
        priced('2026-02-01', 'petrol', 51),
        priced('2026-03-01', 'petrol', 52),
      ])
    ).toBe(true);
  });

  it('is false for missing input', () => {
    expect(shouldShowPriceChart(null)).toBe(false);
    expect(shouldShowPriceChart(undefined)).toBe(false);
  });
});

describe('priceChartKinds', () => {
  it('lists the kinds present, first seen first, without duplicates', () => {
    expect(
      priceChartKinds([
        priced('2026-01-01', 'lpg', 26),
        priced('2026-02-01', 'petrol', 54),
        priced('2026-03-01', 'lpg', 27),
      ])
    ).toEqual(['lpg', 'petrol']);
  });

  it('is empty for missing input', () => {
    expect(priceChartKinds(null)).toEqual([]);
    expect(priceChartKinds([])).toEqual([]);
  });
});

describe('priceChartRows', () => {
  it('gives each refuel its own row with the price under its kind', () => {
    const rows = priceChartRows([
      priced('2026-01-01', 'lpg', 26.5, 'OKKO'),
      priced('2026-02-01', 'petrol', 54.9, 'WOG'),
    ]);

    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ date: '2026-01-01', lpg: 26.5, lpg__station: 'OKKO' });
    expect(rows[1]).toMatchObject({
      date: '2026-02-01',
      petrol: 54.9,
      petrol__station: 'WOG',
    });
  });

  it('leaves the other kinds off a row so each line only plots its own fills', () => {
    // Recharts reads an absent key as a gap; connectNulls then joins the
    // line across the other fuel's refuels instead of dropping to zero.
    const rows = priceChartRows([
      priced('2026-01-01', 'lpg', 26.5),
      priced('2026-02-01', 'petrol', 54.9),
    ]);
    expect(rows[0].petrol).toBeUndefined();
    expect(rows[1].lpg).toBeUndefined();
  });

  it('keeps two refuels on the same date as two separate rows', () => {
    // Keying rows by date would silently drop one of them.
    const rows = priceChartRows([
      priced('2026-01-01', 'lpg', 26.5),
      priced('2026-01-01', 'lpg', 27.0),
    ]);
    expect(rows).toHaveLength(2);
    expect(rows.map((r) => r.lpg)).toEqual([26.5, 27.0]);
  });

  it('preserves the order the API sent — it is already chronological', () => {
    const rows = priceChartRows([
      priced('2026-01-01', 'petrol', 50),
      priced('2026-02-01', 'petrol', 52),
      priced('2026-03-01', 'petrol', 51),
    ]);
    expect(rows.map((r) => r.petrol)).toEqual([50, 52, 51]);
  });

  it('is empty for missing input', () => {
    expect(priceChartRows(null)).toEqual([]);
    expect(priceChartRows(undefined)).toEqual([]);
  });
});

const byKind = {
  lpg: {
    history: [
      { date: '2026-01-10', consumption_l_100km: 11.25 },
      { date: '2026-03-10', consumption_l_100km: 10.0 },
    ],
  },
  petrol: {
    history: [{ date: '2026-02-10', consumption_l_100km: 6.25 }],
  },
};

describe('hasMixedKinds', () => {
  it('is true only once a second fuel appears', () => {
    expect(hasMixedKinds(byKind)).toBe(true);
    expect(hasMixedKinds({ petrol: { history: [] } })).toBe(false);
    expect(hasMixedKinds({})).toBe(false);
    expect(hasMixedKinds(null)).toBe(false);
  });
});

describe('consumptionKinds', () => {
  it('orders the kinds by how much of each was burned, biggest first', () => {
    // The car's main fuel should own the first colour and the top of the
    // legend, whatever order the JSON object happened to arrive in.
    expect(
      consumptionKinds({
        petrol: { total_liters: 55, history: [] },
        lpg: { total_liters: 125, history: [] },
      })
    ).toEqual(['lpg', 'petrol']);
  });

  it('is empty for missing input', () => {
    expect(consumptionKinds(null)).toEqual([]);
    expect(consumptionKinds({})).toEqual([]);
  });
});

describe('consumptionChartRows', () => {
  it('interleaves the kinds into one chronological series', () => {
    const rows = consumptionChartRows(byKind);
    expect(rows.map((r) => r.date)).toEqual(['2026-01-10', '2026-02-10', '2026-03-10']);
    expect(rows[0].lpg).toBe(11.25);
    expect(rows[1].petrol).toBe(6.25);
    expect(rows[2].lpg).toBe(10.0);
  });

  it('leaves the other kinds off a row so each line plots only its own segments', () => {
    const rows = consumptionChartRows(byKind);
    expect(rows[0].petrol).toBeUndefined();
    expect(rows[1].lpg).toBeUndefined();
  });

  it('is empty for missing input or a car with no measured segments', () => {
    expect(consumptionChartRows(null)).toEqual([]);
    expect(consumptionChartRows({})).toEqual([]);
    expect(consumptionChartRows({ petrol: { history: [] } })).toEqual([]);
  });
});
