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

# name, street address, latitude, longitude, under a roof, opening hours
#
# Padel clubs in and around Jakarta. Every one of them is a place that exists:
# the name, the street and the coordinates come out of that club's own
# OpenStreetMap record, so the map has something honest to draw and a booking
# has a real address to send someone to. Two of them sit in a town just outside
# the city — a padel player drives for a good court, and the ones worth driving
# to are not all inside the ring road.
#
# The last two are what OpenStreetMap says about the place rather than about
# the name: a club mapped as a `pitch` is a marked court in the open, a club
# mapped as a `sports_centre` is a building, and a club that records its
# opening hours gets those hours instead of the default window.
#
# Coordinates are OpenStreetMap's, rounded to six decimals (about 10cm). A pin
# in the wrong district is worse than no pin, because it looks right.
VENUES = [
    (
        "Agora Padel",
        "Jalan Kota Bumi, Tanah Abang, Jakarta Pusat",
        -6.198632,
        106.821108,
        False,
        None,
    ),
    (
        "Athletiqs Airdome",
        "Jalan K.H. Mas Mansyur, Tanah Abang, Jakarta Pusat",
        -6.211882,
        106.813886,
        True,
        (6, 24),
    ),
    (
        "Booster Arena",
        "Jalan Andara, Cinere, Depok",
        -6.316026,
        106.803453,
        False,
        None,
    ),
    (
        "Commune Court",
        "Jalan Lingkar Luar Barat, Cengkareng, Jakarta Barat",
        -6.173629,
        106.731041,
        False,
        None,
    ),
    (
        "Crown Padel",
        "Jalan Gempol Raya, Alam Sutera, Pinang, Tangerang",
        -6.228010,
        106.660490,
        True,
        None,
    ),
    (
        "Double Padel by Kadena",
        "Jalan Taman Lebak Bulus IV",
        -6.295686,
        106.775300,
        True,
        (6, 22),
    ),
    (
        "Filari Sport Center",
        "Jalan Sigura Gura II",
        -6.258682,
        106.834028,
        True,
        None,
    ),
    (
        "Home Ground Kedoya",
        "Gang Bakti Karya, Kebon Jeruk, Jakarta Barat",
        -6.187570,
        106.760214,
        True,
        None,
    ),
    (
        "Kula Courts",
        "Jalan Tol Jakarta–Merak, Pinang, Tangerang",
        -6.221654,
        106.652956,
        False,
        None,
    ),
    (
        "Master Padel",
        "Jalan Yos Sudarso, Tanjung Priok, Jakarta Utara",
        -6.146385,
        106.889688,
        False,
        None,
    ),
    (
        "Matchaus Padel & Pickleball",
        "Jalan Bekasi Raya, Cakung, Jakarta Timur",
        -6.183150,
        106.911391,
        True,
        None,
    ),
    (
        "Metro Padel",
        "Jalan Sampora Raya, BSD City",
        -6.307137,
        106.651646,
        True,
        None,
    ),
    (
        "Noble Padel",
        "Jalan M. Husni Thamrin, Pantai Indah Kapuk 2",
        -6.067729,
        106.701392,
        True,
        None,
    ),
    (
        "Off Court",
        "BSD Green Connector, BSD City",
        -6.308952,
        106.657980,
        True,
        None,
    ),
    (
        "Padel Hub",
        "Jalan Raya Cisauk, BSD City",
        -6.316343,
        106.652814,
        True,
        None,
    ),
    (
        "Padel Pro Satrio Club",
        "Jalan Karet Sawah, Jakarta Selatan",
        -6.219991,
        106.818547,
        True,
        (6, 24),
    ),
    (
        "Pop Padel",
        "Gang Bambu Kuning, Cilincing, Jakarta Utara",
        -6.160812,
        106.929802,
        True,
        None,
    ),
    (
        "Racket Kuningan",
        "Jalan Terusan Kuningan Hajjah R. Rasuna Said, Mampang Prapatan, Jakarta Selatan",
        -6.239226,
        106.826777,
        True,
        None,
    ),
    (
        "Republic Padel",
        "Jalan Nangka Raya, Jagakarsa, Jakarta Selatan",
        -6.304320,
        106.842268,
        True,
        None,
    ),
    (
        "Skoya Padel",
        "Jalan Damai Foresta, BSD City",
        -6.308208,
        106.655773,
        True,
        None,
    ),
    (
        "Smash Padel Simatupang",
        "Jalan Tahi Bonar Simatupang",
        -6.299667,
        106.834085,
        False,
        None,
    ),
    (
        "Solace Club",
        "Jalan Jenderal Gatot Subroto, Mampang Prapatan, Jakarta Selatan",
        -6.239183,
        106.828921,
        True,
        None,
    ),
    (
        "The Good Padel Club",
        "Jalan Sutera Tiara V, Alam Sutera, Pinang, Tangerang",
        -6.229573,
        106.655070,
        True,
        None,
    ),
    (
        "ZSC Padel",
        "Jalan Letnan Jenderal Suprapto, Cempaka Putih, Jakarta Pusat",
        -6.174191,
        106.858508,
        False,
        None,
    ),
    (
        "Zeno Padel Court",
        "Jalan Pisangan Barat I, Cireundeu, Ciputat Timur, Tangerang Selatan",
        -6.311359,
        106.761533,
        False,
        None,
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

# Which size each club gets. Not a guess about the world — it is a guess, and
# it says so: OpenStreetMap records a padel club's courts only for a few of
# them, and the manager is expected to correct the count.
VENUE_SIZE = {
    "Agora Padel": MID_VENUE,
    "Athletiqs Airdome": BIG_VENUE,
    "Booster Arena": MID_VENUE,
    "Commune Court": SMALL_VENUE,
    "Crown Padel": MID_VENUE,
    "Double Padel by Kadena": MID_VENUE,
    "Filari Sport Center": MID_VENUE,
    "Home Ground Kedoya": SMALL_VENUE,
    "Kula Courts": SMALL_VENUE,
    "Master Padel": MID_VENUE,
    "Matchaus Padel & Pickleball": MID_VENUE,
    "Metro Padel": MID_VENUE,
    "Noble Padel": MID_VENUE,
    "Off Court": SMALL_VENUE,
    "Padel Hub": MID_VENUE,
    "Padel Pro Satrio Club": BIG_VENUE,
    "Pop Padel": SMALL_VENUE,
    "Racket Kuningan": MID_VENUE,
    "Republic Padel": MID_VENUE,
    "Skoya Padel": SMALL_VENUE,
    "Smash Padel Simatupang": MID_VENUE,
    "Solace Club": MID_VENUE,
    "The Good Padel Club": MID_VENUE,
    "ZSC Padel": MID_VENUE,
    "Zeno Padel Court": SMALL_VENUE,
}

# Booking days from today. Short on purpose: slots are generated rows, and a
# week is enough to exercise next-week in the UI without the table growing
# forever on every seed run.
DAYS_AHEAD = 7
OPEN_HOUR = 8
CLOSE_HOUR = 22


def _tags_for(covered: bool, address: str) -> list[str]:
    """A set of tags, from what is actually known about the place.

    Whether the court is under a roof comes from how the club is mapped, not
    from its name. The rest are the words a padel club of this kind would
    carry — padel is booked by people who come with friends, in the evening,
    and for a match they want to play properly — and the manager is expected to
    correct them.
    """
    tags = {"indoors" if covered else "outdoors"}
    tags.add("classes")
    tags.add("family")
    if "Jakarta" in address:
        tags.add("night-owl")
    else:
        tags.add("event")
    return sorted(tags)


def main() -> None:
    db = SessionLocal()
    try:
        existing = set(db.scalars(select(Venue.name)).all())
        wanted = [v for v in VENUES if v[0] not in existing]
        if not wanted:
            print("already seeded")
            return

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
        # The two earliest slots *from today* and *at the venues just seeded* —
        # the earliest slots in the table could belong to a venue that was here
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
        print(f"seeded {len(venues)} venues, {len(courts)} courts")
        for venue in venues:
            print(f"  {venue.name} — {venue.address}")
    finally:
        db.close()


if __name__ == "__main__":
    main()