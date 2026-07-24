# Car image (prototype) — Wikimedia CC0 + marque-logo fallback

Show a picture beside the car block on the dashboard: a real photo of the car,
or the marque logo when there's no photo.

## Source decision (researched, verified live)

Dedicated render APIs were rejected: carimagesapi.com, imagin.studio and CarsXE
all **watermark their free tier across the whole car**, or aren't self-serve/free.
Verified by fetching real images from each.

**Winner: Wikimedia Commons, filtered to CC0/public-domain.** Query the File
namespace with `gsrsearch=haslicense:unrestricted <make> <model> <year>`; the top
result is a real photo of the actual model with **no watermark and no attribution
requirement**. CC0-only — no CC BY-SA fallback (user's call), so there is never a
credit obligation. ~30–50% of car photos on Commons are CC0/PD; a car with none
gets no photo.

**No-photo fallback: marque logo** from filippofilip95/car-logos-dataset (MIT,
387 brands) via the jsDelivr CDN. Showing the car's own brand logo is nominative
use of the trademark; nothing is re-hosted.

## Data model (migration 0033)

Nullable columns on **cars** (no new table): `image_url`, `image_expires_at`,
`image_checked_at`, `image_missing`.

## Backend

- `services/car_image.py`:
  - `get_car_image(db, car)` → a Wikimedia CC0 photo URL or None, cached on the
    car row (~30 days, since upload.wikimedia.org URLs are stable). Resolves once
    per car; `image_missing` latches a car with no CC0 photo. Best-effort — any
    failure yields None or the last URL, never an exception. Sends the required
    Wikimedia User-Agent.
  - `brand_logo_url(brand)` → a jsDelivr logo URL or None (no API call; gated on
    `app/car_logos.py:LOGO_SLUGS`). Brand→slug lower-cases and hyphenates.
- `GET /api/cars/{id}/image` → `{url, logo}`. No API key needed.

## Frontend

- `api/cars.js:getCarImage` → `{url, logo}`.
- `components/CarPhoto.jsx`: a small thumbnail beside the car name — the photo
  (object-cover) when present, else the logo (contained, as a badge), else
  nothing (no box, no broken image, no layout shift).

## Out of scope (prototype)

No manual per-car image picker, no 3D, no hero banner. Refine size/placement
after seeing it on real cars.
