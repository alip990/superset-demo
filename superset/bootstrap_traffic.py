"""Traffic-police dashboards on the restored beta backup (backup-db, schema bi - see backups/02-bi.sql).

Builds the same tabbed dashboard twice:
- traffic-fa: physical bi.violation for direct Superset logins, with company-tree RLS
  (a user linked to a company in bi.company_user sees it and every company below it);
- traffic-fa-embedded: for guest tokens. Its datasets are virtual and filter on
  get_guest_user_attribute('allowed_companies') (see SUPERSET_RLS_GUIDE.md), so the
  guest token itself carries no rls.
"""
import json, os
import requests

URL = os.environ.get("SUPERSET_URL", "http://superset:8088")
MAP_TILE_URL = os.environ.get("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
BASEMAP = f"tile://{MAP_TILE_URL}"
DB_NAME = "Traffic BI (backup)"
s = requests.Session()


def login():
    tok = s.post(f"{URL}/api/v1/security/login", json={"username": "admin", "password": "admin",
                                                        "provider": "db", "refresh": True}).json()["access_token"]
    s.headers["Authorization"] = f"Bearer {tok}"
    s.headers["X-CSRFToken"] = s.get(f"{URL}/api/v1/security/csrf_token/").json()["result"]
    s.headers["Referer"] = URL


def api(method, path, **kw):
    r = s.request(method, f"{URL}/api/v1/{path}", **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:800]}")
    return r.json()


def find(resource, col, value):
    q = json.dumps({"filters": [{"col": col, "opr": "eq", "value": value}]})
    res = api("GET", f"{resource}/?q={q}")["result"]
    return res[0]["id"] if res else None


login()

db_id = find("database", "database_name", DB_NAME) or api("POST", "database/", json={
    "database_name": DB_NAME,
    "sqlalchemy_uri": "postgresql+psycopg2://bi_reader:bi_reader@backup-db:5432/CrimeManagementDb",
    "expose_in_sqllab": True,
})["id"]



def dataset(name, sql=None, schema="bi"):
    ds = find("dataset", "table_name", name)
    body = {"database": db_id, "schema": schema, "table_name": name}
    if sql:
        body["sql"] = sql
    if ds:
        if sql:
            api("PUT", f"dataset/{ds}", json={"sql": sql})
        return ds
    return api("POST", "dataset/", json=body)["id"]


violation_ds = dataset("violation")
# tenant-scoped copy for guest tokens: the snippet from SUPERSET_RLS_GUIDE.md
violation_scoped_ds = dataset("violation_scoped", sql="""SELECT * FROM bi.violation
WHERE 1=1
{% set allowed_companies = get_guest_user_attribute('allowed_companies') %}
{% if allowed_companies %}
  AND company_id IN ({{ allowed_companies }})
{% else %}
  AND 1=0 -- Failsafe: if the attribute is missing, return nothing to prevent data leaks
{% endif %}""")
# no company_id column: shared reference data, needs no tenant filter
vehicle_ds = dataset("vehicle")

# ---------- metrics & helpers ----------
def metric(sql, label):
    return {"expressionType": "SQL", "sqlExpression": sql, "label": label}

CHECKS = metric("COUNT(*)", "تعداد پایش")
VIOLATIONS = metric("SUM(is_violation)", "تعداد تخلف")
RATE = metric("AVG(is_violation)", "نرخ تخلف")
VEHICLES = metric("COUNT(DISTINCT device_id)", "خودروهای پایش‌شده")
DRIVERS = metric("COUNT(DISTINCT driver_id)", "رانندگان")
ONLY_VIOLATIONS = [{"expressionType": "SQL", "clause": "WHERE", "sqlExpression": "is_violation = 1"}]

# Qom <-> Tehran freeway corridor
VIEWPORT = {"longitude": 51.05, "latitude": 35.1, "zoom": 8.6, "bearing": 0, "pitch": 0}
VIEWPORT_3D = {**VIEWPORT, "zoom": 8.8, "bearing": -12, "pitch": 50}
SPATIAL = {"type": "latlong", "latCol": "lat_grid", "lonCol": "lon_grid"}


def chart(name, viz, params, ds):
    cid = find("chart", "slice_name", name)
    params = {"viz_type": viz, "datasource": f"{ds}__table", "adhoc_filters": [], **params}
    body = {"slice_name": name, "viz_type": viz, "datasource_id": ds, "datasource_type": "table",
            "params": json.dumps(params)}
    if cid:
        api("PUT", f"chart/{cid}", json=body)
        return cid
    return api("POST", "chart/", json=body)["id"]


