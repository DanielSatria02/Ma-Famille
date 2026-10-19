-- Remove the clubs left over from an older seed.
--
-- The seed now holds two branches of Ma-Famille Premiere. A database that was
-- seeded before still has the old rows, and the foreign keys do not cascade:
-- a club cannot be deleted while a booking still points at one of its courts.
-- So the rows come out in order, children first.
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

COMMIT;

-- What is left.
SELECT name, address FROM venues ORDER BY name;
