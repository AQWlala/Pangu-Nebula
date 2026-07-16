from datetime import datetime
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(512))
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    model_provider: Mapped[str | None] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(64), default="gpt-4")
    # v2.2.0 能力开关
    tools_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rag_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sandbox_allow_network: Mapped[bool] = mapped_column(Boolean, default=False)
    terminal_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    browser_use_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # v2.2.1 F7: computer_* 工具独立权限字段 (与 browser_* 解耦,默认关闭,安全优先)
    # 架构师 + 业务专家双票通过新增字段
    computer_use_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="persona", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int | None] = mapped_column(ForeignKey("personas.id", ondelete="SET NULL"))
    title: Mapped[str | None] = mapped_column(String(255))
    # v2.2.0 对话状态: idle/running/error
    status: Mapped[str] = mapped_column(String(20), default="idle")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow)

    persona: Mapped[Persona | None] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    # v2.2.0 工具调用持久化
    tool_calls: Mapped[str | None] = mapped_column(Text)  # JSON: LLM 返回的工具调用数组
    tool_call_id: Mapped[str | None] = mapped_column(String(64))
    tool_name: Mapped[str | None] = mapped_column(String(64))
    tool_result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int | None] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"))
    layer: Mapped[str] = mapped_column(String(8), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    html_content: Mapped[str | None] = mapped_column(Text)
    plain_text: Mapped[str | None] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    tags: Mapped[list | None] = mapped_column(JSON)
    links: Mapped[list | None] = mapped_column(JSON)
    backlinks: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="builtin")
    path: Mapped[str | None] = mapped_column(String(512))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())


class WikiPage(Base):
    __tablename__ = "wiki_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int | None] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    html_content: Mapped[str | None] = mapped_column(Text)
    plain_text: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON)
    links: Mapped[list | None] = mapped_column(JSON)
    backlinks: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft/compiled/published
    source_conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow)


class EvolutionLog(Base):
    __tablename__ = "evolution_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"), nullable=False)
    phase: Mapped[str] = mapped_column(String(64), nullable=False)  # extract/compile/reflect/soul
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/completed/failed
    trigger: Mapped[str] = mapped_column(String(64), default="manual")  # manual/auto_threshold/scheduled
    before_state: Mapped[dict | None] = mapped_column(JSON)
    after_state: Mapped[dict | None] = mapped_column(JSON)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())


class LoopIteration(Base):
    __tablename__ = "loop_iterations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/completed/failed/cancelled
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    max_iterations: Mapped[int] = mapped_column(Integer, default=5)
    steps: Mapped[list | None] = mapped_column(JSON)
    result: Mapped[str | None] = mapped_column(Text)
    evaluation: Mapped[str | None] = mapped_column(Text)
    budget_used: Mapped[dict | None] = mapped_column(JSON)  # {tokens, time_ms, cost}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow)


class BudgetConfig(Base):
    """预算控制配置表(awesome-llm-apps的预算控制模式)"""

    __tablename__ = "budget_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int | None] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"))
    token_limit: Mapped[int] = mapped_column(Integer, default=100000)  # 每周期Token上限
    time_limit_seconds: Mapped[int] = mapped_column(Integer, default=3600)  # 每周期时间上限(秒)
    cost_limit: Mapped[float] = mapped_column(Float, default=10.0)  # 每周期金额上限(美元)
    period: Mapped[str] = mapped_column(String(32), default="daily")  # daily/weekly/monthly
    action_on_exceed: Mapped[str] = mapped_column(String(32), default="stop")  # stop/degrade/warn
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow)


class SyncDevice(Base):
    __tablename__ = "sync_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_name: Mapped[str | None] = mapped_column(String(255))
    did_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Phase 9A: 设备公钥(PEM 格式),用于 E2EE 密钥交换
    public_key: Mapped[str | None] = mapped_column(Text)
    # Phase 9A: UUID 设备 ID,用于多设备同步寻址
    device_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    # Phase 9A: 设备状态 pending/paired/active/blocked
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # Phase 9A: 配对完成时间
    paired_at: Mapped[datetime | None] = mapped_column(DateTime)


class SyncOperation(Base):
    """CRDT 同步操作日志(Phase 9A)

    记录所有 CRDT 操作,用于多设备增量同步:
    - 每个操作有 op_type(lww/orset/rga)和 key(CRDT 键名)
    - payload 存储操作的具体内容(可序列化为 JSON)
    - synced_devices 记录已收到该操作的设备列表,用于增量同步
    """

    __tablename__ = "sync_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 源设备 ID(发起操作的设备)
    device_id: Mapped[str | None] = mapped_column(String(255))
    # 操作类型: lww / orset / rga
    op_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # CRDT 键名
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    # 操作载荷(JSON,包含 value/timestamp/tags 等)
    payload: Mapped[dict | None] = mapped_column(JSON)
    # 已同步设备列表(JSON array),用于增量同步追踪
    synced_devices: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now()
    )


class OauthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)  # gmail/github/notion/slack
    account_id: Mapped[str | None] = mapped_column(String(255))  # 用户在该平台的ID/邮箱
    access_token: Mapped[str] = mapped_column(Text, nullable=False)  # 加密存储
    refresh_token: Mapped[str | None] = mapped_column(Text)  # 加密存储
    token_type: Mapped[str] = mapped_column(String(32), default="Bearer")
    scope: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow)


class DidKey(Base):
    __tablename__ = "did_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int | None] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"))
    did: Mapped[str] = mapped_column(String(255), nullable=False)  # did:key:z6Mk...
    method: Mapped[str] = mapped_column(String(32), default="key")
    public_key: Mapped[str] = mapped_column(Text, nullable=False)  # base58 公钥
    private_key_enc: Mapped[str] = mapped_column(Text, nullable=False)  # 加密存储的私钥
    key_type: Mapped[str] = mapped_column(String(32), default="Ed25519")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict | None] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())


class SchedulerJob(Base):
    __tablename__ = "scheduler_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[dict | None] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())


class AclRule(Base):
    __tablename__ = "acl_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int | None] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"))
    resource: Mapped[str] = mapped_column(String(255), nullable=False)  # 资源路径模式,如 memory/*, skill/*
    action: Mapped[str] = mapped_column(String(32), default="*")  # read/write/execute/*
    effect: Mapped[str] = mapped_column(String(16), default="allow")  # allow/deny
    permission: Mapped[str] = mapped_column(String(16), default="read")  # 旧字段保留兼容
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int | None] = mapped_column(ForeignKey("personas.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # llm_call/tool_call/skill_exec/evolution/loop
    resource: Mapped[str | None] = mapped_column(String(255))  # provider/model/tool_name
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())


class EncryptionKey(Base):
    """加密密钥表,用于密钥轮换(Nebula设计)"""

    __tablename__ = "encryption_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)  # UUID
    key_type: Mapped[str] = mapped_column(String(32), default="AES-256-GCM")
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)  # 用主密钥加密的数据密钥
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime)  # 轮换时间


class TaskRecord(Base):
    """任务记录表,供自进化技能蒸馏引擎分析成功/失败模式"""

    __tablename__ = "task_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    inputs: Mapped[dict | None] = mapped_column(JSON)
    output: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    iterations: Mapped[int] = mapped_column(Integer, default=1)
    persona_id: Mapped[int | None] = mapped_column(ForeignKey("personas.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
