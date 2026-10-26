# Superset with the vehicle backup

| | |
|---|---|
| Superset | http://localhost:8088 (`admin` / `admin`) |
| Host app | http://localhost:8090 |
| Vehicle backup | `127.0.0.1:5441`, database `CrimeManagementDb` |

Open the host app to pick a user from `um."User"` and a company from `um."Company"`. Those tables stay in the 1 May backup. The guest token lists that company and every company under it. `traffic-fa-embedded` keeps only those rows.

`traffic-fa` is the same charts for a direct Superset login. A login whose username matches `um."User"."UserName"` sees that user's company subtree.

## Jalali dates

The image installs [superset-jalali](https://github.com/alip990/superset-jalali), pinned by
`SUPERSET_JALALI_REF` in `superset/Dockerfile` to
`50a28279a604abad5cfb8edddad12747b17c9260`. A Node 22 stage builds its frontend;
a Python 3.11 stage builds the wheel and checks that its manifest and named JS bundle
are included. The final Superset 6.1.0 stage installs that wheel. Once the package
is published on PyPI, replace the two build stages with a pinned package install.

Keep these as the **last two lines** of `superset/superset_config.py` so the plugin
merges the existing feature flags and `get_guest_user_attribute` Jinja helper:

```python
from superset_jalali import init_jalali
init_jalali(globals())
```

`JALALI = {"sql_min_year": 1400, "sql_max_year": 1410}` limits the SQL calendar join
for the backup's 1403–1404 data. Dates outside this window have NULL display columns.
The picker has its own wider calendar. `TZ=Asia/Tehran` keeps rolling presets on
Tehran's server date.

The direct-login dashboard uses the **physical** dataset `bi.violation`. Bootstrap
adds the plugin's Jalali calculated columns to it on `occurred_at`:

```bash
superset jalali add-columns --dataset <id of bi.violation> --column occurred_at
```

Each column is one expression such as `{{ jalali('occurred_at', 'month_label') }}`;
no SQL is needed and the column names are the same as before (`jalali_*`).
`occurred_at` stays the dataset's temporal default column.

The embedded dashboard keeps the **virtual** dataset `violation_scoped`, because the
guest's company list is applied in its SQL:

```sql
SELECT v.*, {{ jalali_columns('v.occurred_at') }}
FROM bi.violation v
{{ jalali_join('v.occurred_at') }}
WHERE 1=1 ... -- get_guest_user_attribute('allowed_companies')
```

`occurred_at` is already Tehran local time without a timezone. The scoped dataset
adds the existing guest company list with `get_guest_user_attribute`, `where_in`,
and an empty-list condition that returns no rows. Its cache keys include that list.

The macros provide `jalali_year`, `jalali_month_num`, `jalali_day`, `jalali_date`
(`1403/07/18`), `jalali_date_int`, `jalali_month` (`1403-07`), `jalali_month_name`,
`jalali_month_label`, `jalali_season`, `jalali_season_key`, `jalali_weekday`,
`jalali_weekday_num` (Saturday = 0), and `jalali_week_start` (Gregorian Saturday).
Sort weekday labels by `jalali_weekday_num`. The BI table stores only Gregorian dates.

The «تاریخ» Time range filter in both dashboards uses the Jalali calendar, including
inside the embedded app. Its end date is inclusive: 1404/01/01–1404/01/31 filters
`occurred_at >= '2025-03-21' AND occurred_at < '2025-04-21'`.
**Every traffic chart, including deck.gl maps, must keep the `occurred_at`
`TEMPORAL_RANGE` time pill with comparator `No filter`**, and `occurred_at` must
remain the dataset's temporal default column. The date-less «ناوگان ثبت‌شده» fleet
chart has no time pill and is excluded from time filter scope.

Explore keeps Superset's Gregorian picker. Calendar presets such as «این ماه» save
fixed dates; rolling presets such as «۷ روز اخیر» follow today and may return no
rows for this historical backup. To restore the stock dashboard picker, add
`"datefilter_enabled": False` to `JALALI`, restart Superset, and fully reload.
The macros and saved ranges still work.

## Start

`backups/1may-backup.sql` must sit next to `backups/02-bi.sql`. It is not in git.

```bash
docker compose up --build -d
docker compose logs -f superset-bootstrap
```

Wait for `TRAFFIC_BOOTSTRAP_DONE`.

`docker compose down -v` deletes both Postgres volumes. The dump is restored only when the backup volume is empty.

```text
superset/Dockerfile           Superset 6.1 plus the Jalali package
superset/superset_config.py   Persian UI and the Jalali macros
superset/bootstrap_traffic.py vehicle dashboard
db/01-init.sql                Superset metadata database
backups/restore.sh            loads 1may-backup.sql
backups/02-bi.sql             bi.vehicle and bi.violation; companies and users stay in the backup
superset-jalali              installed plugin (pinned wheel built in Docker)
```

For this demo, bootstrap creates direct Superset logins for the backup's active users,
with the username as the password and the `TrafficCompanyUser` role. For example,
`navidahmadian` sees the Qom company subtree, `fkreza90` the Tehran subtree, and
`fkreza` the national subtree. The host picker continues to use the backup users and
companies directly. These are demo credentials.

## Upgrade the Jalali integration on existing volumes

Keep the restored backup volume. Rebuild the images, recreate only the BI layer,
then reset only Superset metadata (old datasets refer to removed display columns,
and the direct dataset changed from virtual `violation_jalali` to physical
`bi.violation`).
The metadata reset deletes local Superset users and custom dashboards; bootstrap
recreates the two demo dashboards, direct demo users, and their access rules.

```bash
docker compose build superset-init superset superset-bootstrap embed-app
docker compose stop superset embed-app
docker compose exec -T backup-db psql -U postgres < backups/02-bi.sql
docker compose rm -sf db
docker volume rm superset-demo_pgdata
docker compose up -d
docker compose logs -f superset-bootstrap
```

Wait for `TRAFFIC_BOOTSTRAP_DONE`. Do not remove `superset-demo_backupdata` or use
`docker compose down -v` during this upgrade: the large dump does not need restoring.

```bash
curl -f http://localhost:8088/superset-jalali/health
```

Logged-in `/dynamic-plugins/api/read` should return HTTP 200 with one plugin.

Picker screenshots: [Superset](docs/screenshots/superset-jalali-picker.png) and
[embedded app](docs/screenshots/embedded-jalali-picker.png).
