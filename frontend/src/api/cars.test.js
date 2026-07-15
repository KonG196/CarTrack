import { describe, it, expect, vi, beforeEach } from 'vitest';
import client from './client';
import { getCars, getCar } from './cars';

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('getCars', () => {
  it('keeps the role the server sent', async () => {
    client.get.mockResolvedValue({
      data: [
        { id: 7, your_role: 'viewer' },
        { id: 8, your_role: 'editor' },
      ],
    });

    const cars = await getCars();

    expect(cars.map((c) => c.your_role)).toEqual(['viewer', 'editor']);
  });

  it('reads a car with no role as owned', async () => {
    client.get.mockResolvedValue({ data: [{ id: 7, brand: 'Volkswagen' }] });

    const cars = await getCars();

    expect(cars[0].your_role).toBe('owner');
    expect(cars[0].brand).toBe('Volkswagen');
  });
});

describe('getCar', () => {
  it('keeps the role the server sent', async () => {
    client.get.mockResolvedValue({ data: { id: 7, your_role: 'editor' } });

    await expect(getCar(7)).resolves.toEqual({ id: 7, your_role: 'editor' });
  });

  it('reads a car with no role as owned', async () => {
    client.get.mockResolvedValue({ data: { id: 7, brand: 'Volkswagen' } });

    await expect(getCar(7)).resolves.toEqual({
      id: 7,
      brand: 'Volkswagen',
      your_role: 'owner',
    });
  });
});
