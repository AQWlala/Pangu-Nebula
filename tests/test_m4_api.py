# tests/test_m4_api.py
import json
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from server.main import app
import server.api.cu as cu_module


@pytest.fixture(autouse=True)
def reset_cu_singletons():
    """Reset module-level singletons in server.api.cu to prevent test leakage.

    Clears the _tasks dict, resets the _emergency_stop flag, and drops the
    _executor singleton so each test starts from a clean state. Without this,
    test_cu_emergency_stop would leave _emergency_stop triggered and pollute
    later tests that go through the executor.
    """
    cu_module._tasks.clear()
    cu_module._emergency_stop.reset()
    cu_module._executor = None
    yield


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_cu_create_task(client):
    response = await client.post("/api/cu/tasks", json={
        "instruction": "访问 example.com",
        "steps": [{"action_type": "browser_navigate",
                   "action_payload": {"url": "https://example.com"},
                   "success_criteria": {"url_contains": "example.com"}}],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "task_id" in data
    assert data["step_count"] == 1


@pytest.mark.asyncio
async def test_cu_emergency_stop(client):
    response = await client.post("/api/cu/emergency-stop", json={"reason": "test"})
    assert response.status_code == 200
    assert response.json()["success"] is True
    # Verify the stop was actually triggered on the module-level singleton
    assert cu_module._emergency_stop.is_triggered()
    assert cu_module._emergency_stop.reason == "test"


@pytest.mark.asyncio
async def test_cu_get_task_status(client):
    create_resp = await client.post("/api/cu/tasks", json={
        "instruction": "test",
        "steps": [{"action_type": "browser_navigate",
                   "action_payload": {"url": "https://example.com"},
                   "success_criteria": {"url_contains": "example"}}],
    })
    task_id = create_resp.json()["task_id"]
    response = await client.get(f"/api/cu/tasks/{task_id}/status")
    assert response.status_code == 200
    assert response.json()["task_id"] == task_id


@pytest.mark.asyncio
async def test_cu_list_tasks(client):
    response = await client.get("/api/cu/tasks")
    assert response.status_code == 200
    assert "tasks" in response.json()


@pytest.mark.asyncio
async def test_cu_execute_task(client):
    """POST /api/cu/tasks/{id}/execute — successful execution (mocked)."""
    create_resp = await client.post("/api/cu/tasks", json={
        "instruction": "test execute",
        "steps": [{"action_type": "browser_navigate",
                   "action_payload": {"url": "https://example.com"},
                   "success_criteria": {"url_contains": "example"}}],
    })
    task_id = create_resp.json()["task_id"]

    mock_result = {"task_id": task_id, "status": "completed",
                   "executed_steps": 1, "results": []}
    with patch("server.api.cu.CUExecutor.run_task", return_value=mock_result):
        response = await client.post(f"/api/cu/tasks/{task_id}/execute")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["task_id"] == task_id
    assert data["status"] == "completed"
    assert data["executed_steps"] == 1


@pytest.mark.asyncio
async def test_cu_rollback_task(client):
    """POST /api/cu/tasks/{id}/rollback — successful rollback (mocked)."""
    create_resp = await client.post("/api/cu/tasks", json={
        "instruction": "test rollback",
        "steps": [{"action_type": "browser_navigate",
                   "action_payload": {"url": "https://example.com"},
                   "success_criteria": {"url_contains": "example"}}],
    })
    task_id = create_resp.json()["task_id"]

    mock_result = {"success": True, "rolled_back_count": 1,
                   "skipped_count": 0, "errors": []}
    with patch("server.api.cu.CUExecutor.rollback_task", return_value=mock_result):
        response = await client.post(f"/api/cu/tasks/{task_id}/rollback")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["rolled_back_count"] == 1
    # Rollback success should update task status
    assert cu_module._tasks[task_id]["status"] == "rolled_back"


@pytest.mark.asyncio
async def test_cu_get_audit_log(client, tmp_path):
    """GET /api/cu/tasks/{id}/audit-log — returns audit entries."""
    from server.config_kb_cu import CUConfig

    create_resp = await client.post("/api/cu/tasks", json={
        "instruction": "test audit log",
        "steps": [{"action_type": "browser_navigate",
                   "action_payload": {"url": "https://example.com"},
                   "success_criteria": {"url_contains": "example"}}],
    })
    task_id = create_resp.json()["task_id"]

    # Write a real audit log entry under tmp_path to avoid touching the home dir
    audit_dir = tmp_path / "audit"
    log_file = audit_dir / task_id / "audit.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_entry = {
        "task_id": task_id,
        "step_index": 0,
        "action_type": "browser_navigate",
        "action_payload": {"url": "https://example.com"},
        "result_status": "success",
        "result_data": {},
        "screenshot_path": None,
        "duration_ms": 100,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "prev_hash": "",
        "hash": "abc123",
    }
    log_file.write_text(json.dumps(log_entry) + "\n", encoding="utf-8")

    mock_config = CUConfig(audit_log_dir=audit_dir)
    with patch("server.api.cu._get_config", return_value=mock_config):
        response = await client.get(f"/api/cu/tasks/{task_id}/audit-log")

    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == task_id
    assert len(data["logs"]) >= 1
    assert data["logs"][0]["action_type"] == "browser_navigate"


@pytest.mark.asyncio
async def test_cu_reset_emergency_stop(client):
    """POST /api/cu/emergency-stop/reset — resets a triggered emergency stop."""
    # First trigger emergency stop
    trigger_resp = await client.post("/api/cu/emergency-stop", json={"reason": "test"})
    assert trigger_resp.status_code == 200
    assert cu_module._emergency_stop.is_triggered()

    # Then reset
    response = await client.post("/api/cu/emergency-stop/reset")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert not cu_module._emergency_stop.is_triggered()


@pytest.mark.asyncio
async def test_cu_execute_task_not_found(client):
    """POST /api/cu/tasks/nonexistent/execute → 404."""
    response = await client.post("/api/cu/tasks/nonexistent/execute")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cu_rollback_task_not_found(client):
    """POST /api/cu/tasks/nonexistent/rollback → 404."""
    response = await client.post("/api/cu/tasks/nonexistent/rollback")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cu_audit_log_nonexistent_task(client, tmp_path):
    """GET /api/cu/tasks/nonexistent/audit-log — returns empty logs for unknown task.

    Note: unlike execute/rollback, the audit-log endpoint does not check task
    existence in _tasks and therefore returns 200 with an empty log list rather
    than 404. This test documents the actual behavior.
    """
    from server.config_kb_cu import CUConfig

    mock_config = CUConfig(audit_log_dir=tmp_path / "audit")
    with patch("server.api.cu._get_config", return_value=mock_config):
        response = await client.get("/api/cu/tasks/nonexistent/audit-log")

    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "nonexistent"
    assert data["logs"] == []


def test_mcp_tools_definition():
    from server.cu.mcp_tools import MCP_TOOLS
    assert len(MCP_TOOLS) == 6
    names = [t["name"] for t in MCP_TOOLS]
    assert "cu_plan_task" in names
    assert "cu_emergency_stop" in names
