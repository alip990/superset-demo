# Superset 6.1.0 verification

| # | Fact | Where |
|---|---|---|
| F1 | Virtual dataset SQL is rendered through Jinja (with `JINJA_CONTEXT_ADDONS`) when Superset fetches its columns, so creating a virtual dataset that uses our macros via the REST API works. | `superset/connectors/sqla/utils.py` → `get_virtual_table_metadata()` calls `dataset.get_template_processor().process_template(...)` (~line 108) |
| F2 | `JINJA_CONTEXT_ADDONS` entries are merged into every template processor's context. | `superset/jinja_context.py` → `context_addons()` (~line 94) and `BaseTemplateProcessor.set_context()` (~line 690) |
| F3 | Guest-token RLS rules **without** `dataset` are applied to the **outer** query of every dataset (so every dataset must have that column). This is why the repo's README says every dataset needs `region`. | `superset/connectors/sqla/models.py` → `get_sqla_row_level_filters()` (~lines 741–790) |
| F4 | Guest-token RLS rules **with** `"dataset": <id>` are applied to that physical dataset, **and also to that physical table when it is referenced inside a virtual dataset's SQL** (before aggregation). Global rules are deliberately skipped there to avoid double application. | `superset/utils/rls.py` → `get_predicates_for_table()` (~lines 67–125), comment at ~line 105 |
| F5 | For virtual datasets, RLS predicates are part of the cache key, so different date ranges never share cached results. | `superset/connectors/sqla/models.py` ~lines 1988–2015 |
| F6 | The embedded iframe accepts a new guest token at any time but does **not** re-run queries when it does; there is no "set filters" message. Re-mounting the iframe (what `embed-app` already does) is the reliable way to apply a new range. | `superset-frontend/src/embedded/index.tsx` ~lines 246–257 (`guestToken` handler only calls `setupGuestClient`, `start()` runs once) |
| F7 | The embedded SDK in the 6.1.0 tree is version `0.3.0` (the repo loads `0.2.0` from a CDN). | `superset-embedded-sdk/package.json` |


Sources: [superset/connectors/sqla/utils.py](https://github.com/apache/superset/blob/6.1.0/superset/connectors/sqla/utils.py), [superset/jinja_context.py](https://github.com/apache/superset/blob/6.1.0/superset/jinja_context.py), [superset/connectors/sqla/models.py](https://github.com/apache/superset/blob/6.1.0/superset/connectors/sqla/models.py), [superset/utils/rls.py](https://github.com/apache/superset/blob/6.1.0/superset/utils/rls.py), [superset-frontend/src/embedded/index.tsx](https://github.com/apache/superset/blob/6.1.0/superset-frontend/src/embedded/index.tsx), [superset-embedded-sdk/package.json](https://github.com/apache/superset/blob/6.1.0/superset-embedded-sdk/package.json), [superset/config.py](https://github.com/apache/superset/blob/6.1.0/superset/config.py)

Pivot fields verified in tagged controlPanel.tsx and exercised through chart API and browser. Native Select filters are omitted; the host range picker is the primary date filter. Guest header: X-GuestToken (superset/config.py). SDK 0.3.0 and JalaliDatePicker 1.0.0 CDN assets fetched successfully. Picker input selector: input[data-jdp].

Calendar generation pins jdatetime 6.1.0 and persiantools 4.0.0. Current persiantools 6.2.0 differs from jdatetime starting at 1503 due to future leap corrections. The committed anchors match both pinned libraries throughout 1350–1551; future astronomical accuracy is limited to this agreed calendar convention.

Browser verification: all nine chart data requests succeeded. With manager and 1403/07/01–1403/07/30, the pivot displayed row 1403 and column 1403-07 مهر, the monthly chart displayed one bar, and recent rows were bounded to that month. The host uses embed_app_session to avoid collision with Superset session cookies across ports. Guest smoke SQL comparisons passed for monthly, map, region+date rules, and cache range isolation.