def make_charts(ds, suffix, names):
    """All charts of the traffic dashboard on dataset ds; suffix keeps chart names unique.
    Fills names with {chart id: title without suffix}."""
    def c(name, viz, params):
        cid = chart(name + suffix, viz, params, ds)
        names[cid] = name
        return cid

    def kpi(name, m, fmt=",d"):
        return c(name, "big_number_total", {"metric": m, "y_axis_format": fmt, "header_font_size": 0.4,
                                            "subheader_font_size": 0.15})

    return {
        # ---- KPIs ----
        "k_checks": kpi("کل پایش‌های سرعت", CHECKS),
        "k_viol": kpi("تخلفات سرعت", VIOLATIONS),
        "k_rate": kpi("نرخ تخلف", RATE, ".1%"),
        "k_veh": kpi("خودروهای پایش‌شده", VEHICLES),
        "k_drv": kpi("رانندگان", DRIVERS),
        "gauge": c("شاخص تخلف (درصد)", "gauge_chart", {
            "metric": metric("ROUND(100.0 * AVG(is_violation), 1)", "درصد تخلف"), "min_val": 0, "max_val": 100,
            "start_angle": 225, "end_angle": -45, "font_size": 14, "number_format": "SMART_NUMBER",
            "show_progress": True, "overlap": True, "round_cap": True, "split_number": 10,
            "show_axis_line_ticks": False, "show_split_line": False, "row_limit": 10,
            "intervals": "20,40,100", "interval_color_indices": "4,5,1", "color_scheme": "supersetColors",
        }),
        # ---- company / overview ----
        "sunburst": c("ساختار سازمانی: کشور ← استان ← وضعیت", "sunburst_v2", {
            "columns": ["parent_company", "company", "status"], "metric": CHECKS, "secondary_metric": VIOLATIONS,
            "color_scheme": "supersetColors", "linear_color_scheme": "superset_seq_1", "label_type": "key",
            "show_labels": True, "show_labels_threshold": 3, "show_total": True, "number_format": "SMART_NUMBER",
            "row_limit": 1000,
        }),
        "status": c("سهم وضعیت پایش‌ها", "pie", {
            "groupby": ["status"], "metric": CHECKS, "row_limit": 10, "donut": True, "show_labels": True,
            "label_type": "key_percent", "labels_outside": True, "show_legend": True, "legendOrientation": "bottom",
            "number_format": "SMART_NUMBER", "color_scheme": "supersetColors",
        }),
        "company_bar": c("مقایسه پلیس استان‌ها", "echarts_timeseries_bar", {
            "x_axis": "company", "metrics": [CHECKS, VIOLATIONS], "groupby": [], "row_limit": 100,
            "orientation": "vertical", "show_legend": True, "legendOrientation": "top", "show_value": True,
            "y_axis_format": "SMART_NUMBER", "x_axis_sort_asc": True, "rich_tooltip": True,
            "color_scheme": "supersetColors",
        }),
        "daily": c("پایش‌ها و تخلفات روزانه (شمسی)", "echarts_timeseries_bar", {
            "x_axis": "jalali_date", "metrics": [CHECKS], "groupby": ["status"], "stack": "Stack",
            "row_limit": 1000, "x_axis_sort": "jalali_date", "x_axis_sort_asc": True, "show_legend": True,
            "legendOrientation": "top", "y_axis_format": "SMART_NUMBER", "rich_tooltip": True,
            "color_scheme": "supersetColors",
        }),
        "hourly": c("الگوی ساعتی تخلفات", "echarts_area", {
            "x_axis": "hour_of_day", "metrics": [VIOLATIONS], "groupby": ["company"], "row_limit": 1000,
            "x_axis_sort": "hour_of_day", "x_axis_sort_asc": True, "stack": "Stack", "opacity": 0.4,
            "markerEnabled": True, "markerSize": 4, "show_legend": True, "legendOrientation": "top",
            "y_axis_format": "SMART_NUMBER", "rich_tooltip": True, "x_axis_title": "ساعت",
            "color_scheme": "supersetColors",
        }),
        "day_hour": c("نقشه حرارتی روز × ساعت", "heatmap_v2", {
            "x_axis": "hour_of_day", "groupby": "jalali_date", "metric": VIOLATIONS, "row_limit": 10000,
            "linear_color_scheme": "red_yellow_blue", "normalize_across": "heatmap", "legend_type": "continuous",
            "show_legend": True, "show_values": False, "show_percentage": False, "sort_x_axis": "alpha_asc",
            "sort_y_axis": "alpha_asc", "left_margin": "auto", "bottom_margin": "auto", "xscale_interval": -1,
            "yscale_interval": -1, "y_axis_format": "SMART_NUMBER", "value_bounds": [None, None],
        }),
        # ---- maps ----
        "hex": c("نقشه سه‌بعدی کانون‌های تخلف", "deck_hex", {
            "spatial": SPATIAL, "size": VIOLATIONS, "adhoc_filters": ONLY_VIOLATIONS, "mapbox_style": BASEMAP,
            "extruded": True, "grid_size": 900, "js_agg_function": "sum", "row_limit": 10000,
            "color_picker": {"r": 224, "g": 67, "b": 85, "a": 1}, "viewport": VIEWPORT_3D,
        }),
        "heat": c("نقشه تراکم پایش‌ها", "deck_heatmap", {
            "spatial": SPATIAL, "size": CHECKS, "mapbox_style": BASEMAP, "row_limit": 10000,
            "intensity": 1, "radius_pixels": 25, "aggregation": "SUM", "linear_color_scheme": "oranges",
            "viewport": VIEWPORT,
        }),
        "scatter": c("نقاط تخلف به تفکیک پلیس استان", "deck_scatter", {
            "spatial": SPATIAL, "adhoc_filters": ONLY_VIOLATIONS, "mapbox_style": BASEMAP, "row_limit": 10000,
            "point_radius_fixed": {"type": "metric", "value": VIOLATIONS}, "point_unit": "square_m",
            "multiplier": 1, "min_radius": 3, "max_radius": 40, "dimension": "company",
            "color_scheme": "supersetColors", "color_picker": {"r": 0, "g": 122, "b": 135, "a": 0.8},
            "viewport": VIEWPORT,
        }),
        # ---- roads, vehicles, drivers ----
        "roads": c("پرتخلف‌ترین محورها", "echarts_timeseries_bar", {
            "x_axis": "location", "metrics": [VIOLATIONS], "groupby": [], "row_limit": 10,
            "orientation": "horizontal", "show_value": True, "show_legend": False, "y_axis_format": "SMART_NUMBER",
            "x_axis_sort": "تعداد تخلف", "x_axis_sort_asc": False, "color_scheme": "supersetColors",
        }),
        "treemap": c("تخلفات: پلیس استان ← محور", "treemap_v2", {
            "groupby": ["company", "location"], "metric": VIOLATIONS, "row_limit": 100, "show_labels": True,
            "show_upper_labels": True, "label_type": "key_value", "number_format": "SMART_NUMBER",
            "color_scheme": "supersetColors",
        }),
        "models": c("تخلفات به تفکیک مدل خودرو", "pie", {
            "groupby": ["vehicle_model"], "metric": VIOLATIONS, "row_limit": 20, "donut": False,
            "show_labels": True, "label_type": "key_percent", "show_legend": True, "legendOrientation": "bottom",
            "number_format": "SMART_NUMBER", "color_scheme": "supersetColors", "rose_type": "radius",
        }),
        "vehicles": c("خودروهای پرتخلف", "table", {
            "query_mode": "aggregate", "groupby": ["plate", "vehicle_model", "vehicle_usage", "company"],
            "metrics": [VIOLATIONS, CHECKS, RATE], "all_columns": [], "row_limit": 20, "order_desc": True,
            "timeseries_limit_metric": VIOLATIONS, "server_pagination": False, "show_cell_bars": True,
            "column_config": {"نرخ تخلف": {"d3NumberFormat": ".1%"}},
        }),
        "drivers": c("رانندگان پرتخلف", "table", {
            "query_mode": "aggregate", "groupby": ["driver_name", "plate", "company"],
            "metrics": [VIOLATIONS, CHECKS, RATE], "all_columns": [], "row_limit": 20, "order_desc": True,
            "timeseries_limit_metric": VIOLATIONS, "server_pagination": False, "show_cell_bars": True,
            "column_config": {"نرخ تخلف": {"d3NumberFormat": ".1%"}},
        }),
    }


