"""Host application demo: logs its own users in, then embeds a Superset dashboard
in an iframe with a guest token whose RLS is built from the app user's attributes."""
import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from superset_jalali_sql import g2j, j2g, month_length, parse_jalali
import requests
from flask import Flask, jsonify, render_template, request, session

SUPERSET = os.environ.get("SUPERSET_URL", "http://superset:8088")
SUPERSET_PUBLIC = os.environ.get("SUPERSET_PUBLIC_URL", "http://localhost:8088")

# Users of *our* application and their attributes (would come from your IAM / DB)
APP_USERS = {
    "ali_north": {"name": "علی (منطقه شمال)", "regions": ["north"]},
    "sara_south": {"name": "سارا (جنوب و مرکز)", "regions": ["south", "center"]},
    "manager": {"name": "مدیر (همه مناطق)", "regions": None},  # None = no restriction
}

app = Flask(__name__, template_folder=".")
app.secret_key = "host-app-demo"


def superset_session():
    s = requests.Session()
    tok = s.post(f"{SUPERSET}/api/v1/security/login",
                 json={"username": "admin", "password": "admin", "provider": "db"}).json()["access_token"]
    s.headers["Authorization"] = f"Bearer {tok}"
    s.headers["X-CSRFToken"] = s.get(f"{SUPERSET}/api/v1/security/csrf_token/").json()["result"]
    s.headers["Referer"] = SUPERSET
    return s


@app.get("/")
def index():
    s = superset_session()
    uuid = s.get(f"{SUPERSET}/api/v1/dashboard/sales-fa/embedded").json()["result"]["uuid"]
    return render_template("index.html", users=APP_USERS, current=session.get("user", "ali_north"),
                           dashboard_uuid=uuid, superset_url=SUPERSET_PUBLIC)


@app.post("/login")
def login():
    if not request.is_json or request.json.get("user") not in APP_USERS:
        return jsonify(error="Unknown user"), 400
    session["user"] = request.json["user"]
    return jsonify(ok=True)


def format_jalali(d):
    return "%04d/%02d/%02d" % g2j(d)


def range_gregorian():
    selected = session.get("range")
    if not selected:
        return None
    start = j2g(*parse_jalali(selected["from"]))
    end = j2g(*parse_jalali(selected["to"]))
    return {"from": start.isoformat(), "to": end.isoformat(),
            "end_exclusive": (end + timedelta(days=1)).isoformat()}


@app.post("/range")
def set_range():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="Expected a JSON object"), 400
    if not body:
        session.pop("range", None)
    else:
        try:
            start = j2g(*parse_jalali(body.get("from")))
            end = j2g(*parse_jalali(body.get("to")))
            if start > end:
                raise ValueError("Start must be before end")
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        session["range"] = {"from": format_jalali(start), "to": format_jalali(end)}
    return jsonify(range=session.get("range"), range_gregorian=range_gregorian())


@app.get("/jalali/presets")
def presets():
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()
    y, m, _ = g2j(today)
    py, pm = (y-1,12) if m == 1 else (y,m-1)
    index = y*12 + m-1-2
    ty, tm = divmod(index,12)
    periods = [
        ("امروز", today, today),
        ("این هفته", today-timedelta(days=(today.weekday()+2)%7), today),
        ("این ماه", j2g(y,m,1), today),
        ("ماه گذشته", j2g(py,pm,1), j2g(y,m,1)-timedelta(days=1)),
        ("سه ماه اخیر", j2g(ty,tm+1,1), today),
        ("امسال", j2g(y,1,1), today),
        ("سال گذشته", j2g(y-1,1,1), j2g(y,1,1)-timedelta(days=1)),
    ]
    return jsonify([{"label": label, "from": format_jalali(a), "to": format_jalali(b)} for label,a,b in periods])


_sales_dataset_id = None

def sales_dataset_id(s):
    global _sales_dataset_id
    if _sales_dataset_id is None:
        q = json.dumps({"filters": [{"col": "table_name", "opr": "eq", "value": "sales"}]})
        r = s.get(f"{SUPERSET}/api/v1/dataset/", params={"q": q}, timeout=30)
        r.raise_for_status()
        physical = [d for d in r.json()["result"] if not d.get("sql") and d.get("schema") == "public"]
        if len(physical) != 1:
            raise RuntimeError("Expected exactly one physical sales dataset")
        _sales_dataset_id = physical[0]["id"]
    return _sales_dataset_id


@app.get("/guest-token")
def guest_token():
    uname = session.get("user", "ali_north")
    user = APP_USERS[uname]
    s = superset_session()
    uuid = s.get(f"{SUPERSET}/api/v1/dashboard/sales-fa/embedded").json()["result"]["uuid"]
    rls = []
    if user["regions"] is not None:
        regions = ", ".join("'%s'" % r.replace("'", "''") for r in user["regions"])
        rls.append({"clause": f"region IN ({regions})"})  # applied to every dataset in the dashboard
    selected = range_gregorian()
    if selected:
        rls.append({"dataset": sales_dataset_id(s),
                    "clause": f"sale_date >= DATE '{selected['from']}' AND sale_date < DATE '{selected['end_exclusive']}'"})
    body = {"user": {"username": uname, "first_name": user["name"], "last_name": ""},
            "resources": [{"type": "dashboard", "id": uuid}], "rls": rls}
    r = s.post(f"{SUPERSET}/api/v1/security/guest_token/", json=body)
    r.raise_for_status()
    return jsonify(token=r.json()["token"], rls=rls, range=session.get("range"), range_gregorian=selected)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090, threaded=True)
