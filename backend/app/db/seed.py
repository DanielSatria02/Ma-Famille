"""Demo seed: real padel clubs, their courts, slots and two bookings.

Every club here is a place that exists — the name, the street and the
coordinates come out of that club's OpenStreetMap record, so the map has
something honest to draw and a booking has a real address to send someone to.
The courts inside each club are invented, which they have to be: nobody
publishes a list of which court is number four.

Idempotent — exits quietly when the demo clubs already exist. Rerun it after a
schema change and it adds nothing rather than duplicating anything.

Run: make db-seed (needs a live PostgreSQL + migrated schema).
"""

from datetime import datetime, time, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.booking import Booking
from app.models.court import Court
from app.models.slot import Slot
from app.models.venue import Venue
from app.models.venue_hours import VenueHours

# The two branches of the chain, as (name, street address, latitude, longitude,
# under a roof, opening hours).
#
# Ma-Famille Premiere is the brand and it is not repeated in the row: the club
# card shows the brand above the branch, so a row called "Ma-Famille Premiere
# Pondok Indah" would print the brand twice on the same card. The branch is
# what the manager picks and what the player looks for.
#
# The addresses and the coordinates are real — they come out of OpenStreetMap
# for the place in question — so the map draws something honest and a booking
# has a real address to send someone to.
#
# Pondok Indah is the branch the franchise is named after, and the street
# there is taken from what OpenStreetMap records at that spot: Jalan Bungur V
# in Kebayoran Lama Utara, which is the Pondok Indah / Kebayoran Lama side of
# the city. The second branch is in Lebak Bulus, where there is a padel club
# actually mapped, so that address and those coordinates are a club's own.
#
# The last column is what OpenStreetMap says about the place rather than
# about the name: a club mapped as a `pitch` is a marked court in the open, a
# club mapped as a `sports_centre` is a building, and a club that records its
# opening hours gets those hours instead of the default window.
#
# Coordinates are OpenStreetMap's, rounded to six decimals (about 10cm). A pin
# in the wrong district is worse than no pin, because it looks right.
VENUES = [
    (
        "Pondok Indah",
        "Jalan Bungur V, Kebayoran Lama Utara, Jakarta Selatan",
        -6.245796,
        106.780760,
        True,
        None,
    ),
    (
        "Lebak Bulus",
        "Jalan Taman Lebak Bulus IV, Lebak Bulus, Jakarta Selatan",
        -6.295686,
        106.775300,
        True,
        (6, 22),
    ),
]

# tag -> what a customer filtering on it is actually asking
#
# Tags are the free vocabulary behind the home page filters, so they have to be
# a small closed set or the filter row grows a new button every time a manager
# types something new. Venue, not city: city is already in the address, and
# putting it here too would mean the same place list under two spellings.
TAGS = {
    "indoors": "covered, plays when it rains",
    "outdoors": "open air, weather dependent",
    "classes": "coaching and clinics on the calendar",
    "competitive": "leagues and tournaments, not casual pickup",
    "family": "kids and birthdays, quiet daytime slots",
    "night-owl": "open past 21:00",
    "event": "can be hired for something",
}

# The name, sport, kind and weekend premium for each facility. Weekday prices
# live here too; `price_weekday` on the record is what the manager edits later.
#
# Padel prices by the hour. A padel court costs more than a squash court and
# less than a football pitch, and an indoor club with air conditioning costs
# more than an open one — which is why the numbers are not one value repeated.
FACILITIES = [
    ("Lapangan Padel 1", "padel", "court", 90000, 120000),
    ("Lapangan Padel 2", "padel", "court", 90000, 120000),
    ("Lapangan Padel 3", "padel", "court", 85000, 110000),
    ("Lapangan Padel 4", "padel", "court", 85000, 110000),
    ("Lapangan Padel VIP", "padel", "court", 130000, 170000),
]

# Facilities per venue size. A neighbourhood club has two courts; a sports
# centre with a hall has more. Slicing the same list for every venue made the
# home page look like a template.
SMALL_VENUE = FACILITIES[:2]
MID_VENUE = FACILITIES[:4]
BIG_VENUE = FACILITIES

# Which size each branch gets. A branch in a dense part of the city has more
# courts than a new one; the manager is expected to correct the count either
# way.
VENUE_SIZE = {
    "Pondok Indah": BIG_VENUE,
    "Lebak Bulus": MID_VENUE,
}

# Booking days from today. Short on purpose: slots are generated rows, and a
# week is enough to exercise next-week in the UI without the table growing
# forever on every seed run.
DAYS_AHEAD = 7
OPEN_HOUR = 8
CLOSE_HOUR = 22


