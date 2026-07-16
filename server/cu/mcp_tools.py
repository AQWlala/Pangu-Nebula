# server/cu/mcp_tools.py
"""CU MCP 工具定义"""
from __future__ import annotations


MCP_TOOLS = [
    {"name": "cu_plan_task", "description": "将自然语言指令分解为原子化 CU 任务计划",
     "input_schema": {"type": "object", "properties": {
         "instruction": {"type": "string"}, "scope": {"type": "string", "default": "private"}},
         "required": ["instruction"]}},
    {"name": "cu_execute_task", "description": "执行 CU 任务（沙箱内），返回任务 ID 供监控",
     "input_schema": {"type": "object", "properties": {
         "task_id": {"type": "string"}, "auto_confirm": {"type": "boolean", "default": False}},
         "required": ["task_id"]}},
    {"name": "cu_emergency_stop", "description": "紧急停止当前所有 CU 任务并触发回滚",
     "input_schema": {"type": "object", "properties": {"reason": {"type": "string", "default": "manual"}}}},
    {"name": "cu_rollback_task", "description": "回滚指定 CU 任务到指定步骤",
     "input_schema": {"type": "object", "properties": {
         "task_id": {"type": "string"}, "to_step": {"type": "integer", "default": 0}},
         "required": ["task_id"]}},
    {"name": "cu_get_audit_log", "description": "获取 CU 任务的完整操作审计日志",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}},
    {"name": "cu_get_task_status", "description": "查询 CU 任务实时状态",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}},
]
