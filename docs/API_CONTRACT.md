# API Contract (live — browse it at `GET /docs`)

Base: `/v1`. All domain routes are wired to the store; the only
`501` left is `POST /payments` (and the webhook) when DOKU keys are missing.

## Auth

- Customer reads + booking flow: open.
- `POST /auth/login` `{password}` → `{token, role, expires_at}` (501 when
  `MANAGER_PASSWORD` is unset). The token goes in the same header as the static
  token below; both are accepted until it expires. Each login mints a **distinct**
  token (random nonce), so logging out one device leaves the others signed in.
- **Lockout:** `MANAGER_LOCKOUT_ATTEMPTS` (default 5) wrong passwords from one
  caller inside `MANAGER_LOCKOUT_MINUTES` (default 15) → `429` with a
  `Retry-After` header. A correct password wipes that caller's streak. Counted
  in-process per client IP, so a restart clears it — a speed bump, not a wall.
- `POST /auth/logout` (header `X-Manager-Token`) → `{revoked}`. Session tokens
  are stateless HMACs, so this writes the token's **hash** to a deny-list that
  every manager check consults; the token stops working immediately. Idempotent
  (`revoked: false` when it was already gone). The static `MANAGER_TOKEN` is a
  shared secret, not a session, and is not revocable this way.
- Manager writes (`POST/PATCH/DELETE` venues & courts, slot create/update,
  booking confirm/cancel, payment mark-paid, all of `/manager/*`):
  header `X-Manager-Token` must match `MANAGER_TOKEN` or be a valid,
  **non-revoked** session token (empty `MANAGER_TOKEN` + empty
  `MANAGER_PASSWORD` = open, local dev). Wrong/missing/revoked → `401`.
- A customer cancels their own visit with `?customer_contact=` on the booking
  cancel routes; the contact is compared digit-wise, so `0812…` and `+62 812…`
  are the same person. A wrong or missing contact → `403` (never `401`: the
  route is not manager-only).

### Customer accounts

A customer used to be only the contact string typed into the booking form, so
"My bookings" trusted whatever was entered — the same person with a typo owned
a different history, and anyone who guessed a number could read that contact's
visits. An account replaces that with a signed-in identity.

- `POST /customers/register` `{email, password, display_name, phone?}` → `201`
  `{token, token_type, customer}`. The token is also returned in the
  `X-Customer-Token` header.
- `POST /customers/login` `{email, password}` → `200` with the same shape.
- `GET /customers/me` (header `X-Customer-Token`) → the signed-in customer.
- `POST /customers/logout` (same header) → `204`. Ends that session only.
- **Email** is the login, stored lower-case, unique — `Ana@x.test` and
  `ana@x.test` are one account. `phone` is where a venue reaches them, kept
  separate because it is usually a WhatsApp number, not the login address.
- **Password** is stored as PBKDF2-HMAC-SHA256 (stdlib, no extra dependency)
  with a per-account salt and the iteration count embedded in the hash, so the
  cost can be raised later without invalidating existing accounts.
- **Sessions** are opaque random tokens; only their SHA-256 is stored, so a
  leaked table cannot be replayed as a live login. Held in `customer_sessions`
  for 14 days. Logout deletes the row, so it takes effect immediately.
- **Refusals:** a duplicate email answers `409` (so a form can offer "sign in"
  instead of retrying); other input problems answer `422`. A wrong password
  and an unknown email both answer `401` with the *same* message — telling
  them apart is what makes credential stuffing cheap.

## Identifiers

- `id` (integer, autoincrement): system-level PK, FKs and joins only. Never
  exposed to clients.
- `public_id` (UUIDv7, unique + indexed): the only id clients see, in URLs
  and payloads. Chosen over random v4 GUIDs because v7 is time-ordered —
  sortable and index-friendly — while staying unguessable enough for public
  references. See `backend/app/core/ids.py` and `docs/DATABASE.md`.

## Entities (all carry `public_id`, FKs reference `public_id` client-side)

### Venue
```json
{ "public_id": "uuidv7", "name": "GOR Senayan", "address": "...", "tags": ["indoors", "event"], "lat": -6.2185, "lng": 106.8022, "image_url": "/media/venues/<public_id>.png | null" }
```
`tags` are lower-cased and de-duplicated on write and power the client filters
(`GET /venues?tag=outdoors&q=depok`); `GET /venues/tags` lists the vocabulary in
use, so the filter panel needs no hardcoded options.

