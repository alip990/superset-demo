"""Idempotent-ish demo bootstrap: DB connection, datasets, charts, dashboard, roles, users, RLS, embedding."""
import json, os, time, uuid
import requests

URL = os.environ.get("SUPERSET_URL", "http://superset:8088")
TILE = os.environ.get("TILE_SERVER_PUBLIC_URL", "http://localhost:8081")
# Superset's deck.gl "mapbox_style" field requires "mapbox://styles/..." or
# "tile://http(s)://..." (raster XYZ) - a bare style.json URL is rejected.
MAP_TILE_URL = os.environ.get("MAP_TILE_URL", f"{TILE}/styles/basic-preview/{{z}}/{{x}}/{{y}}.png")
BASEMAP = f"tile://{MAP_TILE_URL}"
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

# ---------- database connection ----------
db_id = find("database", "database_name", "Demo DB (mock)") or api("POST", "database/", json={
    "database_name": "Demo DB (mock)",
    "sqlalchemy_uri": "postgresql+psycopg2://demo_reader:demo_reader@db:5432/demo",
    "expose_in_sqllab": True,
})["id"]


def dataset(name, sql=None):
    ds = find("dataset", "table_name", name)
    if not ds:
        body = {"database": db_id, "schema": "public", "table_name": name}
        if sql:
            body["sql"] = sql
        ds = api("POST", "dataset/", json=body)["id"]
    return ds


sales_ds = dataset("sales")
branch_ds = dataset("sales_by_branch", sql="""
SELECT branch_name, province_fa, region, lat, lon, SUM(amount) AS total_amount, COUNT(*) AS orders
FROM sales GROUP BY 1,2,3,4,5""")
# metric on the sales dataset
cols = api("GET", f"dataset/{sales_ds}")["result"]
if not any(m["metric_name"] == "total_amount" for m in cols["metrics"]):
    metrics = [{"id": m["id"], "metric_name": m["metric_name"], "expression": m["expression"]} for m in cols["metrics"]]
    metrics.append({"metric_name": "total_amount", "verbose_name": "مجموع فروش", "expression": "SUM(amount)"})
    api("PUT", f"dataset/{sales_ds}?override_columns=false", json={"metrics": metrics})

SUM_AMOUNT = {"expressionType": "SQL", "sqlExpression": "SUM(amount)", "label": "مجموع فروش"}


def chart(name, viz, ds, params):
    cid = find("chart", "slice_name", name)
    params = {"viz_type": viz, "datasource": f"{ds}__table", **params}
    body = {"slice_name": name, "viz_type": viz, "datasource_id": ds, "datasource_type": "table",
            "params": json.dumps(params)}
    if cid:
        api("PUT", f"chart/{cid}", json=body)
        return cid
    return api("POST", "chart/", json=body)["id"]


charts = {
    "map": chart("نقشه شعب (سرور نقشه داخلی)", "deck_scatter", branch_ds, {
        "spatial": {"type": "latlong", "latCol": "lat", "lonCol": "lon"},
        "mapbox_style": BASEMAP, "row_limit": 5000, "point_unit": "square_m", "multiplier": 1,
        "point_radius_fixed": {"type": "fix", "value": 12000}, "min_radius": 2, "max_radius": 250,
        "color_picker": {"r": 205, "g": 0, "b": 3, "a": 0.82},
        "viewport": {"longitude": 53.7, "latitude": 32.4, "zoom": 4.4, "bearing": 0, "pitch": 0},
        "js_tooltip": "", "adhoc_filters": [],
    }),
    "total": chart("مجموع فروش", "big_number_total", sales_ds, {"metric": SUM_AMOUNT, "adhoc_filters": [],
                                                              "y_axis_format": ",d"}),
    "monthly": chart("فروش ماهانه (تقویم شمسی)", "echarts_timeseries_bar", sales_ds, {
        "x_axis": "jalali_month", "metrics": [SUM_AMOUNT], "groupby": [], "adhoc_filters": [],
        "row_limit": 1000, "order_desc": False, "x_axis_sort": "jalali_month", "x_axis_sort_asc": True,
        "y_axis_format": "SMART_NUMBER", "show_legend": False,
    }),
    "category": chart("سهم دسته‌بندی‌ها", "pie", sales_ds, {"groupby": ["category"], "metric": SUM_AMOUNT,
                                                            "adhoc_filters": [], "row_limit": 100, "show_labels": True,
                                                            "label_type": "key_percent", "donut": True}),
    "province": chart("فروش به تفکیک استان", "table", sales_ds, {
        "query_mode": "aggregate", "groupby": ["province_fa", "region"], "metrics": [SUM_AMOUNT],
        "all_columns": [], "adhoc_filters": [], "row_limit": 100, "order_desc": True, "server_pagination": False,
    }),
}

