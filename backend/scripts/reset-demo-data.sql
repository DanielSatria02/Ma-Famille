-- Remove the clubs left over from an older seed.
--
-- The seed now holds two branches of Ma-Famille Premiere, one court each. A
-- database that was seeded before still has the old rows, and the foreign
-- keys do not cascade: a club cannot be deleted while a booking still points
-- at one of its courts. So the rows come out in order, children first.
--
-- This is not only tidying. A court left over from the older seed carries a
-- sport the API no longer accepts, and a listing that touches it answers 500
-- instead of a list — the club list, the facility list and the manager
-- dashboard all break on one row that should not be there.
--
-- The branches keep one court each. The extra courts are from the older,
-- larger seed, and their slots and bookings go with them.
--
-- Safe to run more than once.

BEGIN;

-- Payments point at bookings.
DELETE FROM payments
WHERE booking_id IN (
    SELECT b.id FROM bookings b
    JOIN slots s ON s.id = b.slot_id
    JOIN courts c ON c.id = s.court_id
    JOIN venues v ON v.id = c.venue_id
    WHERE v.name NOT IN (
        'Pondok Indah',
        'Lebak Bulus'
    )
);

-- Notifications point at bookings too.
DELETE FROM notifications
WHERE booking_id IN (
    SELECT b.id FROM bookings b
    JOIN slots s ON s.id = b.slot_id
    JOIN courts c ON c.id = s.court_id
    JOIN venues v ON v.id = c.venue_id
    WHERE v.name NOT IN (
        'Pondok Indah',
        'Lebak Bulus'
    )
);

DELETE FROM bookings
WHERE slot_id IN (
    SELECT s.id FROM slots s
    JOIN courts c ON c.id = s.court_id
    JOIN venues v ON v.id = c.venue_id
    WHERE v.name NOT IN (
        'Pondok Indah',
        'Lebak Bulus'
    )
);

DELETE FROM slots
WHERE court_id IN (
    SELECT c.id FROM courts c
    JOIN venues v ON v.id = c.venue_id
    WHERE v.name NOT IN (
        'Pondok Indah',
        'Lebak Bulus'
    )
);

DELETE FROM venue_closures
WHERE venue_id IN (
    SELECT id FROM venues
    WHERE name NOT IN (
        'Pondok Indah',
        'Lebak Bulus'
    )
);

DELETE FROM venue_hours
WHERE venue_id IN (
    SELECT id FROM venues
    WHERE name NOT IN (
        'Pondok Indah',
        'Lebak Bulus'
    )
);

DELETE FROM courts
WHERE venue_id IN (
    SELECT id FROM venues
    WHERE name NOT IN (
        'Pondok Indah',
        'Lebak Bulus'
    )
);

DELETE FROM venues
WHERE name NOT IN (
    'Pondok Indah',
    'Lebak Bulus'
);

-- The branches keep one court each: the oldest row with that name, so a
-- duplicate cannot leave the manager looking at two identical courts. The
-- slots, bookings, payments and notifications on the other courts go first,
-- because the foreign keys do not cascade.
DELETE FROM payments
WHERE booking_id IN (
    SELECT b.id FROM bookings b
    JOIN slots s ON s.id = b.slot_id
    WHERE s.court_id IN (
        SELECT c.id FROM courts c
        JOIN venues v ON v.id = c.venue_id
        WHERE v.name IN ('Pondok Indah', 'Lebak Bulus')
          AND c.id NOT IN (
              SELECT MIN(c2.id) FROM courts c2
              JOIN venues v2 ON v2.id = c2.venue_id
              WHERE v2.name = v.name AND c2.name = 'Lapangan Padel 1'
              GROUP BY v2.name
          )
    )
);

DELETE FROM notifications
WHERE booking_id IN (
    SELECT b.id FROM bookings b
    JOIN slots s ON s.id = b.slot_id
    WHERE s.court_id IN (
        SELECT c.id FROM courts c
        JOIN venues v ON v.id = c.venue_id
        WHERE v.name IN ('Pondok Indah', 'Lebak Bulus')
          AND c.id NOT IN (
              SELECT MIN(c2.id) FROM courts c2
              JOIN venues v2 ON v2.id = c2.venue_id
              WHERE v2.name = v.name AND c2.name = 'Lapangan Padel 1'
              GROUP BY v2.name
          )
    )
);

DELETE FROM bookings
WHERE slot_id IN (
    SELECT s.id FROM slots s
    WHERE s.court_id IN (
        SELECT c.id FROM courts c
        JOIN venues v ON v.id = c.venue_id
        WHERE v.name IN ('Pondok Indah', 'Lebak Bulus')
          AND c.id NOT IN (
              SELECT MIN(c2.id) FROM courts c2
              JOIN venues v2 ON v2.id = c2.venue_id
              WHERE v2.name = v.name AND c2.name = 'Lapangan Padel 1'
              GROUP BY v2.name
          )
    )
);

DELETE FROM slots
WHERE court_id IN (
    SELECT c.id FROM courts c
    JOIN venues v ON v.id = c.venue_id
    WHERE v.name IN ('Pondok Indah', 'Lebak Bulus')
      AND c.id NOT IN (
          SELECT MIN(c2.id) FROM courts c2
          JOIN venues v2 ON v2.id = c2.venue_id
          WHERE v2.name = v.name AND c2.name = 'Lapangan Padel 1'
          GROUP BY v2.name
      )
);

DELETE FROM courts
WHERE id NOT IN (
    -- One court per branch: the oldest row with that name in that branch.
    -- Scoping it to the branch matters — a single MIN across both branches
    -- would keep one court in total and delete the other.
    SELECT MIN(c2.id) FROM courts c2
    JOIN venues v2 ON v2.id = c2.venue_id
    WHERE v2.name IN ('Pondok Indah', 'Lebak Bulus')
      AND c2.name = 'Lapangan Padel 1'
    GROUP BY v2.name
);

COMMIT;

-- What is left.
SELECT v.name, c.name AS court, c.sport
FROM venues v
LEFT JOIN courts c ON c.venue_id = v.id
ORDER BY v.name, c.name;