### Court
```json
{ "public_id": "uuidv7", "venue_public_id": "uuidv7", "name": "Court A", "sport": "futsal|badminton", "kind": "court|office|cafe", "price_weekday": 100000, "price_weekend": 150000, "price_peak": 200000, "peak_start_hour": 17, "peak_end_hour": 21, "is_price_set": true, "is_active": true, "image_url": "/media/courts/<public_id>.jpg | null" }
```
`price_*: null` (and `is_price_set: false`) means the manager has not priced the
facility: it is listed to clients but cannot be booked. `PATCH` writes only the
fields present in the body, so `"price_weekday": null` clears that rate.

**Peak-hour pricing** is an optional premium layered over the day's rate. It is
active only when all three fields are set together — `price_peak` (the rate),
`peak_start_hour` and `peak_end_hour` — and it applies inside the half-open
window `[start, end)`, so 17–21 prices hours 17, 18, 19 and 20. Outside the
window the weekday/weekend rate stands; on a weekend hour inside the window the
peak rate still wins. A partial window is a `422`, not a silent no-op.

Slots are priced **per hour at generation time**, and `POST /slots/generate`
skips hours that already exist — so a `PATCH` that touches any rate field
(`price_weekday`, `price_weekend`, `price_peak`, `peak_start_hour`,
`peak_end_hour`) also **restamps the court's still-open future slots** with the
current rates. Without that, raising a rate (or adding a peak window) would
never reach a schedule that was already generated and quote would keep charging
the old price. What is *not* restamped:

- **Booked / held slots** — the customer agreed to that price, and rewriting it
  would change an invoice that exists.
- **Slots in the past** — history is not rewritten by a rate change.

So a rate change reads as: open hours move, sold hours and history stay put.

### VenueClosure (holiday)
```json
{ "public_id": "uuidv7", "venue_public_id": "uuidv7", "starts_on": "2026-12-25", "ends_on": "2026-12-26", "days": 2, "reason": "Christmas" }
```
Overrides the weekly hours for the dates it covers: `/availability/hours` reports the day
`is_closed` with `closure_reason`, `/availability/dates` omits it, `POST /slots/generate`
counts it in `skipped_closure_days`, and booking that date answers `409` `venue is closed
on YYYY-MM-DD (reason)` — including for slots generated before the closure was added.
Creating one returns `affected_bookings`: the live bookings already inside the window,
so the manager knows who to call. Max 90 days per closure.

### Notification (guest message)
```json
{ "public_id": "uuidv7", "event": "pending|confirmed|cancelled", "channel": "email|whatsapp", "recipient": "0812…", "subject": "Booking received: …", "body": "Hi Budi, …", "status": "queued|sent|logged|failed", "transport": "log|smtp|whatsapp", "error": "", "attempts": 0, "sent_at": null }
```
Written by the booking flow (one message per visit, not per hour), so a guest never loses
a booking because a mail server was down. `channel` follows the contact: an address with
`@` is email, anything else is treated as a WhatsApp number (`0812…` → `62812…`).
`POST /manager/notifications/dispatch` is the only thing that leaves the building, and it
reports the truth: `sent` (a provider accepted it), `logged` (no provider configured, so
the message was only recorded — the default `NOTIFY_TRANSPORT=log`), `failed` (provider
said no; reason kept on the row), still `queued` (the transport cannot carry that channel,
or `SMTP_HOST` / `WHATSAPP_*` are missing).

### Slot (Schedule)
```json
{ "public_id": "uuidv7", "court_public_id": "uuidv7", "starts_at": "2026-09-20T10:00:00Z", "ends_at": "2026-09-20T11:00:00Z", "price": 120000, "status": "available|held|booked|blocked" }
```
Rule: `ends_at > starts_at`. No overlap for same court unless `status=blocked` replaced.

### Booking
```json
{ "public_id": "uuidv7", "slot_public_id": "uuidv7", "group_public_id": "uuidv7", "customer_name": "...", "customer_contact": "...", "status": "pending|confirmed|cancelled", "created_at": "..." }
```
Every booking response also embeds `slot` (`starts_at`, `ends_at`, `price`, `status`),
`court` (`name`, `sport`), `venue` (`name`), `total`, `discount`, `promo_code`,
`payment_status`, `expires_in_seconds`
(`null` unless the booking is still on hold as `pending`) and — once an invoice exists —
`payment_public_id` + `payment_invoice_number`, so list views render without a follow-up
request per row and the manager can mark that payment paid. `total` is already net of
`discount`; `promo_code` is `null` when no code was used.
Rules:
- One active booking per slot (overlap/conflict guard backend-side, `409`).
- `pending` expires after TTL unless confirmed + deposit.

