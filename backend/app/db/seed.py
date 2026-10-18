"""Demo seed: real Indonesian venues, their courts, slots and two bookings.

Every venue here is a place that exists — the name, the street and the
coordinates come out of that place's OpenStreetMap record, so the map has
something honest to draw and a booking has a real address to send someone to.
The facilities inside each venue are invented, which they have to be: nobody
publishes a list of which court is number four.

Idempotent — exits quietly when the demo venues already exist. Rerun it after a
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

# name, street address, latitude, longitude
#
# Coordinates are OpenStreetMap's, rounded to six decimals (about 10cm). Each
# one was read off the OSM record for that place, not typed in from memory: a
# pin in the wrong district is worse than no pin, because it looks right.
VENUES = [
    (
        "Istana Olahraga Gelora Bung Karno",
        "Jalan Plaza Selatan, Gelora, Tanah Abang, Jakarta Pusat",
        -6.220338,
        106.805750,
    ),
    (
        "Indonesia Arena",
        "Jalan Gerbang Pemuda, Gelora, Tanah Abang, Jakarta Pusat",
        -6.214829,
        106.800522,
    ),
    (
        "GOR Velodrome Rawamangun",
        "Jalan Pemuda, Rawamangun, Pulo Gadung, Jakarta Timur",
        -6.193181,
        106.889096,
    ),
    (
        "Gelanggang Olahraga Sunter",
        "Jalan Taman Tirta Sunter 1, Sunter Jaya, Tanjung Priok, Jakarta Utara",
        -6.146852,
        106.875605,
    ),
    (
        "Stadion Tugu",
        "Jalan Jamrud III, Tugu Selatan, Koja, Jakarta Utara",
        -6.136877,
        106.913396,
    ),
    (
        "Cempaka Putih Sport Center Arcici",
        "Jalan Cempaka Putih Barat 26, Cempaka Putih, Jakarta Pusat",
        -6.184235,
        106.868883,
    ),
    (
        "GOR Kemayoran",
        "Jalan Serdang Baru, Kemayoran, Jakarta Pusat",
        -6.157083,
        106.864889,
    ),
    (
        "Stadion Siliwangi",
        "Jalan Lombok, Merdeka, Sumur Bandung, Kota Bandung",
        -6.910328,
        107.619556,
    ),
    (
        "GOR Cisitu",
        "Jalan Cisitu Indah 5, Dago, Coblong, Kota Bandung",
        -6.875402,
        107.613306,
    ),
    (
        "Gelora Bandung Lautan Api",
        "Jalan Pintu Masuk GBLA, Rancanumpang, Gedebage, Kota Bandung",
        -6.956628,
        107.712131,
    ),
    (
        "Kompleks Stadion Mandala Krida",
        "Jalan Kenari, Semaki, Umbulharjo, Kota Yogyakarta",
        -7.796016,
        110.384101,
    ),
    (
        "Stadion Kridosono",
        "Jalan Yos Sudarso, Kotabaru, Gondokusuman, Kota Yogyakarta",
        -7.787698,
        110.374298,
    ),
    (
        "Gelora 10 November",
        "Jalan Tambaksari I, Ploso, Tambaksari, Surabaya",
        -7.251971,
        112.756162,
    ),
    (
        "Stadion Gelora Bung Tomo",
        "Jalan TPA Benowo, Pakal, Surabaya",
        -7.223065,
        112.622833,
    ),
    (
        "DBL Arena",
        "Jalan Ahmad Yani, Ketintang, Gayungan, Surabaya",
        -7.320451,
        112.732202,
    ),
    (
        "GOR Shima",
        "Jalan Jaten Gede Timur II, Pedurungan Tengah, Semarang",
        -6.999153,
        110.473703,
    ),
    (
        "Stadion UNDIP",
        "Jalan Profesor Soedarto, Bulusan, Tembalang, Semarang",
        -7.054688,
        110.446562,
    ),
    (
        "Stadion Teladan",
        "Jalan Stadion Teladan, Teladan Barat, Medan Kota, Medan",
        3.564640,
        98.696084,
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
FACILITIES = [
    ("Lapangan Futsal Utama", "futsal", "court", 120000, 150000),
    ("Lapangan Futsal 2", "futsal", "court", 120000, 150000),
    ("Lapangan Badminton 1", "badminton", "court", 60000, 90000),
    ("Lapangan Badminton 2", "badminton", "court", 60000, 90000),
    ("Lapangan Badminton 3", "badminton", "court", 55000, 85000),
]

# Facilities per venue type. A university stadium has one pitch and no five
# badminton halls; a neighbourhoodsports hall is the reverse. Slicing the same
# list for every venue made the home page look like a template.
SMALL_VENUE = [FACILITIES[2], FACILITIES[3]]
MID_VENUE = FACILITIES[:4]
BIG_VENUE = FACILITIES

VENUE_SIZE = {
    "Istana Olahraga Gelora Bung Karno": MID_VENUE,
    "Indonesia Arena": BIG_VENUE,
    "GOR Velodrome Rawamangun": MID_VENUE,
    "Gelanggang Olahraga Sunter": MID_VENUE,
    "Stadion Tugu": SMALL_VENUE,
    "Cempaka Putih Sport Center Arcici": MID_VENUE,
    "GOR Kemayoran": SMALL_VENUE,
    "Stadion Siliwangi": MID_VENUE,
    "GOR Cisitu": SMALL_VENUE,
    "Gelora Bandung Lautan Api": BIG_VENUE,
    "Kompleks Stadion Mandala Krida": MID_VENUE,
    "Stadion Kridosono": MID_VENUE,
    "Gelora 10 November": MID_VENUE,
    "Stadion Gelora Bung Tomo": SMALL_VENUE,
    "DBL Arena": MID_VENUE,
    "GOR Shima": SMALL_VENUE,
    "Stadion UNDIP": MID_VENUE,
    "Stadion Teladan": SMALL_VENUE,
}

# Booking days from today. Short on purpose: slots are generated rows, and a
# week is enough to exercise next-week in the UI without the table growing
# forever on every seed run.
DAYS_AHEAD = 7
OPEN_HOUR = 8
CLOSE_HOUR = 22


def _tags_for(name: str, address: str) -> list[str]:
    """A plausible set of tags, from what is actually known about the place.

    Nothing here claims a fact about the venue — whether a pitch is roofed is
    not in OpenStreetMap. So these are the default marketing words a venue of
    this kind would carry, and the manager is expected to correct them.
    """
    tags = {"indoors" if "Gelora" in name or "Istana" in name else "outdoors"}
    if "Stadion" in name:
        tags.add("competitive")
    else:
        tags.add("classes")
        tags.add("family")
    if "Jakarta" in address or "Senayan" in address:
        tags.add("night-owl")
    if len(tags) < 3:
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
        for name, address, lat, lng in wanted:
            venue = Venue(
                name=name,
                address=address,
                tags=_tags_for(name, address),
                lat=lat,
                lng=lng,
            )
            db.add(venue)
            db.flush()
            venues.append(venue)
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
                for hour in range(OPEN_HOUR, CLOSE_HOUR):
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
        # The two earliest slots *from today*, not the two oldest rows — those
        # would be last week's, which reads as a booking nobody can reach.
        todays_slots = db.scalars(
            select(Slot)
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