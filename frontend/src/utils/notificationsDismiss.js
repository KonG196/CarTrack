// Client-side dismiss for the in-app notification centre. Nudges are computed
// fresh on read and carry a stable id, so remembering the dismissed ids locally
// is enough — and a nudge that changes (a new due mark, a new year) gets a new
// id and re-appears on its own.

const KEY = 'kapot_dismissed_notifications';

export function loadDismissed() {
  try {
    return new Set(JSON.parse(localStorage.getItem(KEY)) || []);
  } catch {
    return new Set();
  }
}

export function saveDismissed(dismissed) {
  try {
    localStorage.setItem(KEY, JSON.stringify([...dismissed]));
  } catch {
    /* private mode — dismiss simply won't persist */
  }
}

// Drop remembered ids that no longer appear, so the store can't grow forever
// and a nudge whose id changed is not permanently silenced.
export function pruneDismissed(dismissed, presentIds) {
  const present = new Set(presentIds);
  const kept = new Set([...dismissed].filter((id) => present.has(id)));
  if (kept.size !== dismissed.size) saveDismissed(kept);
  return kept;
}

export function activeNotifications(items, dismissed) {
  return items.filter((note) => !dismissed.has(note.id));
}
