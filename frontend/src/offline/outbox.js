/**
 * Offline outbox for log entries.
 *
 * A record written at a no-signal gas station must survive the drive home, so
 * it goes to IndexedDB (raw API — no extra deps) and is replayed FIFO once the
 * network is back.
 *
 * Conflict rule is LWW-lite and matches the backend: the server is
 * authoritative. A queued entry never rewinds the car odometer because the
 * backend already enforces forward-only, so callers just refetch after a flush
 * and let the server state win.
 *
 * The store is injectable (see createOutbox) — the queue logic is unit-tested
 * against an in-memory adapter, since fake-indexeddb is not available here.
 */

const DB_NAME = 'kapot_tracker_outbox';
const DB_VERSION = 1;
const STORE_NAME = 'outbox';

/**
 * HTTP statuses that mean "try again later", not "this entry is bad".
 * A 401 (expired session) or 429 (rate limit) must never cost the user the
 * record they typed — only a real validation refusal drops it.
 */
const RETRYABLE_STATUSES = [401, 408, 429];

const promisify = (request) =>
  new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withStore(mode, fn) {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE_NAME, mode);
    const result = await fn(tx.objectStore(STORE_NAME));
    await new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
    return result;
  } finally {
    db.close();
  }
}

export function createIdbStore() {
  return {
    async add(record) {
      const id = await withStore('readwrite', (store) => promisify(store.add(record)));
      return { ...record, id };
    },
    // Keys are auto-incremented, so getAll() already comes back oldest first.
    all() {
      return withStore('readonly', (store) => promisify(store.getAll()));
    },
    remove(id) {
      return withStore('readwrite', (store) => promisify(store.delete(id)));
    },
  };
}

const sameCar = (a, b) => String(a) === String(b);

export function createOutbox(store) {
  let inFlight = null;

  async function enqueue(carId, payload) {
    return store.add({
      carId,
      payload,
      createdAt: new Date().toISOString(),
      status: 'pending',
    });
  }

  async function listPending(carId) {
    const rows = await store.all();
    return rows.filter((r) => r.status === 'pending' && sameCar(r.carId, carId));
  }

  /** Pending entries count — of one car when carId is given, otherwise of all. */
  async function count(carId) {
    const rows = await store.all();
    const pending = rows.filter((r) => r.status === 'pending');
    return carId === undefined ? pending.length : pending.filter((r) => sameCar(r.carId, carId)).length;
  }

  /**
   * Replays the queue FIFO through apiFn(carId, payload).
   *
   * Stops at the first retryable failure: sending a later entry first would
   * feed the backend an out-of-order odometer. Entries the server refuses as
   * invalid are dropped — retrying them forever would wedge the queue.
   *
   * @param {(carId: any, payload: object) => Promise} apiFn
   * @returns {Promise<{sent: number, dropped: object[], remaining: number}>}
   */
  function flush(apiFn) {
    if (inFlight) return inFlight;
    inFlight = runFlush(apiFn).finally(() => {
      inFlight = null;
    });
    return inFlight;
  }

  async function runFlush(apiFn) {
    const rows = await store.all();
    const pending = rows.filter((r) => r.status === 'pending');
    const dropped = [];
    let sent = 0;

    for (const record of pending) {
      try {
        await apiFn(record.carId, record.payload);
        await store.remove(record.id);
        sent += 1;
      } catch (error) {
        const status = error?.response?.status;
        const retryable =
          status === undefined || status >= 500 || RETRYABLE_STATUSES.includes(status);
        if (retryable) break;
        const detail = error?.response?.data?.detail;
        await store.remove(record.id);
        dropped.push({
          id: record.id,
          carId: record.carId,
          payload: record.payload,
          status,
          detail: typeof detail === 'string' ? detail : null,
        });
      }
    }

    // Counted from the store, not from a loop index: whatever survived the
    // run is exactly what is still waiting.
    return { sent, dropped, remaining: await count() };
  }

  return { enqueue, listPending, count, flush };
}

// The app-wide instance, backed by IndexedDB.
const outbox = createOutbox(createIdbStore());

export const enqueue = (carId, payload) => outbox.enqueue(carId, payload);
export const listPending = (carId) => outbox.listPending(carId);
export const count = (carId) => outbox.count(carId);
export const flush = (apiFn) => outbox.flush(apiFn);

export default outbox;
