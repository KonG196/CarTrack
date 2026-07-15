import { describe, it, expect, vi, beforeEach } from 'vitest';
import client from './client';
import { decodeVin } from './vin';

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('decodeVin', () => {
  it('posts the vin to the decode endpoint', async () => {
    client.post.mockResolvedValue({ data: { valid: false } });

    await decodeVin('WVWZZZAUZHP541983');

    expect(client.post).toHaveBeenCalledWith('/vin/decode', { vin: 'WVWZZZAUZHP541983' });
  });

  it('returns what the decoder read off the vin', async () => {
    const data = {
      wmi: 'WVW',
      manufacturer: 'Volkswagen',
      country: 'Німеччина',
      model_year: 2017,
      valid: true,
    };
    client.post.mockResolvedValue({ data });

    await expect(decodeVin('WVWZZZAUZHP541983')).resolves.toEqual(data);
  });
});
