# Company-tree data access for embedded dashboards

This guide is for analysts who build datasets and charts that will be **embedded** in our
application. Read it before you add a dataset to an embedded dashboard.

## How it works

Companies form a tree. In the demo data, `bi.company` looks like this:

```
راهنمایی و رانندگی کل کشور                  (national)
├── پلیس راهنمایی و رانندگی استان قم          (Qom)
└── پلیس راهنمایی و رانندگی استان تهران       (Tehran)
```

A user of a company may see that company's data and the data of **every company below it**.
The national user sees everything. The Qom user sees only Qom.

1. The host application (`embed-app/app.py`) knows each user's own company. Before it asks
   Superset for a guest token, it walks down the tree with a recursive query and collects the
   allowed ids, for example `"1346027341989220352"` for Qom, or all three ids for national.
2. The application sends those ids to Superset inside the guest token. Superset 6.1 drops a
   `user.attributes` field, so the ids are packed into the username instead:
   `"police_qom|1346027341989220352"`. The token's `rls` list is always empty.
3. Superset makes the ids available in SQL through the Jinja macro
   `get_guest_user_attribute('allowed_companies')`. This macro is defined in
   `superset/superset_config.py`.
4. **Your dataset uses that macro to filter its rows.** Nothing else filters the data, so a
   dataset that doesn't use the macro shows every company's rows.

We don't use the guest token's `rls` list because Superset applies it to *every* dataset on the
dashboard. A dataset without a `company_id` column would then fail with a missing-column
error. Scoping `rls` entries to dataset ids would tie the application to Superset's internal
ids.

## Rules for embedded dashboards

1. **Use virtual datasets, never physical tables**, for any data that has a `company_id`.
   To create one: SQL Lab, write the query, then **Save → Save dataset**. Or go to
   Datasets → + Dataset and write the SQL there.
2. **Every virtual dataset over company data must contain this snippet unchanged:**

   ```sql
   SELECT * FROM your_physical_table
   WHERE 1=1
   {% set allowed_companies = get_guest_user_attribute('allowed_companies') %}

   {% if allowed_companies %}
     AND company_id IN ({{ allowed_companies }})
   {% else %}
     AND 1=0 -- Failsafe: if the attribute is missing, return nothing to prevent data leaks
   {% endif %}
   ```

   Replace `your_physical_table` and, if needed, `company_id` with your table's column. You can
   select specific columns or add joins, but keep the `{% if %}` / `{% else %} AND 1=0` block.
   The `else` branch is what keeps the dataset safe when the token has no company list: the
   dataset then returns no rows instead of every row.
3. **Datasets without a `company_id` column** (shared reference data such as the vehicle
   catalogue `bi.vehicle`) don't use the snippet. They are the same for every company, so they
   can't break and have nothing to leak. Only add such a dataset if the data really is shared
   by all companies.
4. **Native filters** on an embedded dashboard must target the scoped virtual dataset, so that
   the filter's dropdown values are filtered by company too.
5. **Grant the `EmbedGuest` role access only to the scoped virtual datasets** and the shared
   datasets, never to the physical company tables.

## Worked example in this repo

| Dataset | Kind | Company filter |
|---|---|---|
| `violation_scoped` | virtual, over `bi.violation` | the snippet above |
| `vehicle` | physical `bi.vehicle` | none, because it has no `company_id` |
| `violation` | physical `bi.violation` | none in SQL. It is used only by the direct-login dashboard `traffic-fa`, where a regular RLS rule applies |

`superset/bootstrap_traffic.py` builds the embedded dashboard `traffic-fa-embedded` from
these datasets.

## Caching is off, deliberately

Superset builds a chart's cache key from the query definition and the values that its
built-in macros (such as `current_username()`) register. It does **not** use the final SQL. A
custom macro like `get_guest_user_attribute` registers nothing, so with a data cache, Qom and
Tehran would get the same cache key for the same chart. Whichever query ran first would then
be served to the other company.

That's why `superset_config.py` sets `DATA_CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}`.
**Don't turn the data cache back on** unless the macro is changed to register the company
list in the cache key.

## Known limitations

- The ids are placed into the SQL as-is, without validation. They come from our own backend
  in a signed token, but they must stay a comma-separated list of integers.
- The username inside the token, and therefore Superset's logs, contains the company ids.
- In SQL Lab or chart editing as a normal Superset user, the macro returns nothing, so the
  scoped datasets show no rows. This is the failsafe working. Preview through the embed app,
  or temporarily edit the dataset.

## Checking it

With the stack running, open http://localhost:8090 and switch users. The first KPI should
read:

| App user | Allowed companies | Total speed checks |
|---|---|---|
| police_national | all three | 931,335 |
| police_qom | Qom | 511,392 |
| police_tehran | Tehran | 419,943 |

A guest token without the packed ids (username without `|`) shows 0 or "No results" on every
company chart.
