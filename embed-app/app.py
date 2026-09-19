"""Host application demo: logs its own users in, then embeds a Superset dashboard
in an iframe with a guest token whose RLS is built from the app user's attributes."""
import os
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
    session["user"] = request.json["user"]
    return jsonify(ok=True)


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
    body = {"user": {"username": uname, "first_name": user["name"], "last_name": ""},
            "resources": [{"type": "dashboard", "id": uuid}], "rls": rls}
    r = s.post(f"{SUPERSET}/api/v1/security/guest_token/", json=body)
    r.raise_for_status()
    return jsonify(token=r.json()["token"], rls=rls)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
