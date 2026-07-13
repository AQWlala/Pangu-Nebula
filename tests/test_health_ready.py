"""P0-W0 Health ready + sidecar token auth middleware tests (v2.1.0 Phase 0)

Tests for:
- GET /health/ready endpoint (readiness probe for Tauri sidecar)
- Bearer token auth middleware (sidecar_token_auth)
  * No-op in pywebview mode (empty token)
  * Enforces Bearer token in tauri mode (non-empty token)
  * Whitelists /health, /health/ready, /shutdown from auth
"""

import time

import pytest
from fastapi.testclient import TestClient

from server.main import app, settings


# ----------------------------------------------------------------------
# /health/ready — readiness probe
# ----------------------------------------------------------------------

def test_health_ready_returns_200(test_client: TestClient):
    """GET /health/ready returns HTTP 200"""
    response = test_client.get("/health/ready")
    assert response.status_code == 200


def test_health_ready_has_required_fields(test_client: TestClient):
    """Response contains status, db_initialized, services_loaded, uptime_seconds"""
    response = test_client.get("/health/ready")
    data = response.json()
    assert "status" in data
    assert "db_initialized" in data
    assert "services_loaded" in data
    assert "uptime_seconds" in data


def test_health_ready_status_starting(test_client: TestClient, monkeypatch):
    """When DB not initialized, status is 'starting'"""
    monkeypatch.setattr(app.state, "db_initialized", False, raising=False)
    monkeypatch.setattr(app.state, "services_loaded", False, raising=False)

    response = test_client.get("/health/ready")
    data = response.json()
    assert data["status"] == "starting"
    assert data["db_initialized"] is False
    assert data["services_loaded"] is False


def test_health_ready_status_ready(test_client: TestClient, monkeypatch):
    """When DB + services loaded, status is 'ready'"""
    monkeypatch.setattr(app.state, "db_initialized", True, raising=False)
    monkeypatch.setattr(app.state, "services_loaded", True, raising=False)
    monkeypatch.setattr(app.state, "start_time", time.time(), raising=False)

    response = test_client.get("/health/ready")
    data = response.json()
    assert data["status"] == "ready"
    assert data["db_initialized"] is True
    assert data["services_loaded"] is True
    assert data["uptime_seconds"] >= 0.0


def test_health_ready_uptime_increases(test_client: TestClient, monkeypatch):
    """uptime_seconds reflects time since start_time"""
    monkeypatch.setattr(app.state, "db_initialized", True, raising=False)
    monkeypatch.setattr(app.state, "services_loaded", True, raising=False)
    # Set start_time 5 seconds in the past
    monkeypatch.setattr(app.state, "start_time", time.time() - 5.0, raising=False)

    response = test_client.get("/health/ready")
    data = response.json()
    assert data["uptime_seconds"] >= 4.0  # at least ~5s minus scheduling delay


# ----------------------------------------------------------------------
# Middleware — Bearer token auth (sidecar_token_auth)
# ----------------------------------------------------------------------

def test_middleware_noop_without_token(test_client: TestClient, monkeypatch):
    """In pywebview mode (empty sidecar_token), all endpoints accessible"""
    monkeypatch.setattr(settings, "sidecar_token", "", raising=False)

    # /health-check is NOT in the auth whitelist, so it's a good probe.
    response = test_client.get("/health-check")
    assert response.status_code == 200


def test_middleware_rejects_unauthorized(test_client: TestClient, monkeypatch):
    """In tauri mode (token set), non-whitelisted endpoints reject without Bearer"""
    monkeypatch.setattr(settings, "sidecar_token", "secret-token-123", raising=False)

    # /health-check is NOT whitelisted (only /health, /health/ready, /shutdown are)
    response = test_client.get("/health-check")
    assert response.status_code == 401
    data = response.json()
    assert data["ok"] is False
    assert "Unauthorized" in data["error"]


def test_middleware_accepts_valid_bearer(test_client: TestClient, monkeypatch):
    """In tauri mode, valid Bearer token grants access to protected endpoints"""
    monkeypatch.setattr(settings, "sidecar_token", "secret-token-123", raising=False)

    response = test_client.get(
        "/health-check",
        headers={"Authorization": "Bearer secret-token-123"},
    )
    assert response.status_code == 200


def test_middleware_rejects_invalid_bearer(test_client: TestClient, monkeypatch):
    """In tauri mode, wrong Bearer token is rejected with 401"""
    monkeypatch.setattr(settings, "sidecar_token", "secret-token-123", raising=False)

    response = test_client.get(
        "/health-check",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


def test_health_ready_bypasses_auth(test_client: TestClient, monkeypatch):
    """ /health/ready is whitelisted from Bearer token auth (Tauri polls it
    before the frontend has injected the token)"""
    monkeypatch.setattr(settings, "sidecar_token", "secret-token-123", raising=False)
    monkeypatch.setattr(app.state, "db_initialized", True, raising=False)
    monkeypatch.setattr(app.state, "services_loaded", True, raising=False)
    monkeypatch.setattr(app.state, "start_time", time.time(), raising=False)

    response = test_client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
