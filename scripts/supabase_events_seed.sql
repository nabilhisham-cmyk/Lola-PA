-- ─────────────────────────────────────────────────────────────────────
-- Lola PA — El Gouna seed data
--
-- Researched from elgouna.com, the festival listings, Fly Events and press
-- coverage. HONEST SCOPE: this seeds what is publicly documented. Capacities,
-- curfews, power notes and contact details are intentionally LEFT NULL, because
-- I do not know them and a made-up capacity is worse than a blank one. Hisham
-- fills those in, or Lola asks him.
--
-- Safe to re-run: every insert is ON CONFLICT (name) DO NOTHING, so a later
-- correction is not overwritten and a repeat run is a no-op.
-- ─────────────────────────────────────────────────────────────────────

-- ── Venues ───────────────────────────────────────────────────────────
INSERT INTO venues (name, zone, kind, weather_exposed, notes) VALUES
 ('Abu Tig Marina',              'Marina',      'marina',      TRUE,  'Main marina. Marina Street Festival runs weekly in summer in front of Captains Inn. Boat Show venue (New Marina).'),
 ('New Marina',                  'Marina',      'marina',      TRUE,  'El Gouna Boat Show venue.'),
 ('Downtown El Gouna',           'Downtown',    'other',       TRUE,  'Restaurants, galleries, small performances.'),
 ('Kafr El Gouna',               'Kafr',        'other',       TRUE,  'Historic quarter, arts and small venues.'),
 ('Tamr Henna Square',           'Downtown',    'square',      TRUE,  'Public gatherings, markets, performances.'),
 ('El Gouna Conference and Culture Center', 'Downtown', 'indoor_hall', FALSE, 'Conferences, GFF screenings and panels, corporate events.'),
 ('Sea Cinema',                  'Downtown',    'indoor_hall', FALSE, 'Opened for the inaugural El Gouna Film Festival. Managed by -Productions (per public listings).'),
 ('Sliders Cable Park',          'Other',       'other',       TRUE,  'Cable wakeboarding. Wakemania venue. Water-based, so safety cover applies.'),
 ('El Gouna Golf Club',          'Other',       'club',        TRUE,  'Golf course and clubhouse. Federation Cup area.'),
 ('Mangroovy Beach',             'Beach',       'beach',       TRUE,  'Kitesurfing and beach activity. Wind-exposed.'),
 ('Buzzha Beach',               'Beach',       'beach',       TRUE,  'Northern Mangroovy. Kite centre. Wind-exposed.'),
 ('Cook''s Club El Gouna',       'Hotel',       'hotel',       TRUE,  'Hotel programming: daily pool parties, boat parties, Egyptian BBQ nights, seafood nights.'),
 ('Casa Cook El Gouna',          'Hotel',       'hotel',       TRUE,  'Hotel programming: Bedouin parties, Friday BBQ nights, seafood buffet.'),
 ('Steigenberger Golf Resort El Gouna', 'Hotel', 'hotel',      TRUE,  'Hotel programming: The Golden Hour.'),
 ('Sheraton Miramar Resort El Gouna',   'Hotel', 'hotel',      TRUE,  'Hotel programming: seafood paradise buffet.'),
 ('Mövenpick Resort El Gouna',   'Hotel',       'hotel',       TRUE,  'Hotel programming.'),
 ('Three Corners Ocean View',    'Hotel',       'hotel',       TRUE,  'Hotel programming: Sunday breakfast at Oceana.'),
 ('Ancient Sands Golf Resort',   'Hotel',       'hotel',       TRUE,  'Hotel programming: Oriental Night.'),
 ('The Chedi El Gouna',          'Hotel',       'hotel',       TRUE,  'Hotel programming: evening BBQ.'),
 ('Sultan Bey Hotel',            'Hotel',       'hotel',       TRUE,  'Hotel programming: BBQ with jazz nights.'),
 ('Ali Pasha Hotel',             'Hotel',       'hotel',       TRUE,  'Hotel programming: live singers at Tandoor restaurant.'),
 ('El Gouna Tennis Club',        'Other',       'club',        TRUE,  'Tennis, coaching and social programming.'),
 ('El Gouna lagoon and islands', 'Other',       'other',       TRUE,  'Private and branded activations. Water access only.')
ON CONFLICT (name) DO NOTHING;

