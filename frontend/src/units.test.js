import { describe, it, expect } from 'vitest';
import {
  distanceFromKm,
  kmFromDistance,
  volumeFromLitres,
  litresFromVolume,
  consumptionFromL100,
  costPerDistanceFromPerKm,
  normalizeUnitSystem,
  isImperial,
} from './units';

describe('unit conversions', () => {
  it('normalizes and defaults the system', () => {
    expect(normalizeUnitSystem('imperial')).toBe('imperial');
    expect(normalizeUnitSystem('METRIC')).toBe('metric');
    expect(normalizeUnitSystem('nonsense')).toBe('metric');
    expect(normalizeUnitSystem(null)).toBe('metric');
    expect(isImperial('imperial')).toBe(true);
    expect(isImperial('metric')).toBe(false);
  });

  it('is identity in metric', () => {
    expect(distanceFromKm(100, 'metric')).toBe(100);
    expect(volumeFromLitres(40, 'metric')).toBe(40);
    expect(consumptionFromL100(8, 'metric')).toBe(8);
    expect(kmFromDistance(100, 'metric')).toBe(100);
  });

  it('converts distance km <-> mi and round-trips', () => {
    expect(distanceFromKm(160.9344, 'imperial')).toBeCloseTo(100, 6);
    expect(kmFromDistance(100, 'imperial')).toBeCloseTo(160.9344, 6);
    expect(kmFromDistance(distanceFromKm(240054, 'imperial'), 'imperial')).toBeCloseTo(240054, 3);
  });

  it('converts volume litres <-> gallons and round-trips', () => {
    expect(volumeFromLitres(3.785411784, 'imperial')).toBeCloseTo(1, 6);
    expect(litresFromVolume(1, 'imperial')).toBeCloseTo(3.785411784, 6);
    expect(litresFromVolume(volumeFromLitres(40, 'imperial'), 'imperial')).toBeCloseTo(40, 6);
  });

  it('converts l/100km to mpg (inverse, higher is better)', () => {
    // 8 l/100km ≈ 29.4 US mpg; a thirstier 16 l/100km ≈ 14.7 mpg.
    expect(consumptionFromL100(8, 'imperial')).toBeCloseTo(29.4, 1);
    expect(consumptionFromL100(16, 'imperial')).toBeCloseTo(14.7, 1);
    expect(consumptionFromL100(0, 'imperial')).toBeNull();
  });

  it('converts cost per km to cost per mile', () => {
    // A cost is larger per (longer) mile than per km.
    expect(costPerDistanceFromPerKm(1, 'imperial')).toBeCloseTo(1.609344, 6);
    expect(costPerDistanceFromPerKm(1, 'metric')).toBe(1);
  });
});
