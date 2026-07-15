import { describe, expect, it } from 'vitest';

import { computeTripCost, tripInputsFrom } from './tripCost';

describe('computeTripCost', () => {
  it('costs a drive from the car own consumption and last price', () => {
    // Lviv to the Carpathians on the seeded Golf: 240 km at 5.9 l/100 km,
    // last paid 55.99 per litre.
    const result = computeTripCost({
      distanceKm: 240,
      consumption: 5.9,
      pricePerLiter: 55.99,
      people: 3,
    });
    expect(result.liters).toBe(14.16);
    expect(result.cost).toBe(792.82);
    expect(result.perPerson).toBe(264.27);
  });

  it('doubles for the way back', () => {
    const result = computeTripCost({
      distanceKm: 100,
      consumption: 6,
      pricePerLiter: 50,
      people: 2,
    });
    expect(result.cost).toBe(300);
    expect(result.roundTripCost).toBe(600);
    expect(result.roundTripPerPerson).toBe(300);
  });

  it('accepts a decimal comma, as a Ukrainian keyboard types it', () => {
    expect(computeTripCost({ distanceKm: '12,5', consumption: 8, pricePerLiter: 50 }).liters).toBe(1);
  });

  it('never divides by fewer than one person', () => {
    const result = computeTripCost({
      distanceKm: 100,
      consumption: 6,
      pricePerLiter: 50,
      people: 0,
    });
    expect(result.people).toBe(1);
    expect(result.perPerson).toBe(300);
  });

  it('says nothing rather than guessing', () => {
    // No consumption yet (a car without two full tanks) and no price mean the
    // honest answer is silence, not a number from a brochure.
    expect(computeTripCost({ distanceKm: 240, consumption: null, pricePerLiter: 55 })).toBeNull();
    expect(computeTripCost({ distanceKm: 240, consumption: 6, pricePerLiter: null })).toBeNull();
    expect(computeTripCost({ distanceKm: 0, consumption: 6, pricePerLiter: 55 })).toBeNull();
    expect(computeTripCost({ distanceKm: 'багато', consumption: 6, pricePerLiter: 55 })).toBeNull();
  });
});

describe('tripInputsFrom', () => {
  it('takes consumption from analytics and price from the last refuel', () => {
    const inputs = tripInputsFrom(
      { fuel: { avg_consumption_l_100km: 5.9 } },
      { last_price_per_liter: 55.99 },
    );
    expect(inputs).toEqual({ consumption: 5.9, pricePerLiter: 55.99 });
  });

  it('is empty when the car has no measured consumption', () => {
    expect(tripInputsFrom({ fuel: {} }, {})).toEqual({
      consumption: null,
      pricePerLiter: null,
    });
  });
});