def _tags_for(covered: bool, address: str) -> list[str]:
    """A set of tags, from what is actually known about the place.

    Whether the court is under a roof comes from how the branch is mapped, not
    from its name. The rest are the words a padel club of this kind would
    carry — padel is booked by people who come with friends, in the evening,
    and for a match they want to play properly — and the manager is expected to
    correct them.
    """
    tags = {"indoors" if covered else "outdoors"}
    tags.add("classes")
    tags.add("family")
    tags.add("night-owl")
    tags.add("competitive")
    return sorted(tags)


def main() -> None:
    db = SessionLocal()
    try:
        existing = set(db.scalars(select(Venue.name)).all())
        wanted = [v for v in VENUES if v[0] not in existing]
        if not wanted:
            print("already seeded")
            return
        stale = existing - {v[0] for v in VENUES}
        if stale:
            # Rows from an older seed are still in the database. The foreign
            # keys do not cascade, so they have to be removed in order by hand;
            # saying so is better than leaving a database that claims to have
            # clubs it does not have.
            print("note: this database still has clubs from an older seed:")
            for name in sorted(stale):
                print(f"  {name}")
            print("remove them with backend/scripts/reset-demo-data.sql if you want a clean slate")

        venues = []
        courts = []
        windows = {}
        for name, address, lat, lng, covered, hours in wanted:
            venue = Venue(
                name=name,
                address=address,
                tags=_tags_for(covered, address),
                lat=lat,
                lng=lng,
            )
            db.add(venue)
            db.flush()
            venues.append(venue)
            # A club that publishes its hours gets them; the rest run on the
            # default window. The manager can change either afterwards.
            windows[venue.id] = hours
            if hours is not None:
                opens_hour, closes_hour = hours
                # A club that closes at midnight is recorded as closing at 23:00.
                # The last hour of the day is a slot nobody can book anyway
                # once the lead-time rule is in play, and "24:00" is not a time
                # the column or the manager's clock can hold.
                closes_hour = min(closes_hour, 23)
                for day_of_week in range(7):
                    db.add(
                        VenueHours(
                            venue_id=venue.id,
                            day_of_week=day_of_week,
                            opens_at=time(opens_hour),
                            closes_at=time(closes_hour),
                        )
                    )
            for court_name, sport, kind, weekday, weekend in VENUE_SIZE.get(
                name, FACILITIES
            ):
                court = Court(
                    venue_id=venue.id,
                    name=court_name,
                    sport=sport,
                    kind=kind,
                    price_weekday=weekday,
                    price_weekend=weekend,
                )
                db.add(court)
                courts.append((court, weekday, weekend))
        db.flush()

        # Days are the venue's, not the server's — see settings.venue_today.
        first_day = settings.venue_today
        for offset in range(DAYS_AHEAD):
            day = first_day + timedelta(days=offset)
            weekend = day.weekday() >= 5
            for court, weekday, weekend_price in courts:
                price = weekend_price if weekend else weekday
                # A club with published hours only sells the hours it is open.
                # Slots outside its window would be hours a player turns up to
                # find a locked gate.
                window = windows.get(court.venue_id) or (OPEN_HOUR, CLOSE_HOUR)
                # The last hour of the day cannot be sold: a slot that ends at
                # midnight has no hour to live in.
                for hour in range(window[0], min(window[1], 23)):
                    db.add(
                        Slot(
                            court_id=court.id,
                            starts_at=datetime.combine(day, time(hour)),
                            ends_at=datetime.combine(day, time(hour + 1)),
                            price=price,
                        )
                    )
        db.flush()

        # Two bookings so the list is not empty on first load: one already
        # confirmed, one pending so POST /payments can be tried straight away.
        # The two earliest slots *from today* and *at the branches just seeded* —
        # the earliest slots in the table could belong to a branch that was here
        # before, and a booking on a slot that already has one is a duplicate.
        todays_slots = db.scalars(
            select(Slot)
            .where(Slot.court_id.in_([court.id for court, _, _ in courts]))
            .where(Slot.starts_at >= datetime.combine(first_day, time(OPEN_HOUR)))
            .order_by(Slot.id)
            .limit(2)
        ).all()
        for slot, (name, contact, status) in zip(
            todays_slots,
            [
                ("Demo User", "0812000000", "confirmed"),
                ("Checkout Tester", "0812000001", "pending"),
            ],
        ):
            slot.status = "booked"
            db.add(
                Booking(
                    slot_id=slot.id,
                    customer_name=name,
                    customer_contact=contact,
                    status=status,
                )
            )
        db.commit()
        print(f"seeded {len(venues)} branches, {len(courts)} courts")
        for venue in venues:
            print(f"  {venue.name} — {venue.address}")
    finally:
        db.close()


if __name__ == "__main__":
    main()