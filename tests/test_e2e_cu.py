# tests/test_e2e_cu.py
"""T5 — CU 全链路端到端集成测试

验证 Computer Use 任务的完整生命周期：
  create → execute → audit-log → rollback

关键约束：
- 使用 tmp_path fixture，绝不写入用户 home 目录。
- 通过构造器模式创建 CUConfig(audit_log_dir=tmp_path / "audit")。
- Monkeypatch server.api.cu._executor 使其使用测试配置的执行器。
- Monkeypatch server.cu.executor.runner.KBConfig 防止知识桥接写入用户目录。
"""
import pytest
from httpx import AsyncClient, ASGITransport

from server.main import app
from server.config_kb_cu import CUConfig, KBConfig
from server.cu.executor.runner import CUExecutor
from server.cu.safety.emergency_stop import EmergencyStop


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def cu_env(tmp_path, monkeypatch):
    """Set up CU executor + config pointing to tmp_path.

    - Replaces the module-level _executor singleton with a test executor
      whose audit_log_dir lives under tmp_path.
    - Patches _get_config so the audit-log endpoint reads from tmp_path.
    - Patches KBConfig in the runner module so _generate_knowledge does
      not create a default KBConfig pointing to the user home directory.
    """
    cu_config = CUConfig(audit_log_dir=tmp_path / "audit")
    cu_config.ensure_dirs()
    kb_config = KBConfig(kb_root=tmp_path / "kb")
    kb_config.ensure_dirs()

    import server.api.cu as cu_module
    import server.cu.executor.runner as runner_module

    es = EmergencyStop()
    executor = CUExecutor(config=cu_config, emergency_stop=es)
    # Replace the module-level singleton so _get_executor() returns our instance
    monkeypatch.setattr(cu_module, "_executor", executor)
    # Replace _get_config so the audit-log endpoint uses tmp_path
    monkeypatch.setattr(cu_module, "_get_config", lambda: cu_config)
    # Prevent _generate_knowledge from creating a default KBConfig pointing to ~
    monkeypatch.setattr(runner_module, "KBConfig", lambda *a, **kw: kb_config)

    return {"cu_config": cu_config, "kb_config": kb_config, "executor": executor}


@pytest.mark.asyncio
async def test_cu_full_flow_create_execute_audit_rollback(client, cu_env, tmp_path):
    """CU 全链路：create → execute → audit-log → rollback。"""
    target_file = tmp_path / "output.txt"

    # ------------------------------------------------------------------
    # Step 1: POST /api/cu/tasks — 创建任务
    # ------------------------------------------------------------------
    create_resp = await client.post("/api/cu/tasks", json={
        "instruction": "写入测试文件",
        "steps": [{
            "action_type": "fs_write",
            "action_payload": {
                "path": str(target_file),
                "content": "hello from CU",
            },
            "success_criteria": {"url_contains": ""},
        }],
    })
    assert create_resp.status_code == 200, create_resp.text
    create_data = create_resp.json()
    assert create_data["success"] is True
    task_id = create_data["task_id"]
    assert create_data["step_count"] == 1

    # ------------------------------------------------------------------
    # Step 2: POST /api/cu/tasks/{id}/execute — 执行任务
    # ------------------------------------------------------------------
    exec_resp = await client.post(f"/api/cu/tasks/{task_id}/execute")
    assert exec_resp.status_code == 200, exec_resp.text
    exec_data = exec_resp.json()
    assert exec_data["success"] is True
    assert exec_data["task_id"] == task_id
    assert exec_data["status"] == "completed", \
        f"任务应执行完成，实际状态: {exec_data['status']}"
    assert exec_data["executed_steps"] == 1

    # ------------------------------------------------------------------
    # Step 3: GET /api/cu/tasks/{id}/audit-log — 验证审计条目存在
    # ------------------------------------------------------------------
    audit_resp = await client.get(f"/api/cu/tasks/{task_id}/audit-log")
    assert audit_resp.status_code == 200, audit_resp.text
    audit_data = audit_resp.json()
    assert audit_data["task_id"] == task_id
    logs = audit_data["logs"]
    assert len(logs) >= 1, f"应至少有 1 条审计记录，实际 {len(logs)}"
    assert logs[0]["action_type"] == "fs_write"
    assert logs[0]["result_status"] == "success"
    assert logs[0]["step_index"] == 0

    # ------------------------------------------------------------------
    # Step 4: POST /api/cu/tasks/{id}/rollback — 回滚
    # ------------------------------------------------------------------
    rollback_resp = await client.post(f"/api/cu/tasks/{task_id}/rollback")
    assert rollback_resp.status_code == 200, rollback_resp.text
    rollback_data = rollback_resp.json()
    assert rollback_data["success"] is True
    # fs_write is reversible (rollback_action = fs_delete), so it should be rolled back
    assert rollback_data["rolled_back_count"] >= 1, \
        f"fs_write 应被回滚，rolled_back_count={rollback_data['rolled_back_count']}"

    # ------------------------------------------------------------------
    # Step 5: 验证任务状态已变为 rolled_back
    # ------------------------------------------------------------------
    status_resp = await client.get(f"/api/cu/tasks/{task_id}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "rolled_back"


@pytest.mark.asyncio
async def test_cu_task_not_found_returns_404(client, cu_env):
    """不存在的 task_id 应返回 404。"""
    resp = await client.get("/api/cu/tasks/cutask-nonexistent-00000000/audit-log")
    # audit-log endpoint returns empty logs for unknown task_id (no 404),
    # but execute/rollback/status should 404
    exec_resp = await client.post("/api/cu/tasks/cutask-nonexistent-00000000/execute")
    assert exec_resp.status_code == 404

    rollback_resp = await client.post("/api/cu/tasks/cutask-nonexistent-00000000/rollback")
    assert rollback_resp.status_code == 404

    status_resp = await client.get("/api/cu/tasks/cutask-nonexistent-00000000/status")
    assert status_resp.status_code == 404
