# Payments via DOKU (sandbox only)

No real money moves anywhere in this project. All calls default to
`https://api-sandbox.doku.com`; production URLs must never appear in code.

## Setup

1. Register at `https://sandbox.doku.com`, grab **Client ID** + **Secret Key**.
2. Copy them into `backend/.env` (never commit real keys):
   ```bash
   DOKU_CLIENT_ID=MCH-xxxx
   DOKU_SECRET_KEY=SK-xxxx
   DOKU_BASE_URL=https://api-sandbox.doku.com
   ```
3. Without keys, `POST /payments` answers `501` and a refund stays local
   bookkeeping (see below) — nothing pretends money moved.

### Which key this wants

DOKU issues two kinds of credential and they are not interchangeable. The
checkout API used here is **non-SNAP**: it signs each request with
`HMACSHA256` computed from the **Secret Key** in DOKU Back Office
(*Settings → Keys*).

The `doku_key_...` value and the account **public key** that come with it are
the **SNAP** credential. SNAP signs with RSA using the key pair rather than with
HMAC, and DOKU answers a non-SNAP request signed with a SNAP key with
`invalid_signature` — the same refusal you would get from a mistyped secret,
which is why it is worth being sure which one you are holding.

The config detects this: a `DOKU_SECRET_KEY` starting with `doku_key_` leaves
`GET /v1/config` reporting `payment_configured: false` with a `payment_problem`
saying so, and `create_checkout` refuses before making the request rather than
after. So the tell for "wrong kind of key" is not a failure at checkout, it is
`payment_configured: false` on a config that plainly has keys in it.

## One booking, one invoice

`POST /v1/payments` is idempotent while the payment is still unpaid: calling it
again for the same booking returns the same `invoice_number` and the same
`checkout_url` instead of opening a second one. DOKU hands out a fresh invoice
on every call, and two invoices for one visit means two pages to pay and two
amounts for the venue to reconcile — with the one nobody was looking at being
the one that gets paid. The checkout page is stored on the payment row, so it
survives a refresh of the payment page.

## Test flow (no real payment)

1. `POST /v1/payments` with `booking_public_id` + `amount` → returns
   `checkout_url` (a `sandbox.doku.com` page).
2. Open the URL, pick any channel, then pay via the DOKU **Simulator**
   (`Sandbox dashboard → Settings → Simulator`).
3. DOKU POSTs the result to the Notification URL below.

No DOKU account yet? Preview the same flow with no sign-up at
`https://sandbox.doku.com/demo`.

## Webhook

- Path (fixed — DOKU signs it as Request-Target):
  `POST /v1/payments/webhook/doku`
- The endpoint recomputes `Digest` + `HMACSHA256` signature from
  `app/services/doku.py` and rejects mismatches with `401`.
- `transaction.status: SUCCESS` maps to `paid`, `FAILED`/`EXPIRED`/`CANCELLED`
  to `failed` (kept on the row as `provider_status` + `failure_reason`), anything
  else is only recorded as `provider_status`. A `paid` notification
  auto-confirms a pending booking.
- Money that arrives for a visit that was already cancelled is kept as `paid`
  with the note *"paid after the visit was cancelled — refund it"*: the manager
  sees it and refunds, instead of the app silently swallowing the payment.
- Local dev: expose the API publicly first (e.g. `ngrok http 8000`), then
  paste `https://<you>.ngrok.io/v1/payments/webhook/doku` as the
  Notification URL in the DOKU sandbox dashboard.

## Refunds

`POST /v1/payments/{public_id}/refund` (manager) refunds one **paid** payment:

- With keys: calls `POST /cancellation/credit-card/refund` and quotes the
  `original_request_id` kept from the checkout (`provider_request_id`). DOKU only
  documents this endpoint for **cards** — an e-wallet or transfer payment has to be
  refunded from the DOKU dashboard, and the service returns `502` with DOKU's own
  message rather than inventing success. A refusal leaves the payment `paid`.
- Without keys: the payment is marked `refunded` and the response says
  `provider: "local"` + *"no DOKU keys configured — the money itself has to be
  returned by hand"*.
- Anything that is not `paid` → `409` (`unpaid`/`failed`/`refunded`).

An unpaid invoice whose booking hold expired is marked `failed`
(*"the hold expired before the payment arrived"*) by the lazy sweep, so dead
invoices do not sit in the books as money owed.

## Layout

```text
app/services/doku.py   # signature, digest, checkout + refund clients, invoice numbers
app/api/v1/payments.py # /payments, /payments/{id}/refund, /payments/webhook/doku
```

