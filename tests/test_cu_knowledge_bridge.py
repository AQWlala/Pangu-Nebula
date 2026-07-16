# tests/test_cu_knowledge_bridge.py
"""A5 - CUKnowledgeBridge 接入执行器与 InboxWriter 的集成测试。

覆盖三条主线：
1. CUKnowledgeBridge.action_to_knowledge_sync() 通过 InboxWriter.stage() 写入 _inbox，
   且知识条目格式（title/content/tags/scope/frontmatter/meta）正确。
2. CUExecutor.run_task() 在任务完成后调用桥接器（通过 mock 验证）。
3. 桥接器失败不会拖垮执行器（resilience）。
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from server.config_kb_cu import CUConfig, KBConfig
from server.cu.executor.runner import CUExecutor
from server.cu.knowledge_bridge import CUKnowledgeBridge, KnowledgeCandidate
from server.cu.safety.emergency_stop import EmergencyStop
from server.kb.storage.inbox import InboxWriter


# ---------- Test 1: Bridge stages knowledge items to _inbox ----------

def test_bridge_stages_to_inbox_with_real_writer(tmp_path):
    """Test 1a: 真实 InboxWriter —— 验证 stage() 实际写入 _inbox 文件。"""
    inbox_dir = tmp_path / "_inbox"
    inbox_writer = InboxWriter(inbox_dir=inbox_dir)
    bridge = CUKnowledgeBridge(inbox_writer=inbox_writer)

    step_results = [
        {"step_index": 0, "action_type": "browser_navigate", "result_status": "success",
         "result_data": {"url": "https://example.com/login"}},
        {"step_index": 1, "action_type": "browser_click", "result_status": "success",
         "result_data": {"clicked": True}},
    ]

    candidates = bridge.action_to_knowledge_sync(
        task_id="cutask-stage-001",
        step_results=step_results,
        instruction="登录系统",
    )

    # 应当生成至少 1 个 SOP 候选
    assert len(candidates) >= 1
    assert all(isinstance(c, KnowledgeCandidate) for c in candidates)

    # _inbox 下应当存在与候选数量一致的 pending 目录
    pending_dirs = sorted(d for d in inbox_dir.iterdir() if d.is_dir())
    assert len(pending_dirs) == len(candidates)

    for pending_dir in pending_dirs:
        assert (pending_dir / "converted.md").exists()
        assert (pending_dir / "frontmatter.yaml").exists()
        assert (pending_dir / "meta.json").exists()

        # meta.json 必须包含知识条目四要素
        meta = json.loads((pending_dir / "meta.json").read_text(encoding="utf-8"))
        assert meta["source_task_id"] == "cutask-stage-001"
        assert "confidence" in meta
        assert "tags" in meta
        assert "scope" in meta
        assert meta["scope"] == "private"
        assert "cu-generated" in meta["tags"]

        # converted.md 应包含 SOP 标题
        converted = (pending_dir / "converted.md").read_text(encoding="utf-8")
        assert "CU SOP" in converted or "CU 错误案例" in converted

        # frontmatter.yaml 应包含 title 与 scope
        fm_text = (pending_dir / "frontmatter.yaml").read_text(encoding="utf-8")
        assert "title:" in fm_text
        assert "scope:" in fm_text


def test_bridge_stages_to_inbox_call_args_with_mock(tmp_path):
    """Test 1b: mock InboxWriter —— 精确验证 stage() 调用参数格式。"""
    inbox_writer = MagicMock(spec=InboxWriter)
    inbox_writer.stage.return_value = "pending-mock-id"
    bridge = CUKnowledgeBridge(inbox_writer=inbox_writer)

    step_results = [
        {"step_index": 0, "action_type": "browser_navigate", "result_status": "success",
         "result_data": {"url": "https://example.com"}},
    ]

    candidates = bridge.action_to_knowledge_sync(
        task_id="cutask-mock-001",
        step_results=step_results,
        instruction="打开首页",
    )

    assert len(candidates) == 1
    inbox_writer.stage.assert_called_once()

    kwargs = inbox_writer.stage.call_args.kwargs
    # converted_md 即候选 content
    assert "CU SOP" in kwargs["converted_md"]
    # original_filename 形如 cu-<task_id>.md
    assert kwargs["original_filename"] == "cu-cutask-mock-001.md"
    # frontmatter 字段映射
    fm = kwargs["frontmatter"]
    assert fm.title == "CU SOP: 打开首页"
    assert fm.type == "note"
    assert fm.scope == "private"
    assert fm.source_type == "cu"
    assert fm.confidence == pytest.approx(0.88)
    assert "cu-generated" in fm.tags
    assert "sop" in fm.tags
    # meta 携带四要素
    meta = kwargs["meta"]
    assert meta["source_task_id"] == "cutask-mock-001"
    assert meta["confidence"] == pytest.approx(0.88)
    assert meta["scope"] == "private"
    assert "cu-generated" in meta["tags"]


def test_bridge_without_inbox_writer_returns_candidates_only(tmp_path):
    """向后兼容：未注入 inbox_writer 时仅返回候选项，不写入。"""
    bridge = CUKnowledgeBridge()
    candidates = bridge.action_to_knowledge_sync(
        task_id="cutask-noinbox-001",
        step_results=[
            {"step_index": 0, "action_type": "browser_navigate",
             "result_status": "success", "result_data": {}},
        ],
        instruction="任务X",
    )
    assert len(candidates) == 1
    assert candidates[0].tags == ["cu-generated", "sop"]
    assert candidates[0].scope == "private"


# ---------- Test 2: CUExecutor.run_task() triggers bridge ----------

def _make_executor(tmp_path: Path) -> CUExecutor:
    es = EmergencyStop()
    config = CUConfig(audit_log_dir=tmp_path / "audit")
    return CUExecutor(config=config, emergency_stop=es)


def _basic_steps() -> list[dict]:
    return [
        {"step_index": 0, "action_type": "browser_navigate",
         "action_payload": {"url": "https://example.com"},
         "success_criteria": {"url_contains": "example"},
         "timeout_ms": 3000},
    ]


def test_executor_triggers_bridge_after_completion(tmp_path):
    """Test 2: CUExecutor.run_task() 完成后调用 CUKnowledgeBridge.action_to_knowledge_sync()。"""
    executor = _make_executor(tmp_path)

    # 把 KBConfig 重定向到 tmp_path，避免污染用户主目录
    kb_config = KBConfig(kb_root=tmp_path / "kb")

    with patch("server.cu.executor.runner.KBConfig", return_value=kb_config), \
         patch("server.cu.executor.runner.CUKnowledgeBridge") as MockBridge:
        mock_bridge = MockBridge.return_value
        mock_bridge.action_to_knowledge_sync.return_value = []

        result = executor.run_task("cutask-bridge-001", _basic_steps())

        # 执行器应正常完成
        assert result["status"] == "completed"
        assert result["executed_steps"] == 1

        # 桥接器应被实例化且 action_to_knowledge_sync 被调用一次
        MockBridge.assert_called_once()
        mock_bridge.action_to_knowledge_sync.assert_called_once()

        call = mock_bridge.action_to_knowledge_sync.call_args
        assert call.kwargs["task_id"] == "cutask-bridge-001"
        # 传入桥接器的 step_results 与原 steps 数量一致（无 rollback 项）
        assert len(call.kwargs["step_results"]) == 1
        sr = call.kwargs["step_results"][0]
        assert sr["step_index"] == 0
        assert sr["action_type"] == "browser_navigate"
        assert sr["result_status"] == "success"


# ---------- Test 3: Bridge failure does not crash executor ----------

def test_bridge_failure_does_not_crash_executor(tmp_path):
    """Test 3: 桥接器抛异常时执行器仍正常返回（resilience）。"""
    executor = _make_executor(tmp_path)
    kb_config = KBConfig(kb_root=tmp_path / "kb")

    with patch("server.cu.executor.runner.KBConfig", return_value=kb_config), \
         patch("server.cu.executor.runner.CUKnowledgeBridge") as MockBridge:
        mock_bridge = MockBridge.return_value
        mock_bridge.action_to_knowledge_sync.side_effect = RuntimeError("bridge boom")

        result = executor.run_task("cutask-bridge-002", _basic_steps())

        # 尽管桥接失败，任务仍应标记为 completed
        assert result["status"] == "completed"
        assert result["executed_steps"] == 1
        mock_bridge.action_to_knowledge_sync.assert_called_once()


def test_bridge_stage_failure_does_not_crash_action_to_knowledge(tmp_path):
    """Test 3b: 单条 stage() 失败不应让 action_to_knowledge_sync 整体崩溃。"""
    inbox_writer = MagicMock(spec=InboxWriter)
    inbox_writer.stage.side_effect = RuntimeError("disk full")
    bridge = CUKnowledgeBridge(inbox_writer=inbox_writer)

    step_results = [
        {"step_index": 0, "action_type": "browser_navigate", "result_status": "success",
         "result_data": {}},
        {"step_index": 1, "action_type": "browser_click", "result_status": "failed",
         "result_data": {"error": "timeout"}},
    ]

    # 不应抛出
    candidates = bridge.action_to_knowledge_sync(
        task_id="cutask-resilience-001",
        step_results=step_results,
        instruction="鲁棒性测试",
    )

    # 候选仍应返回（SOP + 错误案例）
    assert len(candidates) == 2
    # stage 被尝试调用两次
    assert inbox_writer.stage.call_count == 2