-- ── Recurring series (the programming that never shows up as a "new event") ──
INSERT INTO event_series
  (name, event_type, venue_text, recurrence, weekday, starts_on, ends_on,
   weather_dependency, notes)
VALUES
 ('Marina Street Festival', 'activation', 'Abu Tig Marina', 'weekly', 6,
  NULL, NULL, 'rain_fatal',
  'Weekly through summer, live music and shows in front of Captains Inn. Weekday recorded as Saturday; CONFIRM with Hisham, as the source did not state the day.'),
 ('Cook''s Club Daily Pool Party', 'hotel_programming', 'Cook''s Club El Gouna', 'daily',
  NULL, NULL, NULL, 'rain_fatal', 'Daily hotel programming.'),
 ('Cook''s Club Boat Party', 'hotel_programming', 'Cook''s Club El Gouna', 'weekly', 5,
  NULL, NULL, 'rain_fatal', 'Listed as Fridays. Weekly boat party.'),
 ('Casa Cook Friday BBQ Night', 'hotel_programming', 'Casa Cook El Gouna', 'weekly', 5,
  NULL, NULL, 'rain_fatal', 'Friday BBQ night.'),
 ('Casa Cook Bedouin Party', 'hotel_programming', 'Casa Cook El Gouna', 'weekly', 6,
  NULL, NULL, 'rain_fatal', 'Bedouin party. Weekday recorded as Saturday; CONFIRM.'),
 ('Casa Cook Seafood Buffet', 'hotel_programming', 'Casa Cook El Gouna', 'weekly', 7,
  NULL, NULL, 'none', 'Sunday seafood buffet. Weekday recorded as Sunday; CONFIRM.'),
 ('Ancient Sands Oriental Night', 'hotel_programming', 'Ancient Sands Golf Resort', 'weekly', 6,
  NULL, NULL, 'rain_fatal', 'Oriental Night event. Weekday recorded as Saturday; CONFIRM.'),
 ('Three Corners Sunday Breakfast', 'hotel_programming', 'Three Corners Ocean View', 'weekly', 7,
  NULL, NULL, 'rain_fatal', 'Sunday breakfast at Oceana Restaurant.'),
 ('Sultan Bey BBQ Jazzy Nights', 'hotel_programming', 'Sultan Bey Hotel', 'weekly', 7,
  NULL, NULL, 'rain_fatal', 'BBQ with jazz. Weekday recorded as Sunday; CONFIRM.'),
 ('Cook''s Club Egyptian BBQ Night', 'hotel_programming', 'Cook''s Club El Gouna', 'weekly', 1,
  NULL, NULL, 'rain_fatal', 'Egyptian BBQ night. Weekday recorded as Monday; CONFIRM.'),
 ('Sheraton Miramar Seafood Buffet', 'hotel_programming', 'Sheraton Miramar Resort El Gouna', 'weekly', 4,
  NULL, NULL, 'none', 'Seafood paradise buffet. Weekday recorded as Thursday; CONFIRM.'),
 ('Ali Pasha Live Singers at Tandoor', 'hotel_programming', 'Ali Pasha Hotel', 'weekly', 1,
  NULL, NULL, 'none', 'Live singers at Tandoor Restaurant. Weekday recorded as Monday; CONFIRM.'),
 ('El Gouna Water Sports Festival (GWSF)', 'sporting', 'Abu Tig Marina', 'seasonal',
  NULL, NULL, NULL, 'wind_required',
  'Annual watersports festival, organised by Fly Events. Held September. 2026 Vol. 6 ran 16 to 26 Sep. Contains Kitemania, Windmania, Wakemania, Kayak and SUPball. Cash prizes (300k EGP pool in 2026). Athletes register in advance; the rider list is a live dependency.'),
 ('Kitemania', 'sporting', 'Mangroovy Beach', 'seasonal', NULL, NULL, NULL, 'wind_required',
  'Annual kitesurfing competition, all riding levels. Within GWSF. Wind is the whole event: no wind, no competition.'),
 ('Windmania', 'sporting', 'Mangroovy Beach', 'seasonal', NULL, NULL, NULL, 'wind_required',
  'Windsurfing competition, within GWSF.'),
 ('Wakemania', 'sporting', 'Sliders Cable Park', 'seasonal', NULL, NULL, NULL, 'none',
  'Cable wakeboarding competition at Sliders, within GWSF. 2026 edition 25 Sep. Cable-driven, so not wind dependent like the kite disciplines.')
