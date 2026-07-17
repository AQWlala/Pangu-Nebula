from pydantic import BaseModel, Field


class PersonaCreate(BaseModel):
    name: str = Field(..., description="Persona 名称")
    system_prompt: str = Field("", description="系统提示词,定义 Persona 的角色和行为")
    temperature: float = Field(0.7, description="采样温度,0~2 之间,越高越随机")
    max_tokens: int = Field(4096, description="单次回复最大 token 数")
    model_provider: str = Field("openai", description="LLM Provider 名称")
    model_name: str = Field("gpt-4o", description="模型名称")
    avatar: str = Field("", description="头像 URL 或 base64")
    # v2.3.0 A3: 角色三元组 (CrewAI) + allowed_paths (PathGuard)
    role: str | None = Field(None, description="角色定位,如 架构师/编码者/评审")
    goal: str | None = Field(None, description="角色目标")
    backstory: str | None = Field(None, description="角色背景故事")
    allowed_paths: str | None = Field(None, description="允许访问的路径白名单,逗号分隔")


class PersonaUpdate(BaseModel):
    name: str | None = Field(None, description="Persona 名称")
    system_prompt: str | None = Field(None, description="系统提示词")
    temperature: float | None = Field(None, description="采样温度")
    max_tokens: int | None = Field(None, description="最大 token 数")
    model_provider: str | None = Field(None, description="LLM Provider 名称")
    model_name: str | None = Field(None, description="模型名称")
    avatar: str | None = Field(None, description="头像")
    # v2.3.0 A3: 角色三元组 + allowed_paths (部分更新)
    role: str | None = Field(None, description="角色定位")
    goal: str | None = Field(None, description="角色目标")
    backstory: str | None = Field(None, description="角色背景故事")
    allowed_paths: str | None = Field(None, description="允许访问的路径白名单")


class PersonaRelationCreate(BaseModel):
    """v2.3.0 A3 — 创建角色关联关系"""

    target_id: int = Field(..., description="目标角色 ID")
    relation_type: str = Field("complement", description="关系类型: complement/assist/delegate")
    strength: float = Field(0.5, description="关系强度 0.0-1.0")


class PersonaActivate(BaseModel):
    pass


class PersonaGenerateRequest(BaseModel):
    description: str = Field(..., description="自然语言描述,用于 AI 生成 Persona")
    model_provider: str = Field("openai", description="LLM Provider 名称")
    model_name: str = Field("gpt-4o", description="模型名称")


class ConversationCreate(BaseModel):
    persona_id: int | None = Field(None, description="关联的 Persona ID,为空则使用默认")
    title: str | None = Field(None, description="对话标题")


class MessageSend(BaseModel):
    content: str = Field(..., description="消息内容")


class SwarmCreate(BaseModel):
    persona_id: int = Field(..., description="关联的 Persona ID")
    goal: str = Field(..., description="蜂群任务目标")
    title: str | None = Field(None, description="蜂群任务标题")


class SwarmUpdate(BaseModel):
    title: str | None = Field(None, description="蜂群任务标题")
    goal: str | None = Field(None, description="蜂群任务目标")
    status: str | None = Field(None, description="状态: pending/running/completed/cancelled")


class MemoryCreate(BaseModel):
    persona_id: int | None = Field(None, description="关联的 Persona ID")
    layer: str = Field(..., description="记忆层级: L1/L2/L3/L4/L5")
    title: str = Field(..., description="记忆标题")
    html_content: str = Field(..., description="记忆内容(HTML 格式)")
    importance: float = Field(0.5, description="重要性,0~1 之间")
    tags: list[str] = Field([], description="标签列表")


class MemoryUpdate(BaseModel):
    layer: str | None = Field(None, description="记忆层级")
    title: str | None = Field(None, description="记忆标题")
    html_content: str | None = Field(None, description="记忆内容(HTML)")
    importance: float | None = Field(None, description="重要性,0~1")
    tags: list[str] | None = Field(None, description="标签列表")


class MemorySearchQuery(BaseModel):
    query: str = Field(..., description="搜索关键词")
    persona_id: int | None = Field(None, description="按 Persona 过滤")
    layer: str | None = Field(None, description="按层级过滤")
    limit: int = Field(10, description="返回条数上限")


