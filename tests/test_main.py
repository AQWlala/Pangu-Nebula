import pytest
from fastapi.testclient import TestClient

from server.main import app, settings


def test_health_check(test_client: TestClient):
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_headers(test_client: TestClient):
    response = test_client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in ("*", "http://localhost:3000")


def test_settings_defaults():
    assert settings.server_port == 7860
    assert settings.db_path == "data/nebula.db"
    assert settings.debug is True