### Payment
```json
{ "public_id": "uuidv7", "booking_public_id": "uuidv7", "amount": 60000, "kind": "deposit|full", "status": "unpaid|paid|failed|refunded", "invoice_number": "MAF-…", "provider_status": "SUCCESS|EXPIRED|…", "failure_reason": "gateway reported EXPIRED", "refunded_at": null }
```
`invoice_number` links the row to the DOKU sandbox checkout (see `docs/PAYMENTS.md`).
`provider_request_id` (not exposed) is the DOKU Request-Id of that checkout: a refund
must quote it. `provider_status` keeps the raw gateway status even when it changes no
state; `failure_reason` carries the human-readable why (a gateway failure, an expired
hold, or *"paid after the visit was cancelled — refund it"*). A refund answers
`{payment, provider: "doku"|"local", detail}` so the caller knows whether money actually
moved (`local` = no DOKU keys, bookkeeping only).

## Endpoints

```text
GET    /config (booking TTL, min lead days, login + payment availability)
GET    /venues /venues/{public_id}            POST /venues (manager)
PATCH  /venues/{public_id} (manager)          DELETE /venues/{public_id} (manager)
GET    /venues/{public_id}/hours (7 days)     PUT /venues/{public_id}/hours/{day} (manager, 0=Mon)
GET    /venues/{public_id}/closures            POST /venues/{public_id}/closures (manager, 201)
DELETE /venues/{public_id}/closures/{public_id} (manager, 204)
PUT    /venues/{public_id}/photo      (manager, raw image body)   DELETE …/photo (manager, 204)
PUT    /courts/{public_id}/photo      (manager, raw image body)   DELETE …/photo (manager, 204)
GET    /media/{venues|courts}/{public_id}.{png|jpg|gif|webp}  (static, no auth)
GET    /courts?venue_public_id=...            POST /courts (manager)
GET    /facilities?venue_public_id=&kind= (client picker: bookable + reason)
GET    /manager/facilities (rates, locked until priced)
PATCH  /courts/{public_id} (manager)          DELETE /courts/{public_id} (manager, deactivates)
GET    /slots?court_public_id=&day=           POST /slots (manager, bulk)
POST   /auth/login {password} → {token}       (token replaces MANAGER_TOKEN)
POST   /auth/logout                            (deny-list the session token)
POST   /slots/generate (manager, from venue hours, idempotent)
POST   /slots/block (manager, close/reopen a window of hours; booked hours untouched)
GET    /availability/hours?court_public_id=&day=  GET /availability/dates?court_public_id=&from_day=&to_day=
GET    /pricing/quote?court_public_id=&starts_at=&ends_at= (rate, total, bookability; per-hour peak applies)
PATCH  /slots/{public_id} (manager, open/close)
POST   /bookings  (409 on conflict)           GET /bookings?customer_contact= (history)
POST   /bookings/range (whole-hour range on one court → one group, 409 on conflict)
     └ both accept optional `promo_code`; a refused code is 422 and books nothing
POST   /bookings/groups/{group_public_id}/confirm (manager, every hour of the visit)
POST   /bookings/groups/{group_public_id}/cancel (manager, or the customer with `customer_contact`)
POST   /bookings/{public_id}/confirm (manager)  POST /bookings/{public_id}/cancel (same rule)
POST   /payments  → {invoice_number, checkout_url}   GET /payments?booking_public_id=
POST   /payments/{public_id}/mark-paid (manager, auto-confirms a pending booking)
POST   /payments/{public_id}/refund    (manager, paid only: DOKU refund, or local note)
POST   /payments/webhook/doku (DOKU signed notification → paid + auto-confirm)
GET    /manager/bookings?booking_status=&day=&from_day=&to_day=&limit=&offset=   GET /manager/occupancy?from_day=&to_day=
GET    /manager/stats?day=&week_start= (dashboard counters, one visit = one booking group)
GET    /manager/notifications?status=&limit=&offset= (outbox: queued/sent/logged/failed)
POST   /manager/notifications/dispatch?limit= (send the queue once, reports the tally)
GET    /manager/audit?entity_type=&entity_public_id=&action=&actor=&limit=&offset=
GET    /promotions?limit=&offset=             POST /promotions (manager, 201; 409 on dup code)
PATCH  /promotions/{public_id} (manager)      DELETE /promotions/{public_id} (manager, 204;
                                              409 if already redeemed — deactivate instead)
GET    /promotions/check?code=&court_public_id=&starts_at=&ends_at= (public, dry run)
```
Every manager booking row carries `payment_public_id`, `payment_invoice_number`,
`payment_status` and `payment_failure_reason` so the dashboard can show (and refund)
the money side of a visit without a second request. Rows are also served with
`expires_in_seconds` while a booking is still held.