class SandboxExecuteRequest(BaseModel):
    code: str = Field(..., description="要执行的 Python 代码")
    input_data: dict = Field({}, description="输入数据")
    input_schema: dict | None = Field(None, description="输入 schema 校验")
    output_schema: dict | None = Field(None, description="输出 schema 校验")
    timeout: int = Field(60, description="超时时间(秒)")


class DistillCheckRequest(BaseModel):
    """蒸馏检查请求"""

    task_type: str
    persona_id: int | None = None


class DistillConfirmRequest(BaseModel):
    """蒸馏确认请求:人工确认后将技能写入磁盘"""

    skill_name: str
    skill_content: str


class TaskRecordCreate(BaseModel):
    """新建任务记录请求(供其他模块调用记录任务)"""

    task_type: str
    description: str
    inputs: dict = {}
    output: str | None = None
    success: bool = False
    iterations: int = 1
    persona_id: int | None = None


class SkillImportMarkdownRequest(BaseModel):
    """从 SKILL.md 内容导入技能的请求"""
    content: str
    overwrite: bool = False


# ===== 提示词技能相关模型 (Phase 5A) =====


class SkillCreate(BaseModel):
    name: str = Field(..., description="技能名称(唯一标识)")
    description: str = Field("", description="技能描述")
    category: str = Field("general", description="技能分类")
    prompt_template: str = Field(..., description="提示词模板,支持 {{variable}} 变量")
    tags: list[str] = Field([], description="标签列表")


class SkillUpdate(BaseModel):
    description: str | None = Field(None, description="技能描述")
    category: str | None = Field(None, description="技能分类")
    prompt_template: str | None = Field(None, description="提示词模板")
    tags: list[str] | None = Field(None, description="标签列表")
    # v2.3.0 Phase 3-C: enabled 持久化开关 (持久化到 DB Skill.enabled 列)
    enabled: bool | None = Field(None, description="启用状态")


class SkillExecuteRequest(BaseModel):
    variables: dict[str, str] = Field({}, description="模板变量键值对")


# ===== Phase 6A: Wiki 编译引擎 =====


class WikiCreate(BaseModel):
    persona_id: int | None = None
    title: str
    content: str = ""
    html_content: str = ""
    tags: list[str] = []
    source_conversation_id: int | None = None


class WikiUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    html_content: str | None = None
    tags: list[str] | None = None
    status: str | None = None


class WikiCompileRequest(BaseModel):
    """从对话编译 Wiki 笔记

    v2.3.0 Phase 3-D: 支持多对话编译。
    - conversation_id: 单对话 (向后兼容, 仍可用)
    - conversation_ids: 多对话列表 (新增, 优先使用)
    二者至少提供一个; 同时提供时以 conversation_ids 为准。
    """

    conversation_id: int | None = None
    conversation_ids: list[int] | None = None
    persona_id: int | None = None
    title: str | None = None
    tags: list[str] = []


# ===== Phase 6B: 进化引擎 =====


class EvolutionTriggerRequest(BaseModel):
    """触发进化管道"""

    persona_id: int
    phases: list[str] = ["extract", "compile", "reflect", "soul"]  # 可选择性执行
    trigger: str = "manual"  # manual/auto_threshold/scheduled


# ===== Phase 6C: Loop 循环迭代 =====


class LoopCreateRequest(BaseModel):
    persona_id: int
    goal: str
    max_iterations: int = 5


class LoopUpdateRequest(BaseModel):
    status: str | None = None  # running/cancelled


# ===== Phase 6D: 预算控制 + 审计日志 =====


class BudgetConfigCreate(BaseModel):
    persona_id: int | None = None
    token_limit: int = 100000
    time_limit_seconds: int = 3600
    cost_limit: float = 10.0
    period: str = "daily"  # daily/weekly/monthly
    action_on_exceed: str = "stop"  # stop/degrade/warn
    enabled: bool = True


class BudgetConfigUpdate(BaseModel):
    token_limit: int | None = None
    time_limit_seconds: int | None = None
    cost_limit: float | None = None
    period: str | None = None
    action_on_exceed: str | None = None
    enabled: bool | None = None


class BudgetCheckRequest(BaseModel):
    """检查预算是否超限"""

    persona_id: int | None = None
    tokens_to_add: int = 0
    time_seconds_to_add: int = 0
    cost_to_add: float = 0.0


