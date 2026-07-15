import { describe, it, expect, vi, beforeEach } from 'vitest';
import client from './client';
import { importObdCsv, getObdSessions, getObdSession, deleteObdSession } from './obd';

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('importObdCsv', () => {
  it('posts the csv as multipart form data under the car', async () => {
    client.post.mockResolvedValue({ data: { session: { id: 7 } } });
    const file = new File(['Time,DPF soot mass (g)\n0,18.4\n'], 'golf.csv', {
      type: 'text/csv',
    });

    await importObdCsv(3, file);

    const [url, body] = client.post.mock.calls[0];
    expect(url).toBe('/cars/3/obd');
    expect(body).toBeInstanceOf(FormData);
    expect(body.get('file')).toBe(file);
  });

  it('returns the parsed session, metrics and verdicts', async () => {
    const data = {
      session: { id: 7, sample_count: 3 },
      metrics: [{ key: 'dpf_soot_mass', last: 18.8, series: [[0, 18.4]] }],
      verdicts: [{ key: 'dpf', level: 'warn', text: '🟡 Регенерація скоро.' }],
      unmapped_columns: [],
    };
    client.post.mockResolvedValue({ data });

    await expect(importObdCsv(3, new File([''], 'a.csv'))).resolves.toEqual(data);
  });
});

describe('getObdSessions', () => {
  it('lists the sessions of a car', async () => {
    client.get.mockResolvedValue({ data: [{ id: 7 }] });

    await expect(getObdSessions(3)).resolves.toEqual([{ id: 7 }]);
    expect(client.get).toHaveBeenCalledWith('/cars/3/obd');
  });
});

describe('getObdSession', () => {
  it('reads one session by its own id', async () => {
    client.get.mockResolvedValue({ data: { session: { id: 7 } } });

    await expect(getObdSession(7)).resolves.toEqual({ session: { id: 7 } });
    expect(client.get).toHaveBeenCalledWith('/obd/7');
  });
});

describe('deleteObdSession', () => {
  it('deletes the session', async () => {
    client.delete.mockResolvedValue({});

    await deleteObdSession(7);

    expect(client.delete).toHaveBeenCalledWith('/obd/7');
  });
});