### Paging

List endpoints that grow without bound (`/bookings` history, `/manager/bookings`,
`/manager/notifications`) take `limit` (default 50, max 200) and `offset` (default 0).
They return a slice of the same JSON array — the body never changes shape — and put
the un-sliced row count in an `X-Total-Count` response header (exposed through CORS),
so the client can render "load more" or a page count without a second call. Out-of-range
`limit`/`offset` is a `422`, not a silent clamp.

### Audit trail

Every successful state-changing request under `/v1/` (POST/PUT/PATCH/DELETE that
answers 2xx) appends a row to an **append-only** log, read back through
`GET /manager/audit` (manager-only, paged like the lists above). Filters:
`entity_type` (venue, court, slot, booking, payment…), `entity_public_id` (one
row's whole history), `action` (`venue.update`, `payment.refund`, `booking.confirm`…),
`actor` (`manager` or `customer`). Actions are derived from the path — a trailing
sub-action (`/payments/{id}/refund`) beats the HTTP verb. Two honest limits:

- **Creates** carry no row id in the request path (it exists only in the response),
  so `entity_public_id` is `null` for them. Every later update/confirm/refund on
  that row *is* logged against its id.
- A **4xx** changed nothing, so it is never logged.

Recording is best-effort: if the audit write fails, the business response still
goes out (the trail must never turn a booking into a 500).

### Promo codes

A manager mints a code (`percent` = 1–100, or `amount` = rupiah off), optionally
scoped to one venue and bounded by `valid_from`/`valid_to`/`max_uses`. Codes are
**case-insensitive and stored upper-case**, so `hemat` and `HEMAT` are one voucher;
a duplicate is `409`.

Redeeming: `POST /bookings` and `POST /bookings/range` take an optional
`promo_code`. The code is re-verified at booking time — the client's check is a
hint, never the authority — and the use count is redeemed in the same
transaction, so a rollback gives the use back. A refused code is `422` with a
reason the customer can act on, and **books nothing**:

| refusal | message |
|---|---|
| unknown | `that code does not exist` |
| switched off | `that code is no longer active` |
| not started / past | `that code is not active yet` / `that code has expired` |
| used up | `that code has been used the maximum number of times` |
| other venue | `that code is only valid for a different venue` |

`GET /promotions/check` is the public dry run the client calls before booking.
It writes nothing, and its refusal must match booking-time refusal exactly.

Money: the discount is capped at the gross, so a code can never make a booking
cost less than zero. On a **multi-hour group** one code prices the whole
purchase, and the discount sits on the group's first row only — summing the
rows' `discount` counts it exactly once, and `BookingRangeResponse.total` is
already net (`gross - discount`). `total` per row is likewise net.

### Photos (venues and courts)

Each row carries `image_url`: null (the client draws its own placeholder), an upload
path under `/media`, or a link the manager pasted (`PATCH` accepts only `http(s)` or
`/media/…`). Uploading is a **raw body**, not multipart — no extra dependency:

```bash
curl -X PUT --data-binary @court.png -H 'Content-Type: image/png' \
     http://localhost:8000/v1/venues/<public_id>/photo     # → 200 with the updated row
```

- Type is sniffed from magic bytes (PNG, JPEG, GIF, WebP) → anything else is `415`.
- Bigger than `MAX_PHOTO_BYTES` (500 kB default) → `413`.
- One photo per venue/court: a second upload replaces the first and deletes the old file.
- `DELETE …/photo` → `204` and the file is gone. Unknown id → `404`.
- Files live in `backend/media/<venues|courts>/<public_id>.<ext>` (gitignored) and are served
  at `/media/…` with no auth, which is what the frontend's `<img>` needs. Uploading is the
  only way to get a URL under `/media`; nothing else can write there.

Booking also flips `slot.status` (`available`→`booked` on create,
back to `available` on cancel), so the availability calendar never shows
a taken slot as free.

## Errors

```json
{ "detail": "slot is booked" }
```
- `409` for booking conflicts (`slot is booked`, or `slot already booked`
  on a write race).
- `422` for validation.
- `404` for unknown ids.
- `401` for manager routes without a valid token.

Frontend must surface `detail` verbatim and refresh slot state after `409`.