class AuditLogCreate(BaseModel):
    """记录审计日志(供其他模块调用)"""

    persona_id: int | None = None
    action: str
    resource: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    token_count: int = 0
    cost: float = 0.0
    duration_ms: int = 0
    success: bool = True
    details: dict = {}


class AuditLogQuery(BaseModel):
    """查询审计日志"""

    persona_id: int | None = None
    action: str | None = None
    resource: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    page: int = 1
    page_size: int = 20


# ===== Phase 7A: 多模态 =====


class ImageAnalyzeRequest(BaseModel):
    """图片识别请求"""

    persona_id: int | None = None
    image_base64: str  # base64 编码的图片
    prompt: str = "请描述这张图片的内容"
    model_name: str | None = None


class ASRRequest(BaseModel):
    """语音识别请求"""

    audio_base64: str  # base64 编码的音频
    language: str = "zh"  # zh/en/auto
    model_name: str = "whisper-1"


class TTSRequest(BaseModel):
    """语音合成请求"""

    text: str
    voice: str = "alloy"  # alloy/echo/fable/onyx/nova/shimmer
    model_name: str = "tts-1"
    speed: float = 1.0
    output_format: str = "mp3"  # mp3/opus/aac/flac


class VideoAnalyzeRequest(BaseModel):
    """视频分析请求"""

    persona_id: int | None = None
    video_base64: str | None = None  # base64 编码的视频(小文件)
    video_path: str | None = None  # 视频文件路径(大文件)
    prompt: str = "请分析这个视频的内容"
    max_frames: int = 10  # 抽取的最大帧数
    model_name: str | None = None


# ===== Phase 7B: OS 感知 =====


class ClipboardWatcherConfig(BaseModel):
    """剪贴板监控配置"""

    enabled: bool = True
    interval_seconds: float = 0.5  # 轮询间隔
    max_history: int = 100  # 最大历史记录数
    filter_text: bool = True  # 是否记录文本
    filter_image: bool = True  # 是否记录图片
    ignore_patterns: list[str] = []  # 忽略的模式(正则)


class FileWatcherConfig(BaseModel):
    """文件夹监控配置"""

    enabled: bool = True
    paths: list[str] = []  # 监控的文件夹路径列表
    recursive: bool = True  # 是否递归监控子目录
    event_types: list[str] = ["created", "modified", "deleted", "moved"]  # 监控的事件类型
    ignore_patterns: list[str] = []  # 忽略的文件模式


class TrayConfig(BaseModel):
    """系统托盘配置"""

    enabled: bool = True
    icon_path: str | None = None  # 图标路径
    title: str = "Pangu Nebula"


class ShortcutConfig(BaseModel):
    """全局快捷键配置"""

    enabled: bool = True
    shortcuts: dict[str, str] = {
        "ctrl+shift+n": "toggle_window",  # 切换窗口显示
        "ctrl+shift+c": "quick_chat",  # 快速对话
        "ctrl+shift+s": "screenshot",  # 截图
    }


class ScreenCaptureConfig(BaseModel):
    """屏幕感知配置"""

    enabled: bool = False  # 默认关闭(隐私)
    interval_seconds: float = 30.0  # 截图间隔
    ocr_enabled: bool = True  # 是否启用 OCR
    store_screenshots: bool = False  # 是否存储截图
    max_screenshots: int = 10  # 最大存储数


class ScreenCaptureRequest(BaseModel):
    """手动截图请求"""

    ocr: bool = True  # 是否进行 OCR
    monitor: int = 1  # 显示器编号(1=主屏)


# ===== Phase 7C: 浏览器自动化 =====


class BrowserNavigateRequest(BaseModel):
    """浏览器导航请求"""

    url: str
    wait_until: str = "domcontentloaded"  # load/domcontentloaded/networkidle


class BrowserActionRequest(BaseModel):
    """浏览器操作请求"""

    action: str  # click/type/screenshot/scroll/evaluate/wait_for_selector
    selector: str | None = None  # CSS 选择器
    text: str | None = None  # type 动作的文本
    script: str | None = None  # evaluate 动作的 JS 脚本
    timeout: int = 30000  # 超时(毫秒)


