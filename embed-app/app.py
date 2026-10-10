"""Host application: pick an application user and one company in their subtree,
then embed the traffic dashboard. The guest token carries no RLS clause.
Allowed company ids are packed into the username; the virtual dataset reads
them with get_guest_user_attribute('allowed_companies')."""
import os
import psycopg2
import requests
from flask import Flask, jsonify, render_template, request, session

SUPERSET = os.environ.get("SUPERSET_URL", "http://superset:8088")
SUPERSET_PUBLIC = os.environ.get("SUPERSET_PUBLIC_URL", "http://localhost:8088")
DASHBOARD_SLUG = os.environ.get("EMBED_DASHBOARD_SLUG", "traffic-fa-embedded")
COMPANY_DB = os.environ.get(
    "COMPANY_DB_URL",
    "postgresql://bi_reader:bi_reader@backup-db:5432/CrimeManagementDb",
)
ADMIN = "__admin__"

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
app.config["SESSION_COOKIE_NAME"] = "embed_app_session"


def query(sql, params=None):
    with psycopg2.connect(COMPANY_DB) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def app_users():
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
    """Companies this user may pick, or None when the username is not a known user."""
    if username == ADMIN:
        return [c for root in query("SELECT company_id FROM bi.company WHERE parent_id IS NULL")
                for c in company_subtree(root[0])]
    rows = query("SELECT company_id FROM bi.app_user WHERE username = %s AND activated", (username,))
    if not rows:
        return None
    return company_subtree(rows[0][0])


def current_selection():
    username = session.get("user", ADMIN)
    companies = selectable_companies(username)
    if companies is None:
        username = ADMIN
        companies = selectable_companies(username) or []
    allowed = {c["id"] for c in companies}
    company = session.get("company")
    if company not in allowed:
        company = companies[0]["id"] if companies else None
    return username, company


def superset_session():
    s = requests.Session()
    tok = s.post(f"{SUPERSET}/api/v1/security/login",
                 json={"username": "admin", "password": "admin", "provider": "db"}, timeout=30).json()["access_token"]
    s.headers["Authorization"] = f"Bearer {tok}"
    s.headers["X-CSRFToken"] = s.get(f"{SUPERSET}/api/v1/security/csrf_token/", timeout=30).json()["result"]
    s.headers["Referer"] = SUPERSET
    return s


def embedded_uuid(s):
    return s.get(f"{SUPERSET}/api/v1/dashboard/{DASHBOARD_SLUG}/embedded", timeout=30).json()["result"]["uuid"]


@app.get("/healthz")
def healthz():
    return jsonify(ok=True)


@app.get("/")
def index():
    username, company = current_selection()
    return render_template(
        "index.html", users=app_users(), admin=ADMIN, current_user=username,
        companies=selectable_companies(username) or [], current_company=company,
        dashboard_uuid=embedded_uuid(superset_session()), superset_url=SUPERSET_PUBLIC,
    )


@app.get("/companies")
def companies():
    username = request.args.get("user")
    if not isinstance(username, str) or not username:
        return jsonify(error="Unknown user"), 400
    rows = selectable_companies(username)
    if rows is None:
        return jsonify(error="Unknown user"), 400
    return jsonify(companies=[{**c, "id": str(c["id"])} for c in rows])


@app.post("/login")
def login():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("user"), str) or not body["user"]:
        return jsonify(error="Unknown user"), 400
    username = body["user"]
    allowed_rows = selectable_companies(username)
    if allowed_rows is None:
        return jsonify(error="Unknown user"), 400
    allowed = {c["id"] for c in allowed_rows}
    company = body.get("company")
    session["user"] = username
    try:
        chosen = int(company) if company not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify(error="Unknown company"), 400
    session["company"] = chosen if chosen in allowed else None
    return jsonify(ok=True)


@app.get("/guest-token")
def guest_token():
    username, company = current_selection()
    allowed = ", ".join(str(c["id"]) for c in company_subtree(company))
    s = superset_session()
    body = {
        "user": {"username": f"{username}|{allowed}", "first_name": username, "last_name": ""},
        "resources": [{"type": "dashboard", "id": embedded_uuid(s)}],
        "rls": [],
    }
    r = s.post(f"{SUPERSET}/api/v1/security/guest_token/", json=body, timeout=30)
    r.raise_for_status()
    return jsonify(token=r.json()["token"], rls=[], allowed_companies=allowed or "—")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090, threaded=True)
