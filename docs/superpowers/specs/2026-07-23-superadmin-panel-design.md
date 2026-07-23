# Superadmin panel — design

Owner-only admin panel for Kapot Tracker. Superadmin = maks060691@gmail.com.
v1 scope: **user management only** (cars/logs/intervals view later).

## Access model

- New `User.is_superadmin` boolean (default false), set manually on prod.
- Same JWT as any user; a `require_superadmin` dependency gates `/api/admin/*`.
- Frontend `/admin` section behind a route guard on `user.is_superadmin`.
- No impersonation in v1 (link-generation instead). No separate admin password.

## Data model (migration 0031)

**users** — three columns:
- `is_superadmin` BOOLEAN NOT NULL default 0 — access gate.
- `blocked` BOOLEAN NOT NULL default 0 — blocked account.
- `blocked_reason` VARCHAR(500) nullable — shown to the user on login and to the admin.

**admin_audit_log** — new table:
- `id` PK
- `actor_id` FK users ON DELETE SET NULL — who did it
- `action` VARCHAR(40) — edit_user / block / unblock / verify / unverify /
  set_superadmin / unset_superadmin / issue_reset_link / issue_verify_link /
  send_reset / send_verify / delete_user
- `target_user_id` FK users ON DELETE SET NULL — whom
- `target_email` VARCHAR(255) nullable — kept verbatim so the row still reads
  after the target is deleted
- `detail` TEXT nullable — JSON with specifics (changed fields, reason)
- `created_at` DATETIME

## Backend `/api/admin/*` (routers/admin.py)

All depend on `require_superadmin`. Every mutation writes one audit row in the
same transaction.

- GET `/users` — search (email/name), pagination, per-user counts (cars, logs), statuses
- GET `/users/{id}` — details + cars (read-only) + recent audit rows for this user
- PATCH `/users/{id}` — edit email, display_name, language, currency, unit_system
- POST `/users/{id}/status` — set email_verified / blocked(+reason) / is_superadmin
- POST `/users/{id}/reset-link` — return a reset URL
- POST `/users/{id}/verify-link` — return a verify URL
- POST `/users/{id}/send-reset` — mail the reset link to the user
- POST `/users/{id}/send-verify` — mail the verify link to the user
- DELETE `/users/{id}` — delete account (same cascade as delete_me)
- GET `/audit` — audit feed, paginated

### Safety rails (server-enforced, 400 on violation)

- Cannot block / demote (is_superadmin=false) / delete **self**.
- Blocking bumps target `token_version` → live sessions die immediately.
- Login (`/token`, Google) and `get_current_user` reject a blocked user with 403 + reason.
- Password is never edited directly — only reset link/mail (passwords are hashed).
- Editing email to one already taken → 400.
- Reset/verify links reuse existing `initiate_reset` / `issue_verification` helpers.

## Frontend

- `store/authStore` exposes `user.is_superadmin`.
- Route guard component `RequireSuperadmin` wraps `/admin/*`; non-admins → redirect `/`.
- Entry point: a discreet link in Settings (Garage) visible only to superadmin.
- Pages: `/admin` (user list + search) and `/admin/users/:id` (detail + actions).
- i18n: EN + UK strings for all admin UI.

## Tests

Non-superadmin → 403 everywhere; self block/demote/delete → 400; block kills the
token; audit row written per action; links valid; email-collision → 400; blocked
login → 403 with reason.
