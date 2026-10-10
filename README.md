# Superset with the vehicle backup

| | |
|---|---|
| Superset | http://localhost:8088 (`admin` / `admin`) |
| Host app | http://localhost:8090 |
| Vehicle backup | `127.0.0.1:5441`, database `CrimeManagementDb` |

Open the host app to pick a user from `um."User"` and a company from `um."Company"`. Those tables stay in the 1 May backup. The guest token lists that company and every company under it. `traffic-fa-embedded` keeps only those rows.

`traffic-fa` is the same charts for a direct Superset login. A login whose username matches `um."User"."UserName"` sees that user's company subtree.

The Jalali SQL macros are installed in the Superset image (`packages/superset-jalali-sql`) and registered in `superset/superset_config.py`. Use them on any virtual dataset:

```sql
SELECT s.*, {{ jalali_columns('s.sale_date') }}
FROM sales s
{{ jalali_join('s.sale_date') }}
```

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
packages/superset-jalali-sql  calendar macros
```

Logins `traffic_national`, `traffic_qom`, and `traffic_tehran` use the same word as the password. Each sees its company and the companies below it.
