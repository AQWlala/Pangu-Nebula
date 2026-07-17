-- T4.10 数据库索引优化
--
-- 此文件包含 Pangu Nebula 数据库的推荐索引定义。
-- 这些索引可在生产环境手动应用以提升查询性能,不影响 ORM 模型定义。
--
-- 应用方式 (生产环境):
--   sqlite3 data/nebula.db < server/db/indexes.sql
-- 或通过 SQLAlchemy:
--   async with engine.begin() as conn:
--       await conn.execute(text(open("server/db/indexes.sql").read()))
--
-- 注意:
-- - 索引仅创建一次,重复执行会因 IF NOT EXISTS 安全跳过
-- - 测试环境 (内存 SQLite) 无需应用,ORM 自动创建表和主键索引
-- - 此文件不修改 engine.py (公共文件由主线程统一处理)

-- ----------------------------------------------------------------------
-- personas 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_personas_name ON personas(name);
CREATE INDEX IF NOT EXISTS idx_personas_created_at ON personas(created_at);

-- ----------------------------------------------------------------------
-- conversations 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_conversations_persona_id ON conversations(persona_id);
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_title ON conversations(title);

-- ----------------------------------------------------------------------
-- messages 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);

-- 复合索引: 按对话查询消息列表 (常用场景)
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_created_at
    ON messages(conversation_id, created_at);

-- ----------------------------------------------------------------------
-- memories 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_memories_persona_id ON memories(persona_id);
CREATE INDEX IF NOT EXISTS idx_memories_layer ON memories(layer);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);
CREATE INDEX IF NOT EXISTS idx_memories_title ON memories(title);

-- 复合索引: 按 Persona + 层级查询记忆
CREATE INDEX IF NOT EXISTS idx_memories_persona_id_layer
    ON memories(persona_id, layer);

-- 复合索引: 按 Persona + 创建时间倒序 (最近记忆)
CREATE INDEX IF NOT EXISTS idx_memories_persona_id_created_at
    ON memories(persona_id, created_at DESC);

-- ----------------------------------------------------------------------
-- skills 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
CREATE INDEX IF NOT EXISTS idx_skills_source ON skills(source);
CREATE INDEX IF NOT EXISTS idx_skills_enabled ON skills(enabled);

-- ----------------------------------------------------------------------
-- wiki_pages 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_wiki_pages_persona_id ON wiki_pages(persona_id);
CREATE INDEX IF NOT EXISTS idx_wiki_pages_status ON wiki_pages(status);
CREATE INDEX IF NOT EXISTS idx_wiki_pages_created_at ON wiki_pages(created_at);
CREATE INDEX IF NOT EXISTS idx_wiki_pages_title ON wiki_pages(title);

-- 复合索引: 按 Persona + 状态查询 Wiki
CREATE INDEX IF NOT EXISTS idx_wiki_pages_persona_id_status
    ON wiki_pages(persona_id, status);

-- ----------------------------------------------------------------------
-- evolution_logs 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_evolution_logs_persona_id ON evolution_logs(persona_id);
CREATE INDEX IF NOT EXISTS idx_evolution_logs_phase ON evolution_logs(phase);
CREATE INDEX IF NOT EXISTS idx_evolution_logs_status ON evolution_logs(status);
CREATE INDEX IF NOT EXISTS idx_evolution_logs_created_at ON evolution_logs(created_at);

-- ----------------------------------------------------------------------
-- loop_iterations 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_loop_iterations_persona_id ON loop_iterations(persona_id);
CREATE INDEX IF NOT EXISTS idx_loop_iterations_status ON loop_iterations(status);
CREATE INDEX IF NOT EXISTS idx_loop_iterations_created_at ON loop_iterations(created_at);

-- ----------------------------------------------------------------------
-- sync_devices 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_sync_devices_did_key ON sync_devices(did_key);
CREATE INDEX IF NOT EXISTS idx_sync_devices_device_id ON sync_devices(device_id);
CREATE INDEX IF NOT EXISTS idx_sync_devices_status ON sync_devices(status);

