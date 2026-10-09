# superset-jalali-sql

Dependency-free calendar conversion and PostgreSQL Jinja macros for stock Superset. No calendar objects are installed in the business database.

```python
from superset_jalali_sql import JINJA_ADDONS
JINJA_CONTEXT_ADDONS = dict(JINJA_ADDONS)
```

```sql
SELECT s.*, {{ jalali_columns('s.sale_date') }}
FROM sales s {{ jalali_join('s.sale_date') }}
```

Supports Jalali years 1350–1550, Persian text and optional Persian digits. Python exports `g2j`, `j2g`, `month_length`, `parse_jalali`. SQL helpers include `jalali_to_gregorian` and `jalali_period_sql`.

Install `[dev]` to regenerate Nowruz anchors and run tests. Generation requires agreement between pinned jdatetime 6.1.0 and persiantools 4.0.0. Newer persiantools changes future leap corrections from 1503; the committed table implements the shared convention of the pinned versions. SQL and Python always agree.
