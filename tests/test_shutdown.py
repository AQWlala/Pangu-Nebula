"""P0-W0 Graceful shutdown endpoint tests (v2.1.0 Phase 0)

Tests for:
- POST /shutdown endpoint (graceful sidecar shutdown)
  * Returns 200 with {"ok": True, "data": {"shutting_down": True}}
  * Schedules SIGTERM delivery via background daemon thread
  * Requires a valid Bearer token (security hardening — previously whitelisted,
    which allowed an unauthenticated process kill)

Safety: the safe_kill fixture mocks os.kill and waits 0.3s (real time.sleep)
INSIDE the patch context for the background thread to call the mock. This
ensures no real os.kill call slips through after the mock is removed.
"""

import signal
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from server.main import app, settings


@pytest.fixture
def safe_kill():
    """Mock os.kill for /shutdown tests.

    After the test, waits 0.3s INSIDE the patch context for the background
    daemon thread to call the mocked os.kill. The thread sleeps 0.1s before
    killing, so 0.3s gives ample margin. The mock is only removed after the
    thread has finished, preventing real SIGTERM delivery.
    """
    with patch("os.kill") as mock_kill:
        yield mock_kill
        # Still inside with block — os.kill is still mocked. Wait for the
        # background thread (0.1s real sleep + mocked os.kill) to complete.
        time.sleep(0.3)


def test_shutdown_returns_200(test_client: TestClient, safe_kill):
    """POST /shutdown returns HTTP 200"""
    response = test_client.post("/shutdown")
    assert response.status_code == 200


def test_shutdown_returns_shutting_down(test_client: TestClient, safe_kill):
    """Response body confirms shutdown is in progress"""
    response = test_client.post("/shutdown")
    data = response.json()
    assert data["ok"] is True
    assert data["data"]["shutting_down"] is True
    assert data["error"] is None


def test_shutdown_schedules_sigterm(test_client: TestClient, safe_kill):
    """ /shutdown spawns a background thread that calls os.kill(pid, SIGTERM)
    after a 0.1s delay. We verify the mock was called with SIGTERM."""
    response = test_client.post("/shutdown")
    assert response.status_code == 200

    # The fixture's teardown (time.sleep(0.3)) waits for the background
    # thread to call os.kill. After fixture teardown, check the mock.
    # But we can also poll here for faster feedback.
    for _ in range(50):  # up to 0.5s
        if safe_kill.called:
            break
        time.sleep(0.01)

    assert safe_kill.called, "os.kill was not called within 0.5s"
    call_args = safe_kill.call_args
    # os.kill(pid, signal) — second positional arg should be SIGTERM
    assert call_args[0][1] == signal.SIGTERM


def test_shutdown_requires_auth(test_client: TestClient, monkeypatch, safe_kill):
    """ /shutdown requires a valid Bearer token. Previously it was whitelisted
    from Bearer token auth, which allowed an unauthenticated process kill — a
    security risk. Verify it is now rejected without a token and accepted with
    a valid one."""
    monkeypatch.setattr(settings, "sidecar_token", "secret-token-123", raising=False)

    # Without a Bearer token, /shutdown must be rejected (security fix).
    response = test_client.post("/shutdown")
    assert response.status_code == 401

    # With a valid Bearer token, /shutdown proceeds normally.
    response = test_client.post(
        "/shutdown",
        headers={"Authorization": "Bearer secret-token-123"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