-- ----------------------------------------------------------------------
-- sync_operations 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_sync_operations_device_id ON sync_operations(device_id);
CREATE INDEX IF NOT EXISTS idx_sync_operations_op_type ON sync_operations(op_type);
CREATE INDEX IF NOT EXISTS idx_sync_operations_key ON sync_operations(key);
CREATE INDEX IF NOT EXISTS idx_sync_operations_created_at ON sync_operations(created_at);

-- 复合索引: 按设备 + 操作类型查询
CREATE INDEX IF NOT EXISTS idx_sync_operations_device_id_op_type
    ON sync_operations(device_id, op_type);

-- ----------------------------------------------------------------------
-- oauth_tokens 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_provider ON oauth_tokens(provider);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_account_id ON oauth_tokens(account_id);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_expires_at ON oauth_tokens(expires_at);

-- ----------------------------------------------------------------------
-- did_keys 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_did_keys_persona_id ON did_keys(persona_id);
CREATE INDEX IF NOT EXISTS idx_did_keys_active ON did_keys(active);

-- ----------------------------------------------------------------------
-- channels 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_channels_type ON channels(type);
CREATE INDEX IF NOT EXISTS idx_channels_enabled ON channels(enabled);

-- ----------------------------------------------------------------------
-- scheduler_jobs 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_enabled ON scheduler_jobs(enabled);
CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_name ON scheduler_jobs(name);

-- ----------------------------------------------------------------------
-- acl_rules 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_acl_rules_persona_id ON acl_rules(persona_id);
CREATE INDEX IF NOT EXISTS idx_acl_rules_resource ON acl_rules(resource);
CREATE INDEX IF NOT EXISTS idx_acl_rules_effect ON acl_rules(effect);

-- ----------------------------------------------------------------------
-- audit_logs 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_audit_logs_persona_id ON audit_logs(persona_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource);

-- 复合索引: 按 Persona + 时间查询审计日志
CREATE INDEX IF NOT EXISTS idx_audit_logs_persona_id_created_at
    ON audit_logs(persona_id, created_at);

-- ----------------------------------------------------------------------
-- encryption_keys 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_encryption_keys_is_active ON encryption_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_encryption_keys_created_at ON encryption_keys(created_at);

-- ----------------------------------------------------------------------
-- task_records 表索引
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_task_records_task_type ON task_records(task_type);
CREATE INDEX IF NOT EXISTS idx_task_records_persona_id ON task_records(persona_id);
CREATE INDEX IF NOT EXISTS idx_task_records_success ON task_records(success);
CREATE INDEX IF NOT EXISTS idx_task_records_created_at ON task_records(created_at);

-- 复合索引: 按类型 + 成功状态查询 (用于蒸馏分析)
CREATE INDEX IF NOT EXISTS idx_task_records_task_type_success
    ON task_records(task_type, success);

-- ----------------------------------------------------------------------
-- swarm 相关表索引 (swarm_models.py)
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_swarms_status ON swarms(status);
CREATE INDEX IF NOT EXISTS idx_swarms_persona_id ON swarms(persona_id);
CREATE INDEX IF NOT EXISTS idx_swarms_created_at ON swarms(created_at);

CREATE INDEX IF NOT EXISTS idx_swarm_workers_swarm_id ON swarm_workers(swarm_id);
CREATE INDEX IF NOT EXISTS idx_swarm_workers_status ON swarm_workers(status);

-- ----------------------------------------------------------------------
-- autowork 相关表索引 (autowork_models.py)
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_autowork_jobs_status ON autowork_jobs(status);
CREATE INDEX IF NOT EXISTS idx_autowork_jobs_created_at ON autowork_jobs(created_at);

-- ----------------------------------------------------------------------
-- dag 相关表索引 (dag_models.py)
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_dag_nodes_dag_id ON dag_nodes(dag_id);
CREATE INDEX IF NOT EXISTS idx_dag_edges_source_id ON dag_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_dag_edges_target_id ON dag_edges(target_id);

-- ----------------------------------------------------------------------
-- wiki_review 相关表索引 (wiki_review_models.py)
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_wiki_reviews_page_id ON wiki_reviews(page_id);
CREATE INDEX IF NOT EXISTS idx_wiki_reviews_status ON wiki_reviews(status);
CREATE INDEX IF NOT EXISTS idx_wiki_reviews_created_at ON wiki_reviews(created_at);

