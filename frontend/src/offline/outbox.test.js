import { describe, it, expect, vi } from 'vitest';
import { createOutbox } from './outbox';

// fake-indexeddb is not installed and adding deps is out of scope, so the
// queue logic is tested against an injected in-memory store — the same
// adapter contract the IndexedDB store implements.
function createMemoryStore() {
  let seq = 0;
  const rows = [];
  return {
    async add(record) {
      const row = { ...record, id: (seq += 1) };
      rows.push(row);
      return row;
    },
    async all() {
      return rows.map((r) => ({ ...r })).sort((a, b) => a.id - b.id);
    },
    async remove(id) {
      const index = rows.findIndex((r) => r.id === id);
      if (index !== -1) rows.splice(index, 1);
    },
    // test-only peek
    rows,
  };
}

const payload = (odometer) => ({ type: 'refuel', odometer, date: '2026-07-15', total_cost: 1000 });

/** An axios network failure: the request never got a response. */
const networkError = () => Object.assign(new Error('Network Error'), { response: undefined });

const httpError = (status, detail) =>
  Object.assign(new Error(`Request failed with status code ${status}`), {
    response: { status, data: { detail } },
  });

describe('enqueue', () => {
  it('stores a pending record with the car, the payload and a timestamp', async () => {
    const store = createMemoryStore();
    const outbox = createOutbox(store);

    const record = await outbox.enqueue(7, payload(100500));

    expect(record.id).toBeDefined();
    expect(record.carId).toBe(7);
    expect(record.payload).toEqual(payload(100500));
    expect(record.status).toBe('pending');
    expect(Date.parse(record.createdAt)).not.toBeNaN();
  });
});

describe('listPending', () => {
  it('returns only the given car entries, oldest first', async () => {
    const store = createMemoryStore();
    const outbox = createOutbox(store);

    await outbox.enqueue(1, payload(10));
    await outbox.enqueue(2, payload(20));
    await outbox.enqueue(1, payload(30));

    const pending = await outbox.listPending(1);
    expect(pending.map((r) => r.payload.odometer)).toEqual([10, 30]);
  });

  it('matches the car id regardless of string/number form', async () => {
    // activeCarId lives in localStorage as a string, car.id arrives as a number.
    const store = createMemoryStore();
    const outbox = createOutbox(store);

    await outbox.enqueue(1, payload(10));

    expect(await outbox.listPending('1')).toHaveLength(1);
  });
});

describe('count', () => {
  it('counts every pending entry, or just one car when asked', async () => {
    const store = createMemoryStore();
    const outbox = createOutbox(store);

    await outbox.enqueue(1, payload(10));
    await outbox.enqueue(2, payload(20));

    expect(await outbox.count()).toBe(2);
    expect(await outbox.count(2)).toBe(1);
  });
});

describe('flush', () => {
  it('sends pending entries FIFO and removes them on success', async () => {
    const store = createMemoryStore();
    const outbox = createOutbox(store);
    await outbox.enqueue(1, payload(10));
    await outbox.enqueue(1, payload(20));

    const apiFn = vi.fn().mockResolvedValue({ id: 1 });
    const report = await outbox.flush(apiFn);

    expect(apiFn.mock.calls.map(([carId, p]) => [carId, p.odometer])).toEqual([
      [1, 10],
      [1, 20],
    ]);
    expect(report.sent).toBe(2);
    expect(report.dropped).toEqual([]);
    expect(report.remaining).toBe(0);
    expect(await outbox.count()).toBe(0);
  });

  it('keeps the queue and stops on the first network error', async () => {
    // Stopping matters: sending #2 before #1 would feed the backend an
    // out-of-order odometer.
    const store = createMemoryStore();
    const outbox = createOutbox(store);
    await outbox.enqueue(1, payload(10));
    await outbox.enqueue(1, payload(20));

    const apiFn = vi.fn().mockRejectedValue(networkError());
    const report = await outbox.flush(apiFn);

    expect(apiFn).toHaveBeenCalledTimes(1);
    expect(report.sent).toBe(0);
    expect(report.dropped).toEqual([]);
    expect(report.remaining).toBe(2);
    expect(await outbox.count()).toBe(2);
  });

  it('drops an entry the server rejects as invalid and reports it', async () => {
    const store = createMemoryStore();
    const outbox = createOutbox(store);
    await outbox.enqueue(1, payload(10));
    await outbox.enqueue(1, payload(20));

    const apiFn = vi
      .fn()
      .mockRejectedValueOnce(httpError(422, 'Пробіг не може зменшуватись'))
      .mockResolvedValueOnce({ id: 2 });
    const report = await outbox.flush(apiFn);

    expect(apiFn).toHaveBeenCalledTimes(2);
    expect(report.sent).toBe(1);
    expect(report.dropped).toEqual([
      { id: 1, carId: 1, payload: payload(10), status: 422, detail: 'Пробіг не може зменшуватись' },
    ]);
    expect(report.remaining).toBe(0);
    expect(await outbox.count()).toBe(0);
  });

  it('keeps entries on 5xx — the server is broken, the entry is not', async () => {
    const store = createMemoryStore();
    const outbox = createOutbox(store);
    await outbox.enqueue(1, payload(10));

    const report = await outbox.flush(vi.fn().mockRejectedValue(httpError(500, 'boom')));

    expect(report.sent).toBe(0);
    expect(report.dropped).toEqual([]);
    expect(report.remaining).toBe(1);
  });

  it('keeps entries on 401 — the session expired, the entry is still good', async () => {
    const store = createMemoryStore();
    const outbox = createOutbox(store);
    await outbox.enqueue(1, payload(10));

    const report = await outbox.flush(vi.fn().mockRejectedValue(httpError(401, 'Unauthorized')));

    expect(report.sent).toBe(0);
    expect(report.remaining).toBe(1);
  });

  it('keeps entries on 429 rather than throwing them away', async () => {
    const store = createMemoryStore();
    const outbox = createOutbox(store);
    await outbox.enqueue(1, payload(10));

    const report = await outbox.flush(vi.fn().mockRejectedValue(httpError(429, 'Too many')));

    expect(report.sent).toBe(0);
    expect(report.remaining).toBe(1);
  });

  it('sends an entry once even when two flushes race', async () => {
    const store = createMemoryStore();
    const outbox = createOutbox(store);
    await outbox.enqueue(1, payload(10));

    let resolveApi;
    const inFlight = new Promise((resolve) => {
      resolveApi = resolve;
    });
    const apiFn = vi.fn().mockReturnValue(inFlight);

    const first = outbox.flush(apiFn);
    const second = outbox.flush(apiFn);
    for (let i = 0; i < 10; i += 1) await Promise.resolve();
    resolveApi({ id: 1 });
    await Promise.all([first, second]);

    expect(apiFn).toHaveBeenCalledTimes(1);
    expect(await outbox.count()).toBe(0);
  });

  it('is a no-op on an empty queue', async () => {
    const outbox = createOutbox(createMemoryStore());
    const apiFn = vi.fn();

    expect(await outbox.flush(apiFn)).toEqual({ sent: 0, dropped: [], remaining: 0 });
    expect(apiFn).not.toHaveBeenCalled();
  });

  it('reports a dropped entry even with no detail from the server', async () => {
    const store = createMemoryStore();
    const outbox = createOutbox(store);
    await outbox.enqueue(1, payload(10));

    const report = await outbox.flush(vi.fn().mockRejectedValue(httpError(400, undefined)));

    expect(report.dropped).toHaveLength(1);
    expect(report.dropped[0].detail).toBeNull();
    expect(report.remaining).toBe(0);
  });
});