class BrowserSessionRequest(BaseModel):
    """浏览器会话管理"""

    headless: bool = True
    viewport_width: int = 1280
    viewport_height: int = 720


# ===== Phase 8A: 安全防护 =====


class AclRuleCreate(BaseModel):
    """ACL 规则创建"""

    persona_id: int | None = None
    resource: str  # 资源路径模式,如 memory/*, skill/*
    action: str = "*"  # read/write/execute/*
    effect: str = "allow"  # allow/deny


class AclRuleUpdate(BaseModel):
    """ACL 规则更新"""

    resource: str | None = None
    action: str | None = None
    effect: str | None = None


class AclCheckRequest(BaseModel):
    """ACL 权限检查"""

    persona_id: int | None = None
    resource: str
    action: str = "read"


class InjectionCheckRequest(BaseModel):
    """注入检查请求"""

    text: str
    context: str = "general"  # general/prompt/code/url


class SsrfCheckRequest(BaseModel):
    """SSRF 检查请求"""

    url: str
    allow_internal: bool = False  # 是否允许内网IP


class KeychainStoreRequest(BaseModel):
    """密钥存储请求"""

    key: str  # 密钥名称
    value: str  # 密钥值(明文,会被加密后存储)
    metadata: dict = {}


class KeychainGetRequest(BaseModel):
    """密钥获取请求"""

    key: str


class KeyRotationRequest(BaseModel):
    """密钥轮换请求"""

    force: bool = False  # 是否强制轮换(即使未过期)


# ===== Phase 8B: OAuth + Token =====


class OAuthAuthorizeRequest(BaseModel):
    """OAuth 授权请求"""

    provider: str  # gmail/github/notion/slack
    redirect_uri: str
    state: str | None = None  # CSRF 防护


class OAuthCallbackRequest(BaseModel):
    """OAuth 回调请求"""

    provider: str
    code: str
    state: str | None = None
    redirect_uri: str


class OAuthRefreshRequest(BaseModel):
    """OAuth 刷新令牌"""

    provider: str
    token_id: int


class TokenStoreRequest(BaseModel):
    """Token 存储(手动存储,非OAuth流程)"""

    provider: str
    account_id: str | None = None
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    scope: str | None = None
    expires_at: str | None = None  # ISO 格式


# ===== Phase 8C: DID + 脱敏 =====


class DidCreateRequest(BaseModel):
    """DID 创建请求"""

    persona_id: int | None = None
    key_type: str = "Ed25519"


class DidSignRequest(BaseModel):
    """DID 签名请求"""

    did_id: int
    message: str


class DidVerifyRequest(BaseModel):
    """DID 验证签名请求"""

    did: str  # did:key:...
    message: str
    signature: str


class RedactRequest(BaseModel):
    """敏感信息脱敏请求"""

    text: str
    rules: list[str] = []  # 指定使用的规则,空则使用全部
    replacement: str = "***"  # 替换字符串


# ===== Phase 9A: CRDT + E2EE =====


class LWWCreateRequest(BaseModel):
    """LWW Register 创建/更新"""

    key: str
    value: str
    node_id: str  # 设备ID


class LWWMergeRequest(BaseModel):
    """LWW Register 合并"""

    key: str
    value: str
    timestamp: str  # ISO 格式
    node_id: str


class ORSetCreateRequest(BaseModel):
    """OR-Set 创建"""

    key: str


class ORSetAddRequest(BaseModel):
    """OR-Set 添加元素"""

    value: str


class ORSetRemoveRequest(BaseModel):
    """OR-Set 删除元素"""

    value: str


class ORSetMergeRequest(BaseModel):
    """OR-Set 合并"""

    key: str
    elements: dict  # {value: [tags]}


class SyncOpSyncedRequest(BaseModel):
    """标记同步操作已完成"""

    device_id: str


class CryptoKeygenRequest(BaseModel):
    """密钥对生成请求"""

    device_name: str = "default"


class CryptoEncryptRequest(BaseModel):
    """加密请求"""

    device_id: str  # 目标设备ID
    data: dict  # 明文数据


class CryptoDecryptRequest(BaseModel):
    """解密请求"""

    device_id: str  # 源设备ID
    encrypted: dict  # {ciphertext, nonce, tag}
