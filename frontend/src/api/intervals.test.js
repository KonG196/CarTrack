import { describe, it, expect, vi, beforeEach } from 'vitest';
import client from './client';
import { completeInterval, getIntervalPresets } from './intervals';

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('completeInterval', () => {
  it('posts the payload to the complete endpoint of that interval', async () => {
    client.post.mockResolvedValue({ data: { log: { id: 5 }, interval: { id: 9 } } });
    const payload = {
      odometer: 123456,
      date: '2026-07-15',
      total_cost: 2000,
      parts_cost: 1200,
      labor_cost: 800,
      items: ['Олива двигуна'],
      notes: null,
    };

    await completeInterval(9, payload);

    expect(client.post).toHaveBeenCalledWith('/intervals/9/complete', payload);
  });

  it('returns the created log and the refreshed interval', async () => {
    const data = { log: { id: 5, type: 'maintenance' }, interval: { id: 9, status: 'ok' } };
    client.post.mockResolvedValue({ data });

    await expect(completeInterval(9, {})).resolves.toEqual(data);
  });
});

describe('getIntervalPresets', () => {
  it('reads the preset groups from the presets endpoint', async () => {
    client.get.mockResolvedValue({ data: { maintenance: [], compliance: [] } });

    await getIntervalPresets();

    expect(client.get).toHaveBeenCalledWith('/interval-presets');
  });

  it('returns the maintenance and compliance groups', async () => {
    const data = {
      maintenance: [{ title: 'Олива двигуна', interval_km: 10000, interval_days: 365 }],
      compliance: [{ title: 'Поліс ОСЦПВ', interval_km: null, interval_days: 365 }],
    };
    client.get.mockResolvedValue({ data });

    await expect(getIntervalPresets()).resolves.toEqual(data);
  });
});
