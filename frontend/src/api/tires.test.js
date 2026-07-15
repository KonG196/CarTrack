import { describe, it, expect, vi, beforeEach } from 'vitest';
import client from './client';
import {
  getTireSets,
  createTireSet,
  updateTireSet,
  deleteTireSet,
  installTireSet,
  tireSeasonLabel,
  TIRE_SEASONS,
} from './tires';

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('getTireSets', () => {
  it('reads the tire sets of that car', async () => {
    client.get.mockResolvedValue({ data: [] });

    await getTireSets(7);

    expect(client.get).toHaveBeenCalledWith('/cars/7/tires');
  });

  it('returns the sets as the API ordered them', async () => {
    const data = [{ id: 2, name: 'Зима Nokian', season: 'winter', is_installed: true }];
    client.get.mockResolvedValue({ data });

    await expect(getTireSets(7)).resolves.toEqual(data);
  });
});

describe('createTireSet', () => {
  it('posts the set under that car', async () => {
    const payload = { name: 'Літо Michelin', season: 'summer', size: '205/55 R16' };
    client.post.mockResolvedValue({ data: { id: 3, ...payload } });

    await createTireSet(7, payload);

    expect(client.post).toHaveBeenCalledWith('/cars/7/tires', payload);
  });
});

describe('updateTireSet', () => {
  it('patches the set by its own id', async () => {
    client.patch.mockResolvedValue({ data: { id: 3, size: '195/65 R15' } });

    await updateTireSet(3, { size: '195/65 R15' });

    expect(client.patch).toHaveBeenCalledWith('/tires/3', { size: '195/65 R15' });
  });
});

describe('deleteTireSet', () => {
  it('deletes the set by its own id', async () => {
    client.delete.mockResolvedValue({});

    await deleteTireSet(3);

    expect(client.delete).toHaveBeenCalledWith('/tires/3');
  });
});

describe('installTireSet', () => {
  it('installs the set by its own id, with no body', async () => {
    client.post.mockResolvedValue({ data: { id: 3, is_installed: true } });

    await installTireSet(3);

    expect(client.post).toHaveBeenCalledWith('/tires/3/install');
  });

  it('returns the mounted set the swap left behind', async () => {
    const data = { id: 3, is_installed: true, odometer_at_install: 100000, km_on_set: 0 };
    client.post.mockResolvedValue({ data });

    await expect(installTireSet(3)).resolves.toEqual(data);
  });
});

describe('tireSeasonLabel', () => {
  it('names each season in Ukrainian', () => {
    expect(tireSeasonLabel('summer')).toBe('Літні');
    expect(tireSeasonLabel('winter')).toBe('Зимові');
    expect(tireSeasonLabel('all_season')).toBe('Всесезонні');
  });

  it('falls back to the raw value for an unknown season', () => {
    expect(tireSeasonLabel('autumn')).toBe('autumn');
  });
});

describe('TIRE_SEASONS', () => {
  it('mirrors the three backend seasons in display order', () => {
    expect(TIRE_SEASONS.map((s) => s.value)).toEqual(['summer', 'winter', 'all_season']);
  });
});
