CREATE TABLE IF NOT EXISTS calendar_events (
  id integer PRIMARY KEY, occurred_at timestamp NOT NULL,
  amount integer NOT NULL, tenant_id integer NOT NULL
);
-- UTC storage. Tehran Nowruz 1404 starts at 2025-03-20 20:30 UTC.
INSERT INTO calendar_events VALUES
  (1, '2025-03-20 20:29:59', 1, 1),
  (2, '2025-03-20 20:30:00', 10, 1),
  (3, '2025-03-21 20:29:59', 100, 1),
  (4, '2025-03-21 20:30:00', 1000, 1),
  (5, '2025-03-21 20:30:01', 10000, 1),
  (6, '2025-03-20 21:00:00', 99999, 2)
ON CONFLICT (id) DO NOTHING;
SELECT jalali.build_dim_date(1398, 1410);
