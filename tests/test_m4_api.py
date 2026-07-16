# tests/test_m4_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from server.main import app


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


def test_mcp_tools_definition():
    from server.cu.mcp_tools import MCP_TOOLS
    assert len(MCP_TOOLS) == 6
    names = [t["name"] for t in MCP_TOOLS]
    assert "cu_plan_task" in names
    assert "cu_emergency_stop" in names
