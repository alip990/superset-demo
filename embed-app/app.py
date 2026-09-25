"""Host application demo: pick an application user (and optionally one of the companies
they may see), then embed a Superset dashboard with a guest token scoped to that company
and every company below it in the company tree (see SUPERSET_RLS_GUIDE.md)."""
import os
import psycopg2
import requests
from flask import Flask, abort, jsonify, render_template, request, session

SUPERSET = os.environ.get("SUPERSET_URL", "http://superset:8088")
SUPERSET_PUBLIC = os.environ.get("SUPERSET_PUBLIC_URL", "http://localhost:8088")
DASHBOARD_SLUG = os.environ.get("EMBED_DASHBOARD_SLUG", "traffic-fa-embedded")
# users (bi.app_user) and company tree (bi.company) from the restored backup
COMPANY_DB = os.environ.get("COMPANY_DB_URL",
                            "postgresql://bi_reader:bi_reader@backup-db:5432/CrimeManagementDb")
# pseudo user of the demo: may pick any company directly
ADMIN = "__admin__"

# the company plus all of its descendants; depth for indenting the dropdown
COMPANY_TREE_SQL = """
WITH RECURSIVE company_tree AS (
    SELECT company_id AS id, parent_id, 0 AS level FROM bi.company WHERE company_id = %(user_company_id)s
    UNION ALL
    SELECT c.company_id, c.parent_id, ct.level + 1 FROM bi.company c
    INNER JOIN company_tree ct ON c.parent_id = ct.id
)
SELECT ct.id, c.title, ct.level FROM company_tree ct JOIN bi.company c ON c.company_id = ct.id
ORDER BY ct.level, c.title
"""

app = Flask(__name__, template_folder=".")
app.secret_key = "host-app-demo"


def query(sql, params=None):
    with psycopg2.connect(COMPANY_DB) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def app_users():
    """Activated users, grouped by company in the dropdown."""
    rows = query("""SELECT a.username, a.full_name, a.company_id, coalesce(c.title, 'بدون شرکت')
                    FROM bi.app_user a LEFT JOIN bi.company c USING (company_id)
                    WHERE a.activated ORDER BY c.depth NULLS LAST, c.title, a.username""")
    return [{"username": u, "name": n, "company_id": cid, "company": ct} for u, n, cid, ct in rows]


def company_subtree(company_id):
    if company_id is None:
        return []
    return [{"id": cid, "title": t, "level": lvl}
            for cid, t, lvl in query(COMPANY_TREE_SQL, {"user_company_id": company_id})]


def selectable_companies(username):
    """Companies the user may pick: their own company and everything below it."""
    if username == ADMIN:
        return [c for root in query("SELECT company_id FROM bi.company WHERE parent_id IS NULL")
                for c in company_subtree(root[0])]
    rows = query("SELECT company_id FROM bi.app_user WHERE username = %s AND activated", (username,))
    if not rows:
        abort(404, "unknown user")
    return company_subtree(rows[0][0])


def current_selection():
    """(username, company_id) from the session, company validated against the user's subtree."""
    username = session.get("user", ADMIN)
    allowed = {c["id"] for c in selectable_companies(username)}
    company = session.get("company")
    if company not in allowed:  # none picked yet (or stale): default to the user's top company
        companies = selectable_companies(username)
        company = companies[0]["id"] if companies else None
    return username, company


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
    username, company = current_selection()
    return render_template("index.html", users=app_users(), admin=ADMIN, current_user=username,
                           companies=selectable_companies(username), current_company=company,
                           dashboard_uuid=embedded_uuid(superset_session()), superset_url=SUPERSET_PUBLIC)


@app.get("/companies")
def companies():
    """Dropdown options for a user; the first one (their own company) is the default."""
    return jsonify(companies=[{**c, "id": str(c["id"])} for c in selectable_companies(request.args["user"])])


@app.post("/login")
def login():
    """Select the app user and (optionally) one of the companies they may see."""
    username = request.json["user"]
    company = request.json.get("company")
    allowed = {c["id"] for c in selectable_companies(username)}
    session["user"] = username
    session["company"] = int(company) if company and int(company) in allowed else None
    return jsonify(ok=True)


@app.get("/guest-token")
def guest_token():
    username, company = current_selection()
    allowed = ", ".join(str(c["id"]) for c in company_subtree(company))
    s = superset_session()
    body = {
        # Superset 6.1 drops user.attributes, so the ids ride in the username;
        # superset_config.get_guest_user_attribute('allowed_companies') unpacks them.
        # No company -> "user|" -> the datasets' failsafe returns no rows.
        "user": {"username": f"{username}|{allowed}", "first_name": username, "last_name": ""},
        "resources": [{"type": "dashboard", "id": embedded_uuid(s)}],
        "rls": [],  # tenant filtering happens in the virtual datasets, not here
    }
    r = s.post(f"{SUPERSET}/api/v1/security/guest_token/", json=body)
    r.raise_for_status()
    return jsonify(token=r.json()["token"], allowed_companies=allowed or "—")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
