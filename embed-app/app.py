"""Host app: pick a real backup user and one company in their subtree, then embed
the traffic dashboard. The guest token carries no row filter of its own.
Allowed company ids are packed into the username and read by
get_guest_user_attribute('allowed_companies').

Users and companies are the 1 May tables um."User" and um."Company"
(exposed in CrimeManagementDb as foreign tables). This app does not copy them.
"""
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
    SELECT "Id" AS id, "ParentId" AS parent_id, 0 AS level
    FROM um_src."Company"
    WHERE "Id" = %(user_company_id)s AND NOT "Deleted"
    UNION ALL
    SELECT c."Id", c."ParentId", ct.level + 1
    FROM um_src."Company" c
    INNER JOIN company_tree ct ON c."ParentId" = ct.id
    WHERE NOT c."Deleted"
)
SELECT ct.id, c."Title", ct.level
FROM company_tree ct
JOIN um_src."Company" c ON c."Id" = ct.id
ORDER BY ct.level, c."Title"
"""

app = Flask(__name__, template_folder=".")
app.secret_key = "host-app-demo"
app.config["SESSION_COOKIE_NAME"] = "embed_app_session"


def query(sql, params=None):
    with psycopg2.connect(COMPANY_DB) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def app_users():
    rows = query("""
        SELECT u."UserName", u."FirstName" || ' ' || u."LastName", ua."CompanyId",
               coalesce(c."Title", 'بدون شرکت')
        FROM um_src."User" u
        LEFT JOIN um_src."UserAttribute" ua ON ua."UserId" = u."Id" AND NOT ua."Deleted"
        LEFT JOIN um_src."Company" c ON c."Id" = ua."CompanyId" AND NOT c."Deleted"
        WHERE NOT u."Deleted" AND u."Activated"
        ORDER BY c."Depth" NULLS LAST, c."Title", u."UserName"
    """)
    return [{"username": u, "name": n, "company_id": cid, "company": ct} for u, n, cid, ct in rows]


def company_subtree(company_id):
    if company_id is None:
        return []
    return [{"id": cid, "title": title, "level": level}
            for cid, title, level in query(COMPANY_TREE_SQL, {"user_company_id": company_id})]


def selectable_companies(username):
    if username == ADMIN:
        roots = query('SELECT "Id" FROM um_src."Company" WHERE "ParentId" IS NULL AND NOT "Deleted"')
        return [company for (root,) in roots for company in company_subtree(root)]
    rows = query("""
        SELECT ua."CompanyId"
        FROM um_src."User" u
        LEFT JOIN um_src."UserAttribute" ua ON ua."UserId" = u."Id" AND NOT ua."Deleted"
        WHERE u."UserName" = %s AND NOT u."Deleted" AND u."Activated"
    """, (username,))
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
