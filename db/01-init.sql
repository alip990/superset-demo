-- Metadata DB for Superset + a separate mock business DB
CREATE DATABASE superset;
CREATE DATABASE demo;
\connect demo

-- Gregorian -> Jalali (Persian calendar) conversion, returns 'YYYY-MM-DD'
CREATE OR REPLACE FUNCTION to_jalali(d date) RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  gy int := extract(year from d); gm int := extract(month from d); gd int := extract(day from d);
  g_d_m int[] := ARRAY[0,31,59,90,120,151,181,212,243,273,304,334];
  gy2 int; days int; jy int; jm int; jd int;
BEGIN
  gy2 := CASE WHEN gm > 2 THEN gy + 1 ELSE gy END;
  days := 355666 + (365 * gy) + ((gy2 + 3) / 4) - ((gy2 + 99) / 100) + ((gy2 + 399) / 400) + gd + g_d_m[gm];
  jy := -1595 + (33 * (days / 12053));
  days := days % 12053;
  jy := jy + 4 * (days / 1461);
  days := days % 1461;
  IF days > 365 THEN jy := jy + ((days - 1) / 365); days := (days - 1) % 365; END IF;
  IF days < 186 THEN jm := 1 + (days / 31); jd := 1 + (days % 31);
  ELSE jm := 7 + ((days - 186) / 30); jd := 1 + ((days - 186) % 30); END IF;
  RETURN lpad(jy::text,4,'0') || '-' || lpad(jm::text,2,'0') || '-' || lpad(jd::text,2,'0');
END $$;

CREATE TABLE provinces (
  id serial PRIMARY KEY, name_fa text, name_en text, region text, lat float8, lon float8
);
INSERT INTO provinces (name_fa, name_en, region, lat, lon) VALUES
 ('تهران','Tehran','north',35.6892,51.3890), ('اصفهان','Isfahan','center',32.6546,51.6680),
 ('فارس','Fars','south',29.5918,52.5837), ('خراسان رضوی','Razavi Khorasan','east',36.2605,59.6168),
 ('آذربایجان شرقی','East Azerbaijan','west',38.0962,46.2738), ('خوزستان','Khuzestan','south',31.3183,48.6706),
 ('گیلان','Gilan','north',37.2808,49.5832), ('مازندران','Mazandaran','north',36.5659,53.0586),
 ('کرمان','Kerman','east',30.2839,57.0834), ('هرمزگان','Hormozgan','south',27.1832,56.2666),
 ('یزد','Yazd','center',31.8974,54.3569), ('کرمانشاه','Kermanshah','west',34.3142,47.0650),
 ('سیستان و بلوچستان','Sistan-Baluchestan','east',29.4963,60.8629), ('قم','Qom','center',34.6399,50.8759),
 ('البرز','Alborz','north',35.8400,50.9391), ('آذربایجان غربی','West Azerbaijan','west',37.5527,45.0761);

CREATE TABLE branches (
  id serial PRIMARY KEY, province_id int REFERENCES provinces(id), name_fa text, lat float8, lon float8
);
-- 6 branches around each province capital
INSERT INTO branches (province_id, name_fa, lat, lon)
SELECT p.id, 'شعبه ' || g || ' ' || p.name_fa,
       p.lat + (random() - 0.5) * 0.6, p.lon + (random() - 0.5) * 0.6
FROM provinces p CROSS JOIN generate_series(1, 6) g;

CREATE TABLE sales (
  id bigserial PRIMARY KEY,
  sale_date date NOT NULL,
  jalali_date text, jalali_month text, jalali_year int,
  branch_id int REFERENCES branches(id),
  branch_name text, province_fa text, province_en text, region text,
  lat float8, lon float8,
  category text, amount numeric(14,0), qty int
);
INSERT INTO sales (sale_date, branch_id, branch_name, province_fa, province_en, region, lat, lon, category, amount, qty)
SELECT d::date, b.id, b.name_fa, p.name_fa, p.name_en, p.region, b.lat, b.lon,
       (ARRAY['پوشاک','مواد غذایی','لوازم خانگی','دیجیتال','کتاب'])[1 + floor(random()*5)::int],
       round((random() * 90 + 10) * 100000), 1 + floor(random()*20)::int
FROM generate_series(current_date - interval '540 days', current_date, interval '1 day') d
JOIN branches b ON true JOIN provinces p ON p.id = b.province_id
WHERE random() < 0.35;
UPDATE sales SET jalali_date = to_jalali(sale_date),
                 jalali_month = substr(to_jalali(sale_date), 1, 7),
                 jalali_year = substr(to_jalali(sale_date), 1, 4)::int;
CREATE INDEX ON sales (sale_date); CREATE INDEX ON sales (region);

-- Data-access mapping: which app user may see which region (used by RLS via Jinja)
CREATE TABLE user_access (username text, region text);
INSERT INTO user_access VALUES ('ali_north','north'), ('sara_south','south'), ('sara_south','center'),
  ('manager','north'), ('manager','south'), ('manager','center'), ('manager','east'), ('manager','west');

-- read-only user Superset uses to query the business DB
CREATE ROLE demo_reader LOGIN PASSWORD 'demo_reader';
GRANT CONNECT ON DATABASE demo TO demo_reader;
GRANT USAGE ON SCHEMA public TO demo_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO demo_reader;
