-- Runs once on first start of the db container (empty volume): installs the
-- Jalali calendar library into the demo database and fills the calendar table.
-- db/jalali.sql itself picks no database, so it can also be applied to any other
-- one by hand (see its header).
\set ON_ERROR_STOP on
\connect demo
\i /opt/jalali/jalali.sql
SELECT jalali.build_dim_date(1390, 1420) AS jalali_dim_date_days;
