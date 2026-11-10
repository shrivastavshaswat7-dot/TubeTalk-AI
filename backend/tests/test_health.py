from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json() == {"message": "TubeTalk AI Backend is running"}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy", "application": "TubeTalk AI"}


def test_unknown_route_uses_error_format():
    r = client.get("/nope")
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False and body["error"] == "NOT_FOUND"


def test_config_diagnostic_endpoint_is_not_public():
    assert client.get("/health/config").status_code == 404


def test_cors_allows_configured_origin():
    r = client.get("/health", headers={"Origin": "http://localhost:8501"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8501"