-- ----------------------------------------------------------------------
-- acp 相关表索引 (acp_models.py)
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_acp_sessions_status ON acp_sessions(status);
CREATE INDEX IF NOT EXISTS idx_acp_sessions_created_at ON acp_sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_acp_messages_session_id ON acp_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_acp_messages_created_at ON acp_messages(created_at);

-- ----------------------------------------------------------------------
-- v2.3.0 Phase 0 新增表索引 (orm.py: persona_relations/worker_pools/memory_events/memory_snapshots)
-- v2.3.1 P0-6: 补齐索引定义, 与 ORM __table_args__ 保持一致
-- ----------------------------------------------------------------------

-- persona_relations: 唯一约束 (source_id, target_id, relation_type)
CREATE UNIQUE INDEX IF NOT EXISTS uq_persona_relations_src_tgt_type
    ON persona_relations(source_id, target_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_persona_relations_source_id ON persona_relations(source_id);
CREATE INDEX IF NOT EXISTS idx_persona_relations_target_id ON persona_relations(target_id);
CREATE INDEX IF NOT EXISTS idx_persona_relations_relation_type ON persona_relations(relation_type);

-- worker_pools: 唯一约束 (persona_id, pool_id)
CREATE UNIQUE INDEX IF NOT EXISTS uq_worker_pools_persona_pool
    ON worker_pools(persona_id, pool_id);
CREATE INDEX IF NOT EXISTS idx_worker_pools_pool_id ON worker_pools(pool_id);
CREATE INDEX IF NOT EXISTS idx_worker_pools_status ON worker_pools(status);

-- memory_events: seq/event_type/persona_id 三索引 (支持 SSE 断点续传 + 类型筛选 + 角色查询)
CREATE INDEX IF NOT EXISTS ix_memory_events_seq ON memory_events(seq);
CREATE INDEX IF NOT EXISTS ix_memory_events_event_type ON memory_events(event_type);
CREATE INDEX IF NOT EXISTS ix_memory_events_persona_id ON memory_events(persona_id);
CREATE INDEX IF NOT EXISTS idx_memory_events_memory_id ON memory_events(memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_events_action ON memory_events(action);
CREATE INDEX IF NOT EXISTS idx_memory_events_created_at ON memory_events(created_at);

-- memory_snapshots: persona_id + created_at 复合索引 (按角色查询历史快照倒序)
CREATE INDEX IF NOT EXISTS ix_memory_snapshots_persona_created
    ON memory_snapshots(persona_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memory_snapshots_snapshot_type ON memory_snapshots(snapshot_type);
CREATE INDEX IF NOT EXISTS idx_memory_snapshots_created_at ON memory_snapshots(created_at);

-- ----------------------------------------------------------------------
-- 性能优化说明
-- ----------------------------------------------------------------------
-- 1. 主键索引: SQLite 自动为主键创建索引,无需手动定义
-- 2. 外键索引: 所有外键列均建议添加索引 (已在上方定义)
-- 3. 复合索引: 查询频率高的组合应使用复合索引,顺序遵循"最左前缀"原则
-- 4. 时间戳索引: created_at / updated_at 列常用于排序和范围查询
-- 5. 状态字段索引: status / enabled / active 等低基数列,仅在用于过滤时添加索引
--
-- 验证索引使用情况:
--   EXPLAIN QUERY PLAN SELECT * FROM memories WHERE persona_id = 1 AND layer = 'L3';
-- 应显示 "USING INDEX idx_memories_persona_id_layer"

-- ----------------------------------------------------------------------
-- KB 全文检索虚拟表 (FTS5)
-- ----------------------------------------------------------------------
-- 注意：此表在 KB 的 meta.db (kb_root/meta.db) 中创建，由
-- server/kb/retrieval/hybrid.py 的 ensure_fts_table() 幂等建表，
-- 文档审批时 (server/api/kb.py approve_document) 同步写入。
-- doc_id/scope 标记为 UNINDEXED：不参与全文索引但可用于 WHERE 过滤。
CREATE VIRTUAL TABLE IF NOT EXISTS kb_documents_fts USING fts5(
    doc_id UNINDEXED,
    title,
    content,
    scope UNINDEXED,
    tokenize = 'unicode61'
);