INTRO = """<div class="traffic-intro">
<h3>پایش سرعت محور تهران - قم</h3>
<p>داده‌های نسخه بتا (پشتیبان ۱۱ اردیبهشت ۱۴۰۴): ثبت سرعت دستگاه‌های نصب‌شده روی ناوگان اتوبوس و کامیون.
هر پلیس استان فقط داده‌های حوزه خود و زیرمجموعه‌هایش را می‌بیند؛ پلیس کل کشور همه را.</p>
</div>"""


def build_dashboard(ds, slug, title, suffix="", extra_fleet_row=None):
    """Tabbed dashboard: header + KPI row above three tabs. Returns (dashboard id, charts)."""
    ids = {}
    charts = make_charts(ds, suffix, ids)
    names = {key: ids[cid] for key, cid in charts.items()} if suffix else {}
    pos = {"DASHBOARD_VERSION_KEY": "v2",
           "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
           "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
           "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": title}}}

    def add(node, parents):
        node["parents"] = parents
        pos[node["id"]] = node
        pos[parents[-1]]["children"].append(node["id"])

    def row(rid, parents, items):
        add({"type": "ROW", "id": rid, "children": [], "meta": {"background": "BACKGROUND_TRANSPARENT"}}, parents)
        for key, width, height in items:
            if key.startswith("MD:"):
                add({"type": "MARKDOWN", "id": f"MARKDOWN-{rid}", "children": [],
                     "meta": {"width": width, "height": height, "code": key[3:]}}, parents + [rid])
            else:
                meta = {"chartId": charts[key], "width": width, "height": height}
                if key in names:  # show the chart title without the uniqueness suffix
                    meta["sliceNameOverride"] = names[key]
                add({"type": "CHART", "id": f"CHART-{key}", "children": [], "meta": meta}, parents + [rid])



    G = ["ROOT_ID", "GRID_ID"]
    row("ROW-intro", G, [("MD:" + INTRO, 12, 22)])
    row("ROW-kpi", G, [("k_checks", 2, 30), ("k_viol", 2, 30), ("k_rate", 2, 30),
                       ("k_veh", 2, 30), ("k_drv", 2, 30), ("gauge", 2, 30)])
    add({"type": "TABS", "id": "TABS-main", "children": [], "meta": {}}, G)
    T = G + ["TABS-main"]
    tabs = {"TAB-overview": "نمای کلی و سازمان", "TAB-maps": "نقشه‌ها", "TAB-fleet": "محورها، خودروها و رانندگان"}
    for tid, tab_title in tabs.items():
        add({"type": "TAB", "id": tid, "children": [], "meta": {"text": tab_title, "defaultText": tab_title}}, T)

    row("ROW-o1", T + ["TAB-overview"], [("sunburst", 5, 80), ("company_bar", 4, 80), ("status", 3, 80)])
    row("ROW-o2", T + ["TAB-overview"], [("daily", 6, 70), ("hourly", 6, 70)])
    row("ROW-o3", T + ["TAB-overview"], [("day_hour", 12, 60)])
    row("ROW-m1", T + ["TAB-maps"], [("hex", 12, 110)])
    row("ROW-m2", T + ["TAB-maps"], [("heat", 6, 90), ("scatter", 6, 90)])
    row("ROW-f1", T + ["TAB-fleet"], [("roads", 6, 70), ("treemap", 6, 70)])
    row("ROW-f2", T + ["TAB-fleet"], [("models", 4, 80), ("vehicles", 8, 80)])
    row("ROW-f3", T + ["TAB-fleet"], [("drivers", 12, 70)])
    if extra_fleet_row:  # charts on other datasets: not targeted by the native filters
        charts.update(extra_fleet_row)
        row("ROW-f4", T + ["TAB-fleet"], [(key, 12, 60) for key in extra_fleet_row])

    def select_filter(fid, name, column):
        return {"id": fid, "name": name, "filterType": "filter_select", "type": "NATIVE_FILTER",
                "targets": [{"datasetId": ds, "column": {"name": column}}],
                "controlValues": {"enableEmptyFilter": False, "multiSelect": True, "searchAllOptions": False,
                                  "inverseSelection": False, "defaultToFirstItem": False},
                "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
                "cascadeParentIds": [], "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "chartsInScope": [cid for k, cid in charts.items() if k not in (extra_fleet_row or {})], "tabsInScope": list(tabs), "description": ""}

    filters = [select_filter("NATIVE_FILTER-company", "پلیس استان", "company"),
               select_filter("NATIVE_FILTER-date", "تاریخ (شمسی)", "jalali_date"),
               select_filter("NATIVE_FILTER-status", "وضعیت", "status"),
               select_filter("NATIVE_FILTER-road", "محور", "location"),
               select_filter("NATIVE_FILTER-model", "مدل خودرو", "vehicle_model")]

    metadata = {
        "refresh_frequency": 0, "color_scheme": "supersetColors", "native_filter_configuration": filters,
        "label_colors": {"بدون خلافی": "#5AC189", "دارای تخلف": "#E04355", "لیست سیاه": "#454E7C",
                         "پلیس راهنمایی و رانندگی استان تهران": "#1FA8C9",
                         "پلیس راهنمایی و رانندگی استان قم": "#FCC700",
                         "راهنمایی و رانندگی کل کشور": "#454E7C"},
        "cross_filters_enabled": True,
    }
    CSS = """
    @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap');
    .dashboard, .dashboard-content, .header-title, .chart-header, .dashboard-markdown { font-family: 'Vazirmatn', sans-serif !important; }
    .dashboard-markdown .traffic-intro { direction: rtl; padding: 12px 20px; border-radius: 12px;
      background: linear-gradient(135deg, #0d3b66 0%, #1fa8c9 100%); color: #fff; }
    .dashboard-markdown .traffic-intro h3 { margin: 0 0 6px; font-weight: 800; color: #fff; }
    .dashboard-markdown .traffic-intro p { margin: 0; opacity: .92; line-height: 1.9; }
    .dashboard-component-chart-holder { border-radius: 12px; box-shadow: 0 2px 10px rgba(13, 59, 102, .08); }
    """
    dash_body = {"dashboard_title": title, "slug": slug, "published": True,
                 "position_json": json.dumps(pos), "json_metadata": json.dumps(metadata), "css": CSS}
    dash_id = find("dashboard", "slug", slug)
    if dash_id:
        api("PUT", f"dashboard/{dash_id}", json=dash_body)
    else:
        dash_id = api("POST", "dashboard/", json=dash_body)["id"]
    for cid in charts.values():
        api("PUT", f"chart/{cid}", json={"dashboards": [dash_id]})
    return dash_id, charts


TITLE = "داشبورد پایش سرعت - پلیس راهور"
dash_id, _ = build_dashboard(violation_ds, "traffic-fa", TITLE)
vehicle_chart = chart("ناوگان ثبت‌شده (بدون company_id) - تعبیه", "table", {
    "query_mode": "raw", "all_columns": ["plate", "vehicle_model", "vehicle_usage"], "row_limit": 200,
    "server_pagination": False, "order_by_cols": [], "include_search": True,
}, vehicle_ds)
embed_dash_id, _ = build_dashboard(violation_scoped_ds, "traffic-fa-embedded", TITLE + " (تعبیه‌شده)",
                                   suffix=" - تعبیه", extra_fleet_row={"fleet": vehicle_chart})
embedded = api("POST", f"dashboard/{embed_dash_id}/embedded", json={"allowed_domains": []})["result"]["uuid"]
print("TRAFFIC_EMBEDDED_DASHBOARD_UUID", embedded)

# ---------- company-tree users & RLS ----------
from superset.app import create_app  # noqa: E402

app = create_app()
with app.app_context():
    from superset import db, security_manager as sm
    from superset.connectors.sqla.models import SqlaTable, RowLevelSecurityFilter
    from superset.utils.core import RowLevelSecurityFilterType

    table = db.session.get(SqlaTable, violation_ds)
    role = sm.find_role("TrafficCompanyUser") or sm.add_role("TrafficCompanyUser")
    for pv in sm.find_role("Gamma").permissions:
        sm.add_permission_role(role, pv)
    pv = sm.find_permission_view_menu("datasource_access", table.get_perm())
    if pv:
        sm.add_permission_role(role, pv)

    # guest tokens may only read the tenant-scoped virtual dataset and the company-free one
    guest = sm.find_role("EmbedGuest")
    for ds_id in (violation_scoped_ds, vehicle_ds):
        pv = sm.find_permission_view_menu("datasource_access", db.session.get(SqlaTable, ds_id).get_perm())
        if pv:
            sm.add_permission_role(guest, pv)

    # usernames must match bi.company_user in backups/02-bi.sql
    for uname, first in [("traffic_national", "پلیس کل کشور"), ("traffic_qom", "پلیس قم"),
                         ("traffic_tehran", "پلیس تهران")]:
        if not sm.find_user(username=uname):
            sm.add_user(uname, first, "Demo", f"{uname}@example.com", [role], password=uname)

    rls = db.session.query(RowLevelSecurityFilter).filter_by(name="company-tree-by-current-user").one_or_none()
    if not rls:
        rls = RowLevelSecurityFilter(name="company-tree-by-current-user")
        db.session.add(rls)
    rls.filter_type = RowLevelSecurityFilterType.REGULAR
    rls.clause = ("company_id IN (SELECT cc.descendant_id FROM bi.company_closure cc "
                  "JOIN bi.company_user cu ON cu.company_id = cc.ancestor_id "
                  "WHERE cu.username = '{{ current_username() }}')")
    rls.tables = [table]
    rls.roles = [role]
    rls.description = "A user sees their own company and every company below it in the tree"
    db.session.commit()

print("TRAFFIC_BOOTSTRAP_DONE dashboard_ids=", dash_id, embed_dash_id)
