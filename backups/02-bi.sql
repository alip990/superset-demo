-- BI layer for the restored beta backup: schema "bi" in CrimeManagementDb.
-- Flattens the speeding records (CR.DeviceCrime) and joins the company tree and
-- vehicles from the DeviceManagement DB (via postgres_fdw) so Superset can chart
-- everything from one database. Superset reads it as the read-only bi_reader.
-- Runs automatically after restore.sh on a fresh backup-db volume; to re-run by hand:
--   docker compose exec -T backup-db psql -U postgres < backups/02-bi.sql
\set ON_ERROR_STOP on
\connect "CrimeManagementDb"

DROP SCHEMA IF EXISTS bi CASCADE;
DROP SCHEMA IF EXISTS dm_src CASCADE;
DROP SERVER IF EXISTS device_mgmt CASCADE;
DROP SCHEMA IF EXISTS um_src CASCADE;
DROP SERVER IF EXISTS user_mgmt CASCADE;

-- ---------- DeviceManagement tables as foreign tables ----------
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
CREATE SERVER device_mgmt FOREIGN DATA WRAPPER postgres_fdw OPTIONS (dbname 'DeviceManagement');
CREATE USER MAPPING FOR postgres SERVER device_mgmt OPTIONS (user 'postgres');
CREATE SCHEMA dm_src;
IMPORT FOREIGN SCHEMA "DM" LIMIT TO ("Company", "Vehicle", "VehicleModel", "VehicleUsage", "Plate")
  FROM SERVER device_mgmt INTO dm_src;

CREATE SCHEMA bi;

CREATE FUNCTION bi.to_jalali(d date) RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
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

-- ---------- real application users and companies stay in UserManagementDb ----------
CREATE SERVER user_mgmt FOREIGN DATA WRAPPER postgres_fdw OPTIONS (dbname 'UserManagementDb');
CREATE USER MAPPING FOR postgres SERVER user_mgmt OPTIONS (user 'postgres');
CREATE SCHEMA um_src;
-- Company and user rows stay in the 1 May backup (UserManagementDb). These are foreign tables, not copies.
IMPORT FOREIGN SCHEMA um LIMIT TO ("User", "UserAttribute", "Company") FROM SERVER user_mgmt INTO um_src;

-- ancestor includes self, so a user of a company also sees that company
CREATE VIEW bi.company_closure AS
WITH RECURSIVE t AS (
  SELECT "Id" AS ancestor_id, "Id" AS descendant_id FROM um_src."Company" WHERE NOT "Deleted"
  UNION ALL
  SELECT t.ancestor_id, c."Id"
  FROM um_src."Company" c
  JOIN t ON c."ParentId" = t.descendant_id
  WHERE NOT c."Deleted"
) SELECT * FROM t;

-- ---------- vehicles, one per device ----------
-- NB: CR.DeviceCrime.DeviceId is always DM.Device.Id + 1 in the source data.
CREATE TABLE bi.vehicle AS
SELECT DISTINCT ON (v."DeviceId")
       v."DeviceId" + 1 AS crime_device_id,
       p."NumberFirstSection" || ' ' || p."AlphabeticName" || ' ' || p."NumberLastSection"
         || ' - ایران ' || p."CityCodeInput" AS plate,
       coalesce(trim(trailing '_' FROM m."Title"), 'نامشخص') AS vehicle_model,
       coalesce(u."Title", 'نامشخص') AS vehicle_usage
FROM dm_src."Vehicle" v
LEFT JOIN dm_src."Plate" p ON p."Id" = v."PlateId"
LEFT JOIN dm_src."VehicleModel" m ON m."Id" = v."VehicleModelId"
LEFT JOIN dm_src."VehicleUsage" u ON u."Id" = v."VehicleUsageId"
ORDER BY v."DeviceId", v."Deleted", v."CreationDate" DESC;
ALTER TABLE bi.vehicle ADD PRIMARY KEY (crime_device_id);

-- ---------- one row per speed check (fact table) ----------
CREATE TABLE bi.violation AS
WITH base AS (
  SELECT d.*, (d."OccouredDate" AT TIME ZONE 'Asia/Tehran') AS local_ts FROM "CR"."DeviceCrime" d
  WHERE NOT d."Deleted"
)
SELECT b."Id" AS id,
       b.local_ts AS occurred_at,
       b.local_ts::date AS occurred_date,
       bi.to_jalali(b.local_ts::date) AS jalali_date,
       substr(bi.to_jalali(b.local_ts::date), 1, 7) AS jalali_month,
       extract(hour FROM b.local_ts)::int AS hour_of_day,
       -- isodow 1 = Monday; the number prefix sorts the week Saturday-first
       (ARRAY['۲ دوشنبه','۳ سه‌شنبه','۴ چهارشنبه','۵ پنجشنبه','۶ جمعه','۰ شنبه','۱ یکشنبه'])
         [extract(isodow FROM b.local_ts)::int] AS weekday,
       b."ProvinceName" AS province,
       c."Id" AS company_id, c."Title" AS company, pc."Title" AS parent_company,
       CASE b."CrimeStatus" WHEN 1002002 THEN 'دارای تخلف' WHEN 1002003 THEN 'لیست سیاه' ELSE 'بدون خلافی' END AS status,
       (b."CrimeStatus" <> 1002001)::int AS is_violation,
       coalesce(nullif(trim(b."CrimeLocationTitle"), ''), 'نامشخص') AS location,
       b."Lat" AS lat, b."Lon" AS lon,
       -- ~100 m grid so map charts can aggregate in SQL instead of shipping 900k points
       round(b."Lat"::numeric, 3)::float8 AS lat_grid, round(b."Lon"::numeric, 3)::float8 AS lon_grid,
       b."DeviceId" AS device_id,
       b."DriverId" AS driver_id, b."DriverFullName" AS driver_name,
       coalesce(v.plate, b."NumberFirstSection" || ' ' || b."AlphabeticName" || ' ' || b."NumberLastSection"
         || ' - ایران ' || b."CityCodeInput") AS plate,
       coalesce(v.vehicle_model, 'نامشخص') AS vehicle_model,
       coalesce(v.vehicle_usage, 'نامشخص') AS vehicle_usage
FROM base b
LEFT JOIN um_src."Company" c
  ON NOT c."Deleted"
 AND ((b."ProvinceName" = 'تهران' AND c."Title" LIKE '%تهران%')
   OR (b."ProvinceName" = 'قم' AND c."Title" LIKE '%قم%'))
LEFT JOIN um_src."Company" pc ON pc."Id" = c."ParentId"
LEFT JOIN bi.vehicle v ON v.crime_device_id = b."DeviceId";

ALTER TABLE bi.violation ADD PRIMARY KEY (id);
CREATE INDEX ON bi.violation (occurred_at);
CREATE INDEX ON bi.violation (company_id);
ANALYZE bi.violation;

-- ---------- read-only role for Superset ----------
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bi_reader') THEN
    CREATE ROLE bi_reader LOGIN PASSWORD 'bi_reader';
  END IF;
END $$;
GRANT CONNECT ON DATABASE "CrimeManagementDb" TO bi_reader;
GRANT USAGE ON SCHEMA bi, um_src, dm_src TO bi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA bi, um_src, dm_src TO bi_reader;
GRANT EXECUTE ON FUNCTION bi.to_jalali(date) TO bi_reader;
CREATE USER MAPPING FOR bi_reader SERVER user_mgmt OPTIONS (user 'postgres', password_required 'false');
CREATE USER MAPPING FOR bi_reader SERVER device_mgmt OPTIONS (user 'postgres', password_required 'false');
