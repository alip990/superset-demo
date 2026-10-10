# Superset 6.1.0 verification

| # | Fact | Where |
|---|---|---|
| F1 | Virtual dataset SQL is rendered through Jinja (with `JINJA_CONTEXT_ADDONS`) when Superset fetches its columns, so creating a virtual dataset that uses our macros via the REST API works. | `superset/connectors/sqla/utils.py` → `get_virtual_table_metadata()` calls `dataset.get_template_processor().process_template(...)` (~line 108) |
| F2 | `JINJA_CONTEXT_ADDONS` entries are merged into every template processor's context. | `superset/jinja_context.py` → `context_addons()` (~line 94) and `BaseTemplateProcessor.set_context()` (~line 690) |
| F3 | Guest-token RLS rules **without** `dataset` are applied to the **outer** query of every dataset (so every dataset must have that column). This is why the repo's README says every dataset needs `region`. | `superset/connectors/sqla/models.py` → `get_sqla_row_level_filters()` (~lines 741–790) |
| F4 | Guest-token RLS rules **with** `"dataset": <id>` are applied to that physical dataset, **and also to that physical table when it is referenced inside a virtual dataset's SQL** (before aggregation). Global rules are deliberately skipped there to avoid double application. **Not used any more:** this demo no longer sends scoped date rules. Guest-token RLS is the region security rule only. | `superset/utils/rls.py` → `get_predicates_for_table()` (~lines 67–125), comment at ~line 105 |
| F5 | For virtual datasets, RLS predicates are part of the cache key, so different date ranges never share cached results. | `superset/connectors/sqla/models.py` ~lines 1988–2015 |
| F6 | The embedded iframe accepts a new guest token at any time but does **not** re-run queries when it does; there is no "set filters" message. Re-mounting the iframe (what `embed-app` does when the user changes) is how a new region rule takes effect. Date filters are native dashboard filters, not part of the token. | `superset-frontend/src/embedded/index.tsx` ~lines 246–257 (`guestToken` handler only calls `setupGuestClient`, `start()` runs once) |
| F8 | A saved native filter in 6.1.0 is the object written by `transformFormInput`: `id`, `type: "NATIVE_FILTER"`, `name`, `filterType` (`filter_select` or `filter_range`), `targets: [{datasetId, column: {name}}]`, `scope: {rootPath: ["ROOT_ID"], excluded: [chartId]}`, `controlValues`, `defaultDataMask: {extraFormData, filterState, ownState}`, `cascadeParentIds`, and `description`. Select controls are `multiSelect`, `sortAscending`, `searchAllOptions`, `inverseSelection`, `defaultToFirstItem`, plus `enableEmptyFilter`. If `chartsInScope` is absent, active filters start from every chart id and then drop `scope.excluded`, so excluding the map chart id keeps the date filter off `sales_by_branch`. | `FiltersConfigModal/transformers/filterTransformer.ts` `transformFormInput`; `dashboard/util/activeAllDashboardFilters.ts` (scope falls back to all slice ids, then removes `scope.excluded`); Select and Range `controlPanel.ts` |
| F7 | The embedded SDK in the 6.1.0 tree is version `0.3.0` (the repo loads `0.2.0` from a CDN). | `superset-embedded-sdk/package.json` |


Sources: [superset/connectors/sqla/utils.py](https://github.com/apache/superset/blob/6.1.0/superset/connectors/sqla/utils.py), [superset/jinja_context.py](https://github.com/apache/superset/blob/6.1.0/superset/jinja_context.py), [superset/connectors/sqla/models.py](https://github.com/apache/superset/blob/6.1.0/superset/connectors/sqla/models.py), [superset/utils/rls.py](https://github.com/apache/superset/blob/6.1.0/superset/utils/rls.py), [superset-frontend/src/embedded/index.tsx](https://github.com/apache/superset/blob/6.1.0/superset-frontend/src/embedded/index.tsx), [superset-embedded-sdk/package.json](https://github.com/apache/superset/blob/6.1.0/superset-embedded-sdk/package.json), [superset/config.py](https://github.com/apache/superset/blob/6.1.0/superset/config.py), [filterTransformer.ts](https://github.com/apache/superset/blob/6.1.0/superset-frontend/src/dashboard/components/nativeFilters/FiltersConfigModal/transformers/filterTransformer.ts), [activeAllDashboardFilters.ts](https://github.com/apache/superset/blob/6.1.0/superset-frontend/src/dashboard/util/activeAllDashboardFilters.ts)

Pivot fields verified in tagged controlPanel.tsx and exercised through chart API and browser. Date filtering uses the native filters in F8. Guest header: X-GuestToken (superset/config.py). The vendored SDK is 0.3.0.

Native filter object this demo writes (ids are stable):

```json
{
  "id": "NATIVE_FILTER-jalali_year",
  "name": "سال",
  "filterType": "filter_select",
  "type": "NATIVE_FILTER",
  "targets": [{"datasetId": 1, "column": {"name": "jalali_year"}}],
  "controlValues": {
    "enableEmptyFilter": false,
    "multiSelect": true,
    "sortAscending": true,
    "searchAllOptions": false,
    "inverseSelection": false,
    "defaultToFirstItem": false
  },
  "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
  "cascadeParentIds": [],
  "scope": {"rootPath": ["ROOT_ID"], "excluded": [2]},
  "description": ""
}
```

`filter_range` on `jalali_date_int` uses the same keys with `controlValues` only `{"enableEmptyFilter": false}`. ماه sets `cascadeParentIds` to `["NATIVE_FILTER-jalali_year"]`. `datasetId` and the excluded chart id are the live `sales_jalali` dataset id and the map chart id.

Calendar generation pins jdatetime 6.1.0 and persiantools 4.0.0. Current persiantools 6.2.0 differs from jdatetime starting at 1503 due to future leap corrections. The committed anchors match both pinned libraries throughout 1350–1551; future astronomical accuracy is limited to this agreed calendar convention.

Earlier browser verification (host range picker, now removed): all nine chart data requests succeeded for manager and Mehr 1403. The host still uses `embed_app_session` so its cookie does not collide with Superset across ports. Guest smoke now checks region-only RLS.

Self-hosted map browser verification: 20 raster tile requests returned HTTP 200; the basemap and branch points rendered in the iframe without chart error alerts. All services with health checks are healthy. PostgreSQL integration additionally verified Persian digits preserve numeric/date values and NULL dates produce entirely NULL Jalali outputs.
