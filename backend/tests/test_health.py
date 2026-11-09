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


REQUIRED = ("GROQ_API_KEY", "GROQ_MODEL", "SUPABASE_URL", "SUPABASE_KEY")


def _clear(monkeypatch):
    for name in REQUIRED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.core.config.Settings.model_config", {"env_file": None, "extra": "ignore"})


def test_config_check_reports_booleans_only_and_never_values(monkeypatch):
    _clear(monkeypatch)
    secret = "dummy-secret-value-123"
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", secret)
    r = client.get("/health/config")
    assert r.status_code == 200
    report = r.json()["variables"]
    assert set(report) == set(REQUIRED)
    for flags in report.values():
        assert all(isinstance(v, bool) for v in flags.values())
    assert report["SUPABASE_KEY"] == {"present": True, "non_empty": True, "loaded_by_settings": True,
                                      "near_miss_name": False, "secret_file": False}
    assert report["GROQ_MODEL"]["present"] is False and report["GROQ_MODEL"]["loaded_by_settings"] is False
    assert secret not in r.text and "example.supabase.co" not in r.text


def test_config_check_flags_empty_values_and_near_miss_names(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SUPABASE_URL", "   ")
    monkeypatch.setenv("SUPABASE_KEY ", "dummy")  # trailing space in the name
    monkeypatch.setenv("GROQ_MODEL​", "dummy")  # invisible character in the name
    report = client.get("/health/config").json()["variables"]
    assert report["SUPABASE_URL"]["present"] is True and report["SUPABASE_URL"]["non_empty"] is False
    assert report["SUPABASE_KEY"]["present"] is False and report["SUPABASE_KEY"]["near_miss_name"] is True
    assert report["GROQ_MODEL"]["near_miss_name"] is True


def test_cors_allows_configured_origin():
    r = client.get("/health", headers={"Origin": "http://localhost:8501"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8501"
