import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("host", Path(__file__).parents[1] / "embed-app/app.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def test_login_rejects_unknown_users():
    assert host.app.config["SESSION_COOKIE_NAME"] == "embed_app_session"
    with host.app.test_client() as client:
        assert client.post("/login", json={"user": ""}).status_code == 400
        assert client.post("/login", json={}).status_code == 400
        assert client.post("/login", json=[]).status_code == 400
        assert client.get("/companies").status_code == 400


def test_healthz():
    with host.app.test_client() as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json == {"ok": True}


def test_embed_app_has_no_date_filtering():
    root = Path(__file__).parents[1] / "embed-app"
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(errors="ignore")
        assert "sale_date" not in text, path
        assert "superset_jalali_sql" not in text, path
