"""Compare embedded guest queries with read-only business SQL, including map aggregation."""
import os
import json
import requests
import psycopg2

HOST = os.environ.get("HOST_URL", "http://embed-app:8090")
SS = os.environ.get("SUPERSET_URL", "http://superset:8088")
DSN = os.environ.get("DEMO_DSN", "postgresql://demo_reader:demo_reader@db:5432/demo")


def checked(response):
    response.raise_for_status()
    return response.json()


def run():
    admin = requests.Session()
    token = checked(admin.post(SS + "/api/v1/security/login", json={"username": "admin", "password": "admin", "provider": "db"}, timeout=30))["access_token"]
    admin.headers["Authorization"] = "Bearer " + token
    csrf = checked(admin.get(SS + "/api/v1/security/csrf_token/", timeout=30))["result"]
    datasets = checked(admin.get(SS + "/api/v1/dataset/", params={"q": json.dumps({"page_size": 100})}, timeout=30))["result"]
    ids = {d["table_name"]: d["id"] for d in datasets}

    def query(name, columns, expr, guest_token):
        body = {"datasource": {"id": ids[name], "type": "table"}, "force": False,
                "queries": [{"columns": columns, "metrics": [{"expressionType": "SQL", "sqlExpression": expr, "label": "total"}],
                             "row_limit": 10000, "time_range": "No filter", "filters": [], "extras": {"where": "", "having": ""}}],
                "result_format": "json", "result_type": "full"}
        result = checked(requests.post(SS + "/api/v1/chart/data", json=body, headers={"X-GuestToken": guest_token, "X-CSRFToken": csrf, "Referer": SS}, timeout=120))["result"][0]
        assert result["status"] == "success", result
        return result

    host = requests.Session()
    checked(host.post(HOST + "/login", json={"user": "ali_north"}, timeout=30))
    north = checked(host.get(HOST + "/guest-token", timeout=30))
    assert north["rls"] == [{"clause": "region IN ('north')"}]
    assert set(north) == {"token", "rls"}
    with psycopg2.connect(DSN) as db, db.cursor() as c:
        c.execute("SELECT SUM(amount) FROM sales WHERE region='north'")
        regional = float(c.fetchone()[0])
        assert float(query("sales_jalali", [], "SUM(amount)", north["token"])["data"][0]["total"]) == regional
        assert float(query("sales_by_branch", [], "SUM(total_amount)", north["token"])["data"][0]["total"]) == regional
        checked(host.post(HOST + "/login", json={"user": "manager"}, timeout=30))
        guest = checked(host.get(HOST + "/guest-token", timeout=30))
        assert guest["rls"] == []
        c.execute("SELECT SUM(amount) FROM sales")
        assert float(query("sales_jalali", [], "SUM(amount)", guest["token"])["data"][0]["total"]) == float(c.fetchone()[0])
    print("SMOKE_OK: region-only guest RLS for ali_north and manager, jalali total, and map")


if __name__ == "__main__":
    run()