# ---------- dashboard layout ----------
def chart_node(key, width, height):
    return {"type": "CHART", "id": f"CHART-{key}", "children": [],
            "meta": {"chartId": charts[key], "width": width, "height": height}}

rows = [["total", "category"], ["map", "monthly"], ["province"]]
widths = {"total": 4, "category": 8, "map": 6, "monthly": 6, "province": 12}
heights = {"total": 40, "category": 40, "map": 80, "monthly": 80, "province": 60}
pos = {"DASHBOARD_VERSION_KEY": "v2", "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
       "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
       "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": "داشبورد فروش"}}}
for i, row in enumerate(rows):
    rid = f"ROW-{i}"
    pos["GRID_ID"]["children"].append(rid)
    pos[rid] = {"type": "ROW", "id": rid, "children": [], "parents": ["ROOT_ID", "GRID_ID"],
                "meta": {"background": "BACKGROUND_TRANSPARENT"}}
    for k in row:
        node = chart_node(k, widths[k], heights[k])
        node["parents"] = ["ROOT_ID", "GRID_ID", rid]
        pos[rid]["children"].append(node["id"])
        pos[node["id"]] = node

dash_body = {"dashboard_title": "داشبورد فروش", "slug": "sales-fa", "published": True,
             "position_json": json.dumps(pos), "json_metadata": json.dumps({"refresh_frequency": 0})}
dash_id = find("dashboard", "slug", "sales-fa")
if dash_id:
    api("PUT", f"dashboard/{dash_id}", json=dash_body)
else:
    dash_id = api("POST", "dashboard/", json=dash_body)["id"]
# link charts to dashboard
for cid in charts.values():
    api("PUT", f"chart/{cid}", json={"dashboards": [dash_id]})

embedded = api("POST", f"dashboard/{dash_id}/embedded", json={"allowed_domains": []})["result"]["uuid"]
print("EMBEDDED_DASHBOARD_UUID", embedded)

# ---------- roles, users, RLS (via app context / ORM) ----------
from superset.app import create_app  # noqa: E402

app = create_app()
with app.app_context():
    from superset import db, security_manager as sm
    from superset.connectors.sqla.models import SqlaTable, RowLevelSecurityFilter
    from superset.utils.core import RowLevelSecurityFilterType

    gamma = sm.find_role("Gamma")

    def role_with_data(name):
        role = sm.find_role(name) or sm.add_role(name)
        for pv in gamma.permissions:
            sm.add_permission_role(role, pv)
        for t in db.session.query(SqlaTable).filter(SqlaTable.database_id == db_id):
            pv = sm.find_permission_view_menu("datasource_access", t.get_perm())
            if pv:
                sm.add_permission_role(role, pv)
        return role

    viewer = role_with_data("DemoViewer")
    guest = role_with_data("EmbedGuest")
    regional = sm.find_role("RegionalUser") or sm.add_role("RegionalUser")

    for uname, first in [("ali_north", "علی"), ("sara_south", "سارا"), ("manager", "مدیر")]:
        u = sm.find_user(username=uname)
        if not u:
            sm.add_user(uname, first, "Demo", f"{uname}@example.com", [viewer, regional], password=uname)

    tables = db.session.query(SqlaTable).filter(SqlaTable.table_name.in_(["sales", "sales_by_branch"])).all()
    rls = db.session.query(RowLevelSecurityFilter).filter_by(name="region-by-current-user").one_or_none()
    if not rls:
        rls = RowLevelSecurityFilter(name="region-by-current-user")
        db.session.add(rls)
    rls.filter_type = RowLevelSecurityFilterType.REGULAR
    rls.clause = "region IN (SELECT region FROM user_access WHERE username = '{{ current_username() }}')"
    rls.tables = tables
    rls.roles = [regional]
    rls.description = "Mandatory filter: each user only sees regions granted in user_access table"
    db.session.commit()

print("BOOTSTRAP_DONE dashboard_id=", dash_id)
