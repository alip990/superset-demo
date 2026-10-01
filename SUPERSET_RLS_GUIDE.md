# Company-tree data access for embedded dashboards

<div dir="rtl">

**خلاصهٔ فارسی:** در داشبوردهای embed، هر کاربر فقط دادهٔ شرکت خودش و شرکت‌های زیرمجموعه‌اش را می‌بیند. برنامهٔ میزبان شناسهٔ این شرکت‌ها را داخل توکن مهمان می‌فرستد و هر dataset مجازی باید با `get_guest_user_attribute('allowed_companies')` فیلتر کند؛ اگر شناسه‌ای نباشد، هیچ سطری برنمی‌گردد. کش داده روشن است، چون مقدار این شناسه‌ها در کلید کش هم می‌آید. توضیح کامل و ساده: [راهنمای فارسی در README](README.md#راهنمای-فارسی)

</div>

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

1. The host application (`embed-app/app.py`) knows each user's own company
   (`um.UserAttribute.CompanyId` in the user service, copied to `bi.app_user`). The user may
   narrow the view to a company below their own. Before it asks Superset for a guest token,
   the application walks down the tree from the selected company with a recursive query and
   collects the allowed ids, for example `"1346027341989220352"` for Qom, or all three ids for
   national.
2. The application sends those ids to Superset inside the guest token, as a guest-user
   attribute:

   ```json
   {"user": {"username": "police_qom",
             "attributes": {"allowed_companies": [1346027341989220352]}},
    "resources": [{"type": "dashboard", "id": "..."}],
    "rls": []}
   ```

   The token's `rls` list is always empty.
3. Superset makes the ids available in SQL through the Jinja macro
   `get_guest_user_attribute('allowed_companies')`.

   Both halves of that - `user.attributes` surviving the API, and the macro existing - come
   from `superset/guest_user_attributes.py`, which backports the feature from
   apache/superset master onto 6.1.0. Released Superset (6.1.0 included) silently **drops**
   `user.attributes`, because its marshmallow `UserSchema` excludes unknown fields, and has
   no macro to read them back. `superset_config.py` installs the backport from
   `FLASK_APP_MUTATOR`.
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
   {% set allowed_companies = get_guest_user_attribute('allowed_companies', escape_result=False) %}

   {% if allowed_companies %}
     AND company_id IN {{ allowed_companies | where_in }}
   {% else %}
     AND 1=0 -- Failsafe: if the attribute is missing, return nothing to prevent data leaks
   {% endif %}
   ```

   `where_in` renders the list as a parenthesised SQL list and quotes each value with the
   database dialect's own literal rendering, so the ids never reach the SQL unescaped - that
   is why the snippet has no parentheses of its own around it. `escape_result=False` goes
   with it: the macro escapes strings itself by default, and letting both escape would quote
   every value twice.

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

## Caching is on, and why that is safe

Superset builds a chart's cache key from the query definition plus whatever its macros
register through `cache_key_wrapper()`. It does **not** hash the final SQL. So a macro that
registers nothing is invisible to the cache key: Qom and Tehran get the *same* key for the
same chart, and whichever query runs first is served to the other company.

There are two parts to registering, and both are in `guest_user_attributes.py`:

- the macro is bound to the request's own `ExtraCache` instance, so its
  `cache_key_wrapper(f"guest_user_attribute:allowed_companies:{value}")` call lands in
  *this* query's extra cache keys. A macro added through `JINJA_CONTEXT_ADDONS` cannot do
  this - it has no `ExtraCache` to register with, which is why the earlier version of this
  demo had to disable the cache;
- `get_guest_user_attribute` is added to `ExtraCache.regex`. That regex is how
  `SqlaTable.has_extra_cache_key_calls()` decides whether a dataset's SQL is even worth
  re-rendering to collect cache keys. A macro missing from it never gets the chance to
  register, no matter how it is bound.

With both in place `DATA_CACHE_CONFIG` points at Redis again, and each distinct
`allowed_companies` value gets its own cache entry.

If you port this to another Superset version, check that patch still applies. It raises at
start-up rather than booting half-patched, because a silently unregistered macro is a
cross-tenant data leak, not a performance regression.

The Jalali dataset macros (`superset/jalali_calendar/jinja.py`) are registered the same way,
for the same reason in a milder form: `{{ jalali_filter('occurred_at', 'Current jalali
month') }}` resolves to a different date range every month, so without the cache key a chart
would keep serving last month's rows after midnight on the 1st. The three macros whose value
depends only on their arguments (`to_jalali`, `from_jalali`, `jalali_grain`) deliberately
register nothing. See [JALALI_CALENDAR.md](JALALI_CALENDAR.md).

## Known limitations

- The ids are not validated beyond `where_in`'s dialect quoting. They come from our own
  backend inside a signed token; keep them a list of integers.
- `guest_user_attributes.py` monkeypatches Superset at start-up. Re-check it on every
  Superset upgrade, and drop it once a release ships the feature (SIP-174).
- Pipe a list attribute through `| where_in` and index into a dict attribute; don't render
  a whole list or dict into SQL. Individual strings are escaped, but rendering the whole
  container goes through Python's `repr()`, which adds quote characters of its own.
- In SQL Lab or chart editing as a normal Superset user, the macro returns nothing, so the
  scoped datasets show no rows. This is the failsafe working. Preview through the embed app,
  or temporarily edit the dataset.

## Checking it

With the stack running, open http://localhost:8090. The page has two dropdowns:

- **کاربر (user):** the activated users of the real user service (`um.User`, copied to
  `bi.app_user`), plus the demo-only **مدیر سامانه** entry that may pick any company.
- **شرکت (company):** only the user's own company and the companies below it. The default is
  the user's own company. The backend checks the chosen company again, so a Qom user can't
  request Tehran by editing the request.

| Selection | allowed_companies | Total speed checks |
|---|---|---|
| `fkreza` (national) | all three | 931,335 |
| `fkreza` → company Tehran | Tehran | 419,943 |
| `navidahmadian` (Qom) | Qom only; the dropdown offers nothing else | 511,392 |
| `superadmin` (no company) | none | 0 (failsafe) |
| مدیر سامانه → Qom | Qom | 511,392 |

A guest token with no `allowed_companies` attribute shows 0 or "No results" on every company
chart - that is the `{% else %} AND 1=0` failsafe, not a bug.
