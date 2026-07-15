import { describe, it, expect, vi, beforeEach } from 'vitest';
import client from './client';
import {
  getSpecs,
  createSpec,
  updateSpec,
  deleteSpec,
  applySpecPreset,
  groupSpecsByCategory,
  SPEC_CATEGORIES,
} from './specs';

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('getSpecs', () => {
  it('reads the cheat sheet of that car', async () => {
    client.get.mockResolvedValue({ data: [] });

    await getSpecs(7);

    expect(client.get).toHaveBeenCalledWith('/cars/7/specs');
  });

  it('returns the rows as the API ordered them', async () => {
    const data = [
      { id: 1, category: 'Моменти затяжки', name: 'Колісні болти', value: '120 Нм' },
    ];
    client.get.mockResolvedValue({ data });

    await expect(getSpecs(7)).resolves.toEqual(data);
  });
});

describe('createSpec', () => {
  it('posts the row under that car', async () => {
    const payload = { category: 'Допуски', name: 'Допуск оливи', value: 'VW 507.00' };
    client.post.mockResolvedValue({ data: { id: 3, ...payload } });

    await createSpec(7, payload);

    expect(client.post).toHaveBeenCalledWith('/cars/7/specs', payload);
  });
});

describe('updateSpec', () => {
  it('patches the row by its own id', async () => {
    client.patch.mockResolvedValue({ data: { id: 3, value: '140 Нм' } });

    await updateSpec(3, { value: '140 Нм' });

    expect(client.patch).toHaveBeenCalledWith('/specs/3', { value: '140 Нм' });
  });
});

describe('deleteSpec', () => {
  it('deletes the row by its own id', async () => {
    client.delete.mockResolvedValue({});

    await deleteSpec(3);

    expect(client.delete).toHaveBeenCalledWith('/specs/3');
  });
});

describe('applySpecPreset', () => {
  it('posts the preset key as a query param', async () => {
    client.post.mockResolvedValue({ data: [] });

    await applySpecPreset(7, 'golf7_16tdi');

    expect(client.post).toHaveBeenCalledWith('/cars/7/specs/preset', null, {
      params: { key: 'golf7_16tdi' },
    });
  });

  it('returns the whole sheet the preset left behind', async () => {
    const data = [{ id: 1, category: 'Інше', name: 'Код фарби', value: 'LI7F (Urano Gray)' }];
    client.post.mockResolvedValue({ data });

    await expect(applySpecPreset(7, 'golf7_16tdi')).resolves.toEqual(data);
  });
});

describe('groupSpecsByCategory', () => {
  it('groups rows under their category, keeping the API order inside each', () => {
    const specs = [
      { id: 1, category: 'Моменти затяжки', name: 'Колісні болти', value: '120 Нм' },
      { id: 2, category: 'Моменти затяжки', name: 'Пробка', value: '30 Нм' },
      { id: 3, category: 'Інше', name: 'Код фарби', value: 'LI7F' },
    ];

    expect(groupSpecsByCategory(specs)).toEqual([
      { category: 'Моменти затяжки', specs: [specs[0], specs[1]] },
      { category: 'Інше', specs: [specs[2]] },
    ]);
  });

  it('drops categories that have no rows', () => {
    const specs = [{ id: 3, category: 'Допуски', name: 'Паливо', value: 'ДП Євро-5' }];

    expect(groupSpecsByCategory(specs).map((g) => g.category)).toEqual(['Допуски']);
  });

  it('returns nothing for an empty sheet', () => {
    expect(groupSpecsByCategory([])).toEqual([]);
  });

  it('orders groups the way the categories are declared, not the way rows arrive', () => {
    const specs = [
      { id: 1, category: 'Інше', name: 'Код КПП', value: 'RTD' },
      { id: 2, category: 'Моменти затяжки', name: 'Колісні болти', value: '120 Нм' },
    ];

    expect(groupSpecsByCategory(specs).map((g) => g.category)).toEqual([
      'Моменти затяжки',
      'Інше',
    ]);
  });

  it('keeps an unknown category rather than swallowing the row', () => {
    const specs = [{ id: 1, category: 'Невідома', name: 'X', value: 'Y' }];

    expect(groupSpecsByCategory(specs)).toEqual([
      { category: 'Невідома', specs: [specs[0]] },
    ]);
  });
});

describe('SPEC_CATEGORIES', () => {
  it('mirrors the four backend categories in display order', () => {
    expect(SPEC_CATEGORIES).toEqual([
      'Моменти затяжки',
      'Рідини та обʼєми',
      'Допуски',
      'Інше',
    ]);
  });
});
