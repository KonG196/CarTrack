import { describe, it, expect, beforeEach } from 'vitest';
import {
  loadDismissed,
  saveDismissed,
  pruneDismissed,
  activeNotifications,
} from './notificationsDismiss';

beforeEach(() => {
  // The util tests run in a plain Node env with no localStorage — provide a
  // minimal in-memory stand-in so the store round-trips deterministically.
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
    clear: () => store.clear(),
  };
});

describe('notificationsDismiss', () => {
  it('round-trips through localStorage', () => {
    saveDismissed(new Set(['a', 'b']));
    expect(loadDismissed()).toEqual(new Set(['a', 'b']));
  });

  it('returns an empty set when nothing is stored', () => {
    expect(loadDismissed()).toEqual(new Set());
  });

  it('prunes ids that are no longer present and persists the result', () => {
    saveDismissed(new Set(['a', 'b', 'c']));
    const kept = pruneDismissed(loadDismissed(), ['b', 'c', 'd']);
    expect(kept).toEqual(new Set(['b', 'c']));
    expect(loadDismissed()).toEqual(new Set(['b', 'c']));
  });

  it('filters out dismissed notifications', () => {
    const items = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
    expect(activeNotifications(items, new Set(['b']))).toEqual([{ id: 'a' }, { id: 'c' }]);
  });
});
