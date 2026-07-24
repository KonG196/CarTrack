# Notification centre: bell + modal + history page

Give notifications a persistent home: a bell icon in the header (badge = unread
count) that opens a modal of recent alerts, with a "See all" button to a full
history page. Replaces the dashboard banner.

## The storage problem

Notifications are currently **computed on read** (`services/notifications.build_notifications`)
and never stored. A nudge disappears the moment its condition stops holding (a
service is logged, a season passes, a policy renews) — so there is no history.
Decision: **persist them** in a new table so "past notifications" is real.

## Data model (migration 0032)

**notification_log** — one row per (user, stable notification id) ever seen:
- `id` PK
- `user_id` FK users ON DELETE CASCADE, indexed
- `notif_key` VARCHAR — the stable id `build_notifications` already assigns
  (e.g. `interval-<id>-due`), unique per user (unique constraint on
  user_id+notif_key)
- `kind`, `severity` VARCHAR — snapshot for display/filtering
- `car_id` INT nullable, `car_label` VARCHAR nullable — snapshot
- `title`, `body` TEXT — snapshot of the copy when first seen
- `action` VARCHAR nullable — the in-app link snapshot
- `first_seen_at` DATETIME — when it first appeared
- `read_at` DATETIME nullable — when the user opened the centre after it appeared
- `resolved_at` DATETIME nullable — when it stopped being active (condition gone)
- `last_active_at` DATETIME — last time it was still computed as active

## Backend

- `GET /notifications` (existing) keeps returning the **live/active** list, but
  now also **upserts** each active item into notification_log (insert new,
  refresh last_active_at) and marks rows whose key is no longer active as
  resolved (resolved_at set). This is the sync point — computed truth reconciled
  into stored history on every read. Response unchanged for the panel, plus an
  `unread` count.
- `GET /notifications/history` (new) — the full log, newest first, paginated,
  with active/resolved status. For the history page.
- `POST /notifications/read` (new) — mark all currently-unread rows read
  (read_at = now). Called when the modal opens. Returns the new unread count (0).
- Unread = rows with read_at IS NULL. Badge count = that.
- Keep it cheap: the upsert/reconcile runs inside the existing per-read call, a
  handful of rows per user. No new polling.

## Frontend

- **Bell in the header** (`Layout.jsx`), left of / near the car switcher, on every
  page. Shows a badge with the unread count (capped "9+"). A small store
  (`notificationStore`) holds unread + polls `/notifications` on mount / focus /
  route change (reuses the existing fetch; no new timer storm).
- **NotificationModal** (new) — opens on bell tap. Lists recent active
  notifications (reuses NotificationsPanel's row rendering), a "See all" button →
  `/notifications`, and an empty state. Opening it fires `POST /notifications/read`
  → badge clears.
- **`/notifications` becomes the history page**: active + past (resolved) rows,
  resolved ones muted with their resolved date. The per-type **settings toggles**
  move to a small section at the bottom (or stay linked from Settings) — kept, as
  the user asked.
- **Remove** `NotificationsBanner` from the dashboard.

## i18n

New keys for the modal (title, see-all, empty), history page (active/past
headers, resolved date), bell aria-label. EN + UK.

## Out of scope

No change to what notifications exist or how they're computed — only persistence,
the bell/modal surface, and the history view.
