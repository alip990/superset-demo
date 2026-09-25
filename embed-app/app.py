"""Host application demo: logs its own users in, then embeds a Superset dashboard
in an iframe with a guest token scoped to the user's company and every company below
it in the company tree (see SUPERSET_RLS_GUIDE.md)."""
import os
import psycopg2
import requests
from flask import Flask, jsonify, render_template, request, session

SUPERSET = os.environ.get("SUPERSET_URL", "http://superset:8088")
SUPERSET_PUBLIC = os.environ.get("SUPERSET_PUBLIC_URL", "http://localhost:8088")
DASHBOARD_SLUG = os.environ.get("EMBED_DASHBOARD_SLUG", "traffic-fa-embedded")
# database holding the company tree (bi.company in the restored backup)
COMPANY_DB = os.environ.get("COMPANY_DB_URL",
                            "postgresql://bi_reader:bi_reader@backup-db:5432/CrimeManagementDb")

# Users of *our* application and their primary company (would come from your IAM / DB)
APP_USERS = {
    "police_national": {"name": "پلیس راهور کل کشور", "company_id": 1346026935875735552},
    "police_qom": {"name": "پلیس راهور استان قم", "company_id": 1346027341989220352},
    "police_tehran": {"name": "پلیس راهور استان تهران", "company_id": 1346027517705392128},
}
DEFAULT_USER = "police_qom"

# the user's company plus all of its descendants
COMPANY_TREE_SQL = """
WITH RECURSIVE company_tree AS (
    SELECT company_id AS id, parent_id FROM bi.company WHERE company_id = %(user_company_id)s
    UNION ALL
    SELECT c.company_id, c.parent_id FROM bi.company c
    INNER JOIN company_tree ct ON c.parent_id = ct.id
)
SELECT id FROM company_tree ORDER BY id
"""

app = Flask(__name__, template_folder=".")
app.secret_key = "host-app-demo"


def allowed_companies(company_id):
    """Flatten the company tree under company_id into "2, 3, 5"."""
    with psycopg2.connect(COMPANY_DB) as conn, conn.cursor() as cur:
        cur.execute(COMPANY_TREE_SQL, {"user_company_id": company_id})
        return ", ".join(str(row[0]) for row in cur.fetchall())


def superset_session():
    s = requests.Session()
    tok = s.post(f"{SUPERSET}/api/v1/security/login",
                 json={"username": "admin", "password": "admin", "provider": "db"}).json()["access_token"]
    s.headers["Authorization"] = f"Bearer {tok}"
    s.headers["X-CSRFToken"] = s.get(f"{SUPERSET}/api/v1/security/csrf_token/").json()["result"]
    s.headers["Referer"] = SUPERSET
    return s


def embedded_uuid(s):
    return s.get(f"{SUPERSET}/api/v1/dashboard/{DASHBOARD_SLUG}/embedded").json()["result"]["uuid"]


@app.get("/")
def index():
    return render_template("index.html", users=APP_USERS, current=session.get("user", DEFAULT_USER),
                           dashboard_uuid=embedded_uuid(superset_session()), superset_url=SUPERSET_PUBLIC)


@app.post("/login")
def login():
    session["user"] = request.json["user"]
    return jsonify(ok=True)


@app.get("/guest-token")
def guest_token():
    uname = session.get("user", DEFAULT_USER)
    user = APP_USERS[uname]
    allowed = allowed_companies(user["company_id"])
    s = superset_session()
    body = {
        # Superset 6.1 drops user.attributes, so the ids ride in the username;
        # superset_config.get_guest_user_attribute('allowed_companies') unpacks them
        "user": {"username": f"{uname}|{allowed}", "first_name": user["name"], "last_name": ""},
        "resources": [{"type": "dashboard", "id": embedded_uuid(s)}],
        "rls": [],  # tenant filtering happens in the virtual datasets, not here
    }
    r = s.post(f"{SUPERSET}/api/v1/security/guest_token/", json=body)
    r.raise_for_status()
    return jsonify(token=r.json()["token"], allowed_companies=allowed)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
