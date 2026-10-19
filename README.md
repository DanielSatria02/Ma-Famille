# ma-famille

Booking web app for padel clubs — hourly slots and a checkout that goes through
DOKU. A customer picks a club, picks a day, taps the hours, and pays. A club
manager runs the other side of it from a four-tab dashboard: today's bookings,
the slot grid, pricing, and the record.

One brand, two branches: Ma-Famille Premiere — Pondok Indah and Lebak Bulus.

This is the repository for a college group project. The backend is complete and
tested; the frontend covers every route a user can reach.

---

## Table of contents

- [What is in here](#what-is-in-here)
- [Stack](#stack)
- [Running it locally](#running-it-locally)
  - [Prerequisites](#prerequisites)
  - [One-time setup](#one-time-setup)
  - [Starting PostgreSQL](#starting-postgresql)
  - [Starting the backend](#starting-the-backend)
  - [Starting the frontend](#starting-the-frontend)
  - [Opening it](#opening-it)
- [Environment variables](#environment-variables)
- [Seed data](#seed-data)
- [Accounts and tokens](#accounts-and-tokens)
- [Payments](#payments)
- [Every command in the Makefile](#every-command-in-the-makefile)
- [Tests and linting](#tests-and-linting)
- [Repository layout](#repository-layout)
- [How the code fits together](#how-the-code-fits-together)
- [Feature reference](#feature-reference)
- [Frontend layout](#frontend-layout)
- [Database](#database)
- [Conventions worth knowing before you touch it](#conventions-worth-knowing-before-you-touch-it)
- [Deployment](#deployment)

---

## What is in here

| Area | What it does |
|---|---|
| **Customer flow** | Register or sign in, browse clubs on a map or a list, filter by area, see which hours are free, tap a start and an end hour, confirm, and pay. |
| **My bookings** | Every booking on the account, with its status, its payment state, and cancellation for the ones still cancellable. |
| **Live updates** | A WebSocket pushes status changes to the booking and payment pages, so a booking that is confirmed while you watch it confirms on screen. |
| **Manager dashboard** | Four tabs: today's bookings, slot generation and blocking, club hours and pricing, and the record (audit trail, guest messages, occupancy). A switch picks the branch, because one dashboard cannot be about every club at once. |
| **Pricing** | Weekday rate, weekend rate, and an optional peak-hours premium that overlays either. Promotion codes with a flat or percentage discount. |
| **Payments** | DOKU checkout, a signed webhook, refunds, and a pending-booking hold that expires on its own. |
| **Reviews** | A confirmed booking can be rated and reviewed once, tied to the booking rather than to a name. |
| **Notifications** | Guest messages on WhatsApp or email, with a `log` transport that records without sending. |

## Stack

**Frontend** — Vue 3 (Composition API, `<script setup>`), Vite, Pinia,
Vue Router, Axios, Tailwind CSS 4, Leaflet for the map, Vitest.

**Backend** — FastAPI, SQLAlchemy 2 (mapped as `Mapped[...]`), Alembic,
PostgreSQL 16, Pydantic Settings, Pytest, httpx, Ruff.

**Infrastructure** — Docker or Podman compose for the local database, uv for
the Python environment, GitHub Actions for CI and deployment, Make for the
shortcuts.

---

## Running it locally

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11 or newer | `.python-version` pins 3.11. |
| Node.js | 20 or newer | Vite 8 will not run on anything older. |
| npm | 10 or newer | Ships with Node. |
| Docker **or** Podman | any recent | Only for PostgreSQL. Podman works — see below. |
| uv | optional | Only to create the virtualenv faster. `pip` inside a venv works too. |
| GNU Make | any | Every command below goes through it. |

On Windows, run all of this inside **WSL2**. The backend uses `fuser` and
`.venv/bin/python` paths that assume a Unix shell.

### One-time setup

```bash
git clone <repository-url>
cd ma-famille

cp backend/.env.example backend/.env     # the one the API reads
cp frontend/.env.example frontend/.env   # VITE_API_URL, read at build time
```

Leave them as they are for a first run. Every setting has a default that works
against a local database, and the app starts without either file — you just get
a server with no manager password and no payment gateway, which is not what you
want to find out halfway through.

There is also a root `.env.example` covering both halves in one file. Nothing
loads it; it is there so there is one place to read every setting. Copy it if
you want the overview, edit `backend/.env` for anything that changes behaviour.

### Starting PostgreSQL

```bash
make db-up
```

That reads `docker-compose.yml` and starts one `postgres:16-alpine` container on
port 5432, with the database, role, and password all called `mafamille`.

On Podman, name the engine once per shell:

```bash
export CONTAINER_ENGINE=podman
make db-up
```

or pass it per command: `make db-up CONTAINER_ENGINE=podman`.

Check that it is actually up:

```bash
make db-logs        # follow the container log
curl http://localhost:5432  # not a web endpoint; use psql instead
```

The compose file defines a healthcheck, so `docker compose ps` showing `healthy`
means the database is ready for migrations.

### Apply the migrations

```bash
make db-upgrade
```

Twenty-four Alembic revisions take an empty database to the current schema. The
head is checked in; there is nothing to generate.

### Seed the data

```bash
make db-seed
```

Optional but recommended — without it the app is an empty map. It inserts the
two branches, their courts, and a week of hourly slots. See
[Seed data](#seed-data).

### Starting the backend

```bash
make backend-install   # first time only
make backend-dev
```

That installs into a project-local `.venv` at the repository root and starts
uvicorn with `--reload` on <http://localhost:8000>.

> **The backend reads `backend/.env`, so it runs from `backend/`.** The settings
> module looks for its `.env` relative to the working directory. The `Makefile`
> takes care of that for you, which is why `backend-dev`, `db-upgrade`, and
> `db-seed` all do `cd backend` first. Start it by hand from the repository root
> and it still comes up — with every key blank, no manager password and no
> payment gateway, and nothing in the log saying a file it should have read was
> sitting one directory down.

Do not start it with `uvicorn` directly from the root for the same reason.

Useful endpoints once it is up:

| URL | What it is |
|---|---|
| <http://localhost:8000/docs> | Interactive API documentation |
| <http://localhost:8000/v1/health> | Liveness, does not touch the database |
| <http://localhost:8000/v1/health/db> | Liveness plus a real database query |

### Starting the frontend

In a second terminal:

```bash
make frontend-install   # first time only
make frontend-dev
```

Vite serves the app on <http://localhost:5173> with hot module replacement.

### Opening it

Go to <http://localhost:5173>. You land on the home page, which is public.
Choose a club, choose a day, choose hours, and the app asks you to sign in when
you try to confirm — that is deliberate, so nobody can hold a slot without an
account.

---

## Environment variables

Three files, and they do different things:

| File | Read by | Notes |
|---|---|---|
| `.env` (root) | — | A template covering both halves. Nothing loads it. Handy as a single place to read every setting; edit `backend/.env` instead. |
| `backend/.env` | the API | The one that matters. Read relative to the working directory, so the API has to run from `backend/`. |
| `frontend/.env` | Vite | `VITE_API_URL` only, read at build time. |

The root `.env` exists so there is one place to see every setting at once. It is
not read by anything.

The ones that change behaviour rather than just working:

| Variable | Default | What it does |
|---|---|---|
| `DATABASE_URL` | local `mafamille` | PostgreSQL connection string. |
| `MANAGER_PASSWORD` | empty | Password for `POST /v1/auth/login`. **Empty disables manager login entirely**, and the dashboard sends you to the customer sign-in form. |
| `MANAGER_TOKEN` | empty | A static token that also authenticates as manager. Production sets a random one. |
| `MANAGER_SESSION_MINUTES` | 480 | How long a manager login lasts. |
| `MANAGER_LOCKOUT_ATTEMPTS` | 5 | Wrong passwords before the caller is locked out with `429` and a `Retry-After`. |
| `BOOKING_TTL_MINUTES` | 30 | How long a pending booking holds its slot before it is cancelled automatically. |
| `BOOKING_MIN_LEAD_DAYS` | 0 (prod 1) | How many days ahead a booking must be made. |
| `VENUE_TIMEZONE` | `Asia/Jakarta` | The calendar the venue keeps. Days, not hours: see below. |
| `DEFAULT_OPENS_AT` / `DEFAULT_CLOSES_AT` | `08:00` / `22:00` | Fallback opening window for a day with no stored hours. |
| `BACKEND_CORS_ORIGINS` | localhost:5173 | Comma-separated allowed origins. |
| `ROOT_PATH` | empty | Set to `/ma-famille` in production so the API sits under a subpath. |
| `NOTIFY_TRANSPORT` | `log` | `log` records the message without sending it. `smtp` and `whatsapp` actually deliver. |

**Why `VENUE_TIMEZONE` exists.** Slots store wall-clock time with no offset, so
"Tuesday" on a slot means Tuesday where the courts are. Counting lead time in
UTC meant a same-day booking was accepted all evening and refused the next
morning, with nothing deployed in between. An unknown zone name falls back to
UTC rather than stopping the API from starting.

Never commit a filled `.env`. All three are in `.gitignore`.

## Seed data

`make db-seed` is idempotent — it exits quietly if the clubs are already there,
so running it twice changes nothing.

Ma-Famille Premiere is a franchise, and a franchise does not own every club in
the city — so the seed holds the two branches the chain runs: **Pondok Indah**
and **Lebak Bulus**. The brand is the same on every card; the branch is what
the player picks and what the manager switches between.

The ground is real even though the clubs are ours. The street and the
coordinates come out of OpenStreetMap for the place in question, so the map
draws something honest and the directions link sends someone to the right
building. The courts inside each branch are invented, which they have to be:
nobody publishes a list of which court is number four.

| Branch | Street | Courts |
|---|---|---|
| Pondok Indah | Jalan Alam Permai X, Pondok Pinang, Jakarta Selatan | 5 |
| Lebak Bulus | Jalan Taman Lebak Bulus IV, Lebak Bulus, Jakarta Selatan | 4 |

Tags (`indoors`, `classes`, `competitive`, `family`, `night-owl`, `outdoors`)
drive the home page filters, so they are a small closed set — otherwise the
filter row grows a new button every time a manager types something new.

A database seeded with the older, longer club list still has those rows in
it, and the foreign keys do not cascade. Clear them with
`backend/scripts/reset-demo-data.sql` before seeding the branches.

The seed also leaves two bookings: one confirmed and one pending, so
`POST /v1/payments` can be tried straight away.

## Accounts and tokens

**Customers** register themselves at `/customers/register`. The session token is
opaque, stored hashed, lasts 14 days, and travels in the `X-Customer-Token`
header. A wrong password and an unknown email return the same response, so the
form cannot be used to find out who has an account.

**Managers** sign in at `POST /v1/auth/login` with `MANAGER_PASSWORD`. Each login
mints a distinct token, so signing out one device leaves the others signed in.
The token is HMAC-signed as `manager:<expiry>:<nonce>` and travels in the same
`X-Manager-Token` header that `MANAGER_TOKEN` uses.

With `MANAGER_PASSWORD` unset, `/manager` redirects to customer sign-in. That is
the correct behaviour, not a bug.

## Payments

See [`docs/PAYMENTS.md`](docs/PAYMENTS.md) for the full flow. The short version:

- Without DOKU keys, `POST /v1/payments` answers `501` and a refund stays local
  bookkeeping. Nothing pretends money moved.
- A pending booking holds its slot for `BOOKING_TTL_MINUTES` while payment is in
  flight, and the payment page counts it down.
- `GET /v1/config` reports `payment_configured: false` when the keys are missing
  **or** when `DOKU_SECRET_KEY` holds a SNAP key, which is a different credential
  that cannot sign a checkout request. The reason comes back as
  `payment_problem`.

## Every command in the Makefile

| Command | What it does |
|---|---|
| `make help` | List the targets, including the active container engine. |
| `make backend-venv` | Create `.venv` (uv if available, otherwise `python3 -m venv`). |
| `make backend-install` | Install `backend/requirements-dev.txt` into that venv. |
| `make backend-dev` | uvicorn with `--reload` on port 8000. |
| `make backend-test` | `pytest backend/tests -v`. |
| `make backend-lint` | `ruff check backend`. |
| `make db-up` | Start PostgreSQL. Add `CONTAINER_ENGINE=podman` for Podman. |
| `make db-down` | Stop it. |
| `make db-logs` | Follow the container log. |
| `make db-migrate m="msg"` | Autogenerate a revision. |
| `make db-upgrade` | `alembic upgrade head`. |
| `make db-downgrade` | Roll back one revision. |
| `make db-seed` | Insert the demo clubs, courts, and slots. |
| `make frontend-install` | `npm install` in `frontend/`. |
| `make frontend-dev` | Vite dev server. |
| `make frontend-build` | Production build. |
| `make test` | Backend tests and the frontend build. |

## Tests and linting

```bash
make backend-test       # 218 tests
make backend-lint       # ruff
npm --prefix frontend test        # 37 tests
npm --prefix frontend run build
```

CI (`.github/workflows/ci.yml`) runs the backend tests, ruff, the frontend tests,
and the frontend build on every push.

## Repository layout

```text
ma-famille/
  backend/
    app/
      api/v1/         # routers, one per domain
      core/           # settings
      db/             # engine, session, seed
      models/         # SQLAlchemy tables
      schemas/        # Pydantic request and response shapes
      services/       # business logic, no HTTP in here
      main.py
    tests/            # pytest, API-level against SQLite or Postgres
    alembic/          # migrations
    requirements*.txt
  frontend/
    src/
      components/     # 25 components
      views/          # 8 routed pages
      stores/         # Pinia: app, auth, bookings, checkout, customer, venues
      composables/    # useBookingForm
      services/       # api, live (websocket), payment, session
      utils/          # date, maps, booking rules, image
      styles/         # component stylesheets
      router/
  docs/
    API_CONTRACT.md   # the contract; update this before changing behaviour
    ARCHITECTURE.md
    COLLABORATION.md  # group workflow
    CONVENTIONS.md
    DATABASE.md
    DEPLOYMENT.md
    PAYMENTS.md
    adr/              # 14 architecture decision records
  scripts/            # bootstrap and deploy helpers
  media/              # uploaded venue photos
  tunnel/             # cloudflared tunnel config for the single-domain setup
  .github/workflows/  # ci, deploy, web
  Makefile
  docker-compose.yml  # local PostgreSQL
  compose.prod.yml    # production overrides
```

## How the code fits together

The backend is a conventional FastAPI split:

```
router  ->  schema  ->  service  ->  model  ->  PostgreSQL
```

Routers do HTTP: parse the request, check the token, pick the status code.
Services hold the rules and raise domain exceptions. Models are the tables.
Nothing in `services/` knows about HTTP, which is why most of the test suite
can hit the API directly without a real server.

Public IDs are UUIDv7 and the integer primary key stays internal, so a booking
identifier in a URL is not a guessable row number. See ADR 0005.

The frontend has no component library. Every component is hand-written Vue with
its own stylesheet under `src/styles/`, and Tailwind handles layout utilities.
The reason is bundle size and a team of six people editing the same files.

## Feature reference

Everything below is reachable in the running app. The API paths are all under
`/v1`.

**Public**

| Route | What it does |
|---|---|
| `GET /health`, `GET /health/db` | Liveness, with and without a database round-trip. |
| `GET /venues`, `GET /venues/tags`, `GET /venues/{id}` | Browse and search. |
| `GET /facilities` | Every bookable facility, with its venue attached. |
| `GET /availability/dates`, `GET /availability/hours` | Which days are open, which hours are free. |
| `GET /pricing/quote` | Price for a facility on a day, including peak and promo. |
| `GET /promotions/check` | Whether a code is valid and what it does. |
| `GET /reviews`, `GET /reviews/summary` | Ratings and comments. |

**Customer** (needs `X-Customer-Token`)

| Route | What it does |
|---|---|
| `POST /customers/register`, `/customers/login`, `/customers/logout`, `GET /customers/me` | The account. |
| `POST /bookings`, `POST /bookings/range`, `GET /bookings`, `GET /bookings/{id}` | Create and read. A range booking takes a contiguous run of slots in one transaction, so it cannot half-succeed. |
| `POST /bookings/{id}/cancel`, `/confirm` | Cancel or confirm. |
| `POST /bookings/groups/{id}/cancel`, `/confirm` | The same, for a multi-slot booking. |
| `POST /payments`, `POST /payments/{id}/refund` | Checkout and refund. |
| `POST /reviews` | Rate a confirmed booking, once. |
| `WS /ws/bookings/{id}` | Live status. |

**Manager** (needs `X-Manager-Token`)

| Route | What it does |
|---|---|
| `POST /auth/login`, `/auth/logout` | Sign in, with lockout. |
| `GET /manager/stats`, `/manager/bookings`, `/manager/facilities`, `/manager/occupancy` | The dashboard's numbers. |
| `POST` and `PATCH` on `/venues`, `/courts` | Create and edit. |
| `PUT /venues/{id}/hours/{day}`, `/venues/{id}/closures` | Opening hours and days off. |
| `POST /slots/generate`, `/slots/block`, `PATCH /slots/{id}` | Build the bookable grid. |
| `POST /promotions`, `PATCH` and `DELETE /promotions/{id}` | Discount codes. |
| `GET /manager/audit`, `/manager/notifications`, `POST /manager/notifications/dispatch` | The record, and guest messages. |
| `PUT` and `DELETE` on `/{venue\|court}/{id}/photo` | Images. |

## Frontend layout

Eight routed pages: `HomeView`, `LoginView`, `BookingView`, `MyBookingsView`,
`PaymentView`, `ManagerHomeView`, `HealthView`, `NotFoundView`.

A global guard in `src/router/index.js` redirects anyone who needs an account to
`/login`, carrying a validated `next` so they land where they were going. A URL
that matches no route gets `NotFoundView` — it does not bounce to sign-in.

Some things that are deliberate and will look odd otherwise:

- **No transitions between views.** Each page animates itself on mount. A
  cross-fade whose leave half never completes leaves the URL and the DOM
  disagreeing, which reads as the page not having loaded.
- **A route change is a hard navigation.** There is no stale DOM left behind.
- **The map is lazy-loaded.** Leaflet is 148 kB and only loads once there is a
  venue to put on it. `leaflet/dist/leaflet.css` is imported explicitly — without
  it the tiles render at their natural size and spill across the page, while the
  JavaScript behaves perfectly, which is a confusing way to lose an afternoon.
- **Nothing scrolls sideways.** `overflow-x: hidden` on `body`, not on `html`,
  because the sidebar is `position: fixed` and needs its containing block left
  alone.
- **A hand appears where there is something to press**, scoped to a fine
  pointer. A text field keeps the I-beam, a disabled control gets
  `not-allowed`, a slider gets `grab`.
- **Touch targets are 44px minimum** on coarse pointers, and no page overflows
  its viewport from 320px to 4K.

## Database

Fifteen tables — thirteen of them domain data, plus `audit_events`,
`revoked_tokens`, and Alembic's own `alembic_version`. PostgreSQL in development
and production. The test suite runs
each test file against its own in-memory SQLite database, so a run cannot touch
your data and needs no database to be up — which is why `make backend-test`
works on a fresh clone with nothing else running.

```
                    customer_sessions ──> customers
                                │            │
                                │            │
venues ──< courts ──< slots ──< bookings >────┘
   │              │         │        │
   │              │         │        ├── payments
   │              │         │        └── notifications
   │              │         │
   ├── venue_hours        (a booking is one slot)
   ├── venue_closures
   ├── promotions
   └── reviews

plus audit_events (who changed what) and revoked_tokens (manager sign-outs)
```

A slot is one bookable hour on one court. Status is
`available | held | booked | blocked`. Bookings reference slots directly, which
is what makes a double-booking impossible rather than merely unlikely — the
conflict check and the insert happen in one transaction.

Every foreign key is `NO ACTION`, not `ON DELETE CASCADE`. Removing a venue
means removing its slots, bookings, payments, and notifications in dependency
order. That is deliberate: a cascade on payments would let a mistake delete
financial records silently.

See [`docs/DATABASE.md`](docs/DATABASE.md) for the column-level detail.

## Conventions worth knowing before you touch it

These are the ones that will cost you an hour if you do not know them.

**Update `docs/API_CONTRACT.md` before you change behaviour.** The group
agreement is that the contract moves first. A route that changes shape without
the document changing is a broken promise to the other five groups.

**Comments and user-facing strings are in English.** All of them. The deploy
scripts were the last holdout.

**The venue's timezone decides what "today" means.** If you write a date
comparison, compare against `settings.venue_today`, never
`datetime.now(UTC).date()`. There is a test that failed for exactly this reason
and it is worth reading before you touch `bookings.py`.

**Text files are stored with CRLF** and `.gitattributes` says so. Without it
every edit looks like a thousand-line diff. Do not run a tool that rewrites line
endings — check the file after.

**`.env` files are gitignored.** Confirm with `git check-ignore -v backend/.env`
before you commit anything that looks like a key.

**One feature, one commit, semantic message.** `feat(scope): what and why`, in
the imperative. The repository is read by people who need to find the commit
that broke something.

## Deployment

`docs/DEPLOYMENT.md` has the current procedure. In short: the frontend builds
to Cloudflare Pages, the backend deploys by SSH to a single domain that routes
`/ma-famille` to the API and everything else to the static files. Secrets live
in GitHub Actions environment variables, never in the repository.

`.github/workflows/ci.yml` runs on every push. `deploy.yml` runs on `main`.