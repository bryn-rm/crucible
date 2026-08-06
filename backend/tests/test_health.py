from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_environments_empty() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/environments")
    assert resp.status_code == 200
    assert resp.json() == []