ON CONFLICT (name) DO NOTHING;

-- ── Signature events still to come in 2026 ───────────────────────────
-- Recorded as events, not series, because they are one-off annual editions.
--
-- NOTE on idempotency: `events` has NO unique constraint on `name` (deliberately,
-- because the same name can legitimately recur in different years), so
-- `ON CONFLICT DO NOTHING` has no conflict target here and silently inserted a
-- duplicate row on every re-run. Caught by applying this seed twice and finding
-- 8 rows where there should have been 4. The guarded WHERE NOT EXISTS below is
-- what makes it genuinely re-runnable.
INSERT INTO events
  (name, event_type, status, starts_on, ends_on, venue_text,
   weather_dependency, description, source)
SELECT * FROM (VALUES
 ('El Gouna Boat Show 2026', 'activation', 'proposed', DATE '2026-10-08', DATE '2026-10-08',
  'New Marina', 'rain_fatal',
  'Red Sea marine event at the New Marina. Annual. Dates from the town''s own events listing.',
  'seed'),
 ('El Gouna Film Festival 2026 (9th Edition)', 'festival', 'confirmed',
  DATE '2026-10-15', DATE '2026-10-23', 'El Gouna Conference and Culture Center', 'none',
  'The town''s flagship event. Nine days, multiple venues, international talent and press. Runs on Eventival, the festival''s own management system. Founded 2017 by Naguib Sawiris with Bushra Rozza and Amr Mansi (CEO of I-Events).',
  'seed'),
 ('The El Gouna Federation Cup 2026', 'sporting', 'proposed',
  DATE '2026-11-04', DATE '2026-11-04', 'El Gouna Golf Club', 'wind_fatal',
  'Annual sporting event. Dates from the town''s own events listing.',
  'seed'),
 ('El Gouna Half Marathon 2026', 'sporting', 'proposed',
  DATE '2026-11-21', DATE '2026-11-21', 'Downtown El Gouna', 'rain_risk',
  'Annual half marathon. Road closures, medical cover and water stations are the core logistics.',
  'seed')
) AS v(name, event_type, status, starts_on, ends_on, venue_text,
       weather_dependency, description, source)
WHERE NOT EXISTS (
    SELECT 1 FROM events e WHERE e.name = v.name AND e.starts_on = v.starts_on
);

-- ── Hisham's four key events (named by him directly) ─────────────────
-- These are the ones he cares about most. Health-checked against the real
-- calendar: Sandbox May, Kings Polo and Squash April, GFF October.
INSERT INTO events
  (name, event_type, status, starts_on, ends_on, venue_text,
   weather_dependency, description, source)
SELECT * FROM (VALUES
 ('Sandbox Festival 2026', 'festival', 'confirmed',
  DATE '2026-05-07', DATE '2026-05-09', 'El Gouna beach', 'rain_fatal',
  'KEY EVENT. Multi-stage electronic music festival, three days, broad international lineup, 21+ beach setting. 12th edition. Organiser is external; El Gouna supplies the town.',
  'seed'),
 ('Kings Polo 2026 (Beach Polo Silver Cup)', 'sporting', 'proposed',
  DATE '2026-04-10', DATE '2026-04-10', 'El Gouna beach', 'wind_fatal',
  'KEY EVENT. El Gouna Beach Polo Kings Polo Silver Cup, the biggest arena polo in Egypt. Six teams with well-known Argentinian professionals. First played 2017, paused over COVID. Wind is a genuine risk for arena polo.',
  'seed'),
 ('El Gouna International Squash Open 2026', 'sporting', 'confirmed',
  DATE '2026-04-04', DATE '2026-04-10', 'El Gouna Conference and Culture Center', 'none',
  'KEY EVENT. Annual men''s and women''s PSA World Series squash tournament, the top tier of professional squash. Indoor, so weather-independent.',
  'seed')
) AS v(name, event_type, status, starts_on, ends_on, venue_text,
       weather_dependency, description, source)
WHERE NOT EXISTS (
    SELECT 1 FROM events e WHERE e.name = v.name AND e.starts_on = v.starts_on
);
