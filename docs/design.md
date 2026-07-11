# Pangu Nebula — 详细设计 v2.0

## 1. UI 设计规范（暖色调迪士尼风格）

### 1.1 三色系方案

用户可在设置中切换三套暖色系：

**温暖橙（默认）**
```
--bg-primary: #FFF3E0
--bg-secondary: #FFE0B2
--bg-tertiary: #FFCC80
--border: #FFB74D
--text-primary: #4E342E
--text-secondary: #795548
--text-muted: #A1887F
--accent: #FF8C42
--accent-hover: #E67A35
```

**柔和粉**
```
--bg-primary: #FFF0F5
--bg-secondary: #FFD6E7
--bg-tertiary: #FFB8D0
--border: #FF9EC0
--text-primary: #4A2040
--text-secondary: #7A5068
--text-muted: #A08090
--accent: #FF7EB3
--accent-hover: #E56A9E
```

**奶油米白**
```
--bg-primary: #FEF9EF
--bg-secondary: #FFF8E1
--bg-tertiary: #FFECB3
--border: #FFE082
--text-primary: #5D4037
--text-secondary: #8D6E63
--text-muted: #BCAAA4
--accent: #FFA726
--accent-hover: #F09000
```

### 1.2 字体系统
```
--font-sans: Geist, PingFang SC, Microsoft YaHei, sans-serif
--font-display: Geist Display, PingFang SC
--font-mono: JetBrains Mono, Fira Code
```

### 1.3 圆角与间距（沿用 Nebula 体系）
```
--radius-sm: 4px
--radius-md: 8px
--radius-lg: 16px
--spacing-xs: 4px ~ --spacing-3xl: 64px
```

### 1.4 毛玻璃效果（保留）
```
--glass-bg: rgba(255, 255, 255, 0.6)
--glass-border: rgba(0, 0, 0, 0.06)
--glass-blur: saturate(180%) blur(20px)
```

### 1.5 完整布局结构

```
+---------+------------------------------------------------------+
| Titlebar (44px): [🔴🟡🟢] Nebula  [🔍 搜索...]  [🪟🌀⚙️]        |
+---------+------------------------------------------------------+
| Sidebar |  ContentArea (flex:1, padding:12px)                  |
| (220px) |  +--------------------------------------------------+ |
|         |  |  ContentCard (毛玻璃卡片, flex:1)                  | |
| 🌌 Neb  |  |                                                  | |
|         |  |  对话 / 蜂群 / 记忆 / 代码 / 技能 / ...           | |
| ★ 收藏  |  |  (根据侧边栏导航切换视图)                         | |
| 💬 对话  |  |                                                  | |
| 🐝 蜂群  |  |                                                  | |
|         |  |                                                  | |
| 💼 工作  |  |                                                  | |
| 🧠 记忆  |  |                                                  | |
| 💻 代码  |  |                                         +------+ | |
| 🔍 技能  |  |                                         | 卡通  | | |
|         |  |                                         | 助理  | | |
| 📊 监控  |  |                                         | O O  | | |
| 📊 仪表  |  |                                         |  ~   | | |
| 💰 积分  |  |                                         +------+ | |
| 🩺 诊断  |  +--------------------------------------------------+ |
|         |                                                      |
| 🌑 高级  |                                                      |
| 🌑 影子  |                                                      |
| ⏳ 长任务 |                                                      |
|         |                                                      |
| ⚙️ 系统  |                                                      |
| ⚙️ 设置  |                                                      |
|         |                                                      |
| ● 模型在线|                                                     |
| 内存 42MB |                                                     |
| v2.2.0   |                                                     |
+---------+------------------------------------------------------+
```

**布局要点**：
- 顶部 Titlebar（44px）：交通灯按钮 + 应用标题 + 搜索框 + 操作按钮
- 左侧 Sidebar（220px）：分组导航（收藏/工作/监控/高级/系统），底部状态区显示模型状态、内存、版本号
- 右侧 ContentArea + ContentCard：毛玻璃卡片容器，侧边栏导航驱动视图切换
- 卡通助理定位在 ContentCard 右下角

### 1.6 Sidebar + Titlebar 组件规范

```css
/* ===== Titlebar ===== */
.titlebar {
  height: 44px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  background: rgba(255,248,225,0.85);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  gap: 16px;
}

.traffic-lights { display: flex; gap: 8px; }
.traffic-light { width: 12px; height: 12px; border-radius: 50%; }
.tl-close { background: #ff5f57; }
.tl-min { background: #febc2e; }
.tl-max { background: #28c840; }

.titlebar-title {
  font-size: 14px; font-weight: 600;
  color: var(--text-secondary); letter-spacing: -0.01em;
}

.titlebar-search {
  flex: 1; max-width: 360px; margin: 0 auto;
  background: rgba(139,90,43,0.08); border-radius: 8px;
  padding: 5px 12px; color: var(--text-muted); font-size: 13px;
  display: flex; align-items: center; gap: 6px;
  border: 1px solid rgba(255,255,255,0.04);
}

.titlebar-actions { display: flex; gap: 8px; }
.titlebar-btn {
  width: 28px; height: 28px; border-radius: 6px;
  background: rgba(139,90,43,0.08);
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; cursor: pointer; transition: background 0.15s;
}
.titlebar-btn:hover { background: rgba(255,255,255,0.12); }

/* ===== Sidebar ===== */
.sidebar {
  width: 220px;
  background: rgba(30,30,30,0.5);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-right: 1px solid rgba(255,255,255,0.06);
  display: flex; flex-direction: column; flex-shrink: 0;
  overflow-y: auto;
}

.sidebar-brand {
  padding: 16px 16px 12px;
  display: flex; align-items: center; gap: 8px;
}
.sidebar-brand-icon { font-size: 24px; }
.sidebar-brand-text {
  font-size: 16px; font-weight: 700;
  letter-spacing: -0.02em; color: #0A84FF;
}

.nav-group { margin-bottom: 12px; }
.nav-group-label {
  padding: 4px 16px; font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.5px;
  color: rgba(255,255,255,0.3);
}

.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 16px; margin: 1px 8px; border-radius: 8px;
  font-size: 13px; color: rgba(255,255,255,0.7); cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.nav-item:hover {
  background: rgba(139,90,43,0.08); color: rgba(255,255,255,0.9);
}
.nav-item.active {
  background: rgba(10,132,255,0.2); color: #0A84FF; font-weight: 500;
}
.nav-item-icon { font-size: 15px; width: 20px; text-align: center; }

/* ===== Sidebar 底部状态区 ===== */
.sidebar-status {
  margin-top: auto; padding: 12px 16px;
  border-top: 1px solid rgba(255,255,255,0.06);
  font-size: 11px; color: var(--text-muted);
}
.status-row { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; }
.status-dot.ok { background: #28c840; }

/* ===== 主内容区 ===== */
.content-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; padding: 12px; }
.content-card {
  flex: 1; background: rgba(40,40,40,0.4);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255,255,255,0.06); border-radius: 16px;
  display: flex; flex-direction: column; overflow: hidden;
}
```

### 1.7 MascotAssistant 组件规范（暖色迪士尼卡通风格）

- 位置: 定位在 ContentCard 右下角（position: absolute; right: 20px; bottom: 20px; 相对 content-card）
- 尺寸: 80x80px（含 8px padding）
- 设计风格: 暖色迪士尼卡通助理，圆润造型，温暖配色，友好表情
- 动画:
  - 待机: 呼吸缩放(scale 1.0-1.05, 3s ease-in-out infinite)
  - 对话中: 点头(rotate -5deg-5deg) + 眼部高亮
  - 蜂群工作中: 思考状(眼珠左右移动 + 问号气泡)
  - 任务完成: 跳跃(translateY -10px) + 星星特效
- 状态切换通过 data-state 属性控制

```css
.mascot {
  position: absolute;
  right: 20px;
  bottom: 20px;
  width: 80px;
  height: 80px;
  cursor: pointer;
  z-index: 500;
  transition: transform 0.3s;
}

.mascot:hover {
  transform: scale(1.1);
}

.mascot[data-state="idle"] .body {
  animation: breathe 3s ease-in-out infinite;
}

.mascot[data-state="chatting"] .head {
  animation: nod 1.5s ease-in-out infinite;
}

.mascot[data-state="swarming"] .eyes {
  animation: think 2s ease-in-out infinite;
}

.mascot[data-state="done"] .body {
  animation: jump 0.5s ease-out;
}

@keyframes breathe {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}

@keyframes nod {
  0%, 100% { transform: rotate(0); }
  25% { transform: rotate(-3deg); }
  75% { transform: rotate(3deg); }
}

@keyframes think {
  0%, 100% { transform: translateX(0); }
  50% { transform: translateX(3px); }
}

@keyframes jump {
  0% { transform: translateY(0); }
  50% { transform: translateY(-12px); }
  100% { transform: translateY(0); }
}
```

### 1.8 OnboardingWizard 组件规范

首次引导流程，4 步卡片式：

1. 欢迎页：卡通助理挥手 + "你好！我是盘古星云的私人助理。先了解一下你吧~"
2. 工作内容：6 个选项卡片（编程/写作/自媒体/数据处理/项目管理/其他），单选
3. 日常偏好：多个 tag 选择（代码审查/文档编写/创意写作/数据分析/会议纪要...），多选
4. 沟通风格：4 个选项（简洁高效/详细周全/轻松幽默/严谨专业），单选
5. 生成 SOUL.md：AI 根据选择生成 → 展示预览 → 确认/修改 → 完成

样式: 居中卡片、毛玻璃背景、大号 emoji 图标、进度点指示器

### 1.9 各面板组件（沿用 Nebula 改造）

所有保留面板从 Nebula 迁移，主要改造：
- 面板切换通过侧边栏导航驱动（点击 nav-item 设置 currentView signal）
- 各面板渲染在右侧 ContentCard 毛玻璃卡片内，共享统一的 page-header + page-body 结构
- 侧边栏导航分组：收藏（对话/蜂群）、工作（记忆/代码/技能）、监控（仪表盘/积分/诊断）、高级（影子/长任务）、系统（设置）
- 对话区始终作为默认视图（nav-item.active 默认指向 chat）
- 侧边栏底部状态区显示模型在线状态、内存占用、版本号

---

## 2. Persona Agent 交互流程

```
[用户] 配置菜单中选择角色"网文作者"
   v
[用户] 在聊天中输入"帮我写一章修仙小说的打斗场景"
   v
[Persona Agent] 以网文作者口吻追问：
  "好的道友，这个打斗场景贫道来帮你推演一番。
   敢问主角如今什么境界了？对手是何方势力？
   道友是想要一场碾压式的完胜，还是险中求胜的死战？"
   v
[用户] 逐一回答
   v
[Persona Agent] 确认需求完毕，后台拆解为 3 个 subtask → Orchestrator 并行派发
   v
[卡通助理] 表情切换为"思考工作状"
   v
[Worker-1] 设计战斗节奏和转折点
[Worker-2] 撰写核心段落 3000 字
[Worker-3] 检查前后文连贯性和战力体系一致性
   v
[Orchestrator] 收集结果 → Persona Agent 汇总
   v
[卡通助理] 表情切换为"完成祝贺"，弹出"章节已完成！"
   v
[用户] 看到完整章节 + 简要说明
```

## 3. 数据库设计

（同 v1 设计，增加 personas.content_html 和 memories.plain_text）

```sql
CREATE TABLE personas (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    system_prompt TEXT NOT NULL,
    model_provider TEXT DEFAULT 'ollama',
    model_name TEXT DEFAULT 'qwen2.5:7b',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    layer TEXT NOT NULL,
    domain TEXT DEFAULT 'shared',
    title TEXT,
    content_html TEXT NOT NULL,
    plain_text TEXT,
    embedding_id TEXT,
    importance REAL DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP,
    source_conversation_id TEXT,
    tags TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 4. Provider Adapter 设计

### 国产大厂统一适配（OpenAI 兼容 API）

```python
PROVIDER_PRESETS = {
    "qwen": {
        "name": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-vl-plus"],
    },
    "ernie": {
        "name": "文心一言",
        "base_url": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
        "models": ["ernie-4.0-turbo", "ernie-3.5"],
    },
    "glm": {
        "name": "智谱GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4", "glm-4v"],
    },
    "moonshot": {
        "name": "Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    },
    "doubao": {
        "name": "豆包",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-pro-32k", "doubao-lite-32k"],
    },
    "hunyuan": {
        "name": "混元",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "models": ["hunyuan-pro", "hunyuan-lite"],
    },
    "nim": {
        "name": "NVIDIA NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "models": ["meta/llama-3.1-8b-instruct", "nvidia/nemotron-4-340b-instruct"],
    },
}
```

## 5. API 设计

（同 v1 设计，增加 providers 配置端点）

```
GET  /api/providers              → 提供商列表 + 预设
PUT  /api/providers/config        → 配置 API Key
POST /api/providers/test/{id}    → 测试连通性
GET  /api/providers/status       → 所有提供商状态
```

## 6. 从 awesome-llm-apps 借鉴的模式

1. Advisor-Orchestrator-Worker: Advisor=Persona Agent, Orchestrator=编排器, Worker=子智能体
2. 自进化技能: 从成功任务自动蒸馏新技能
3. 多 Agent 信任层: 子智能体结果互验

---

## 7. 多模态架构设计

### 7.1 图片识别

统一接口 `chat_with_image`，屏蔽底层模型差异，支持多 Provider 自动切换：

```python
async def chat_with_image(
    prompt: str,
    image: str | bytes | Path,        # URL / 文件路径 / 原始字节
    provider: str = "auto",            # auto | gpt-4o | claude-vision | ollama-llava
    **kwargs,
) -> str:
    """
    统一图片理解入口：
    - auto: 按 provider 优先级依次尝试（GPT-4o → Claude Vision → Ollama llava）
    - 返回模型对图片的文字描述/回答
    """
```

Provider 适配层：

| Provider | 模型 | 调用方式 |
|----------|------|----------|
| `gpt-4o` | gpt-4o / gpt-4o-mini | OpenAI Chat Completions + image_url |
| `claude-vision` | claude-3-5-sonnet | Anthropic Messages + image content block |
| `ollama-llava` | llava:13b / llava:7b | Ollama `/api/chat` + base64 image |

### 7.2 语音输入（ASR）

双引擎架构，兼顾离线可用性与流式实时性：

- **Whisper 本地**：`faster-whisper` 基于 CTranslate2 加速，支持 100+ 语言，适用于离线长音频转录
- **Paraformer 流式**：阿里 FunASR Paraformer，支持流式识别，延迟 < 300ms，适用于实时对话场景

```python
class ASREngine(Protocol):
    async def transcribe(self, audio: bytes, language: str = "zh") -> str: ...
    async def stream_transcribe(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]: ...
```

引擎选择策略：在线优先 Paraformer 流式 → 降级 Whisper 本地

### 7.3 语音输出（TTS）

纯本地化方案，零云端依赖：

- **MeloTTS**：支持中英日韩多语言，CPU 友好，推理速度 > 20x 实时
- **Kokoro**：高质量中文语音，自然度更优，需 GPU 加速

```python
class TTSEngine(Protocol):
    async def synthesize(self, text: str, voice: str = "default", speed: float = 1.0) -> bytes: ...
    async def stream_synthesize(self, text: str, **kwargs) -> AsyncIterator[bytes]: ...
```

### 7.4 视频分析

两阶段管线：帧抽取 → 图像理解

**帧抽取**：
- `ffmpeg`：`ffmpeg -i input.mp4 -vf fps=1/5 frames_%04d.jpg`，适用于关键帧提取
- `opencv`（cv2）：逐帧/跳帧读取，适用于精细分析（动作识别等）

**图像理解**：
- 对抽取帧调用 `chat_with_image` 进行批量理解
- 支持时间线聚合：将帧分析结果按时间轴合并为结构化摘要

```python
async def analyze_video(
    video_path: Path,
    fps: float = 0.2,                 # 每秒抽取帧数
    prompt: str = "描述这个视频的关键内容",
    provider: str = "auto",
) -> VideoAnalysisResult:
    frames = extract_frames(video_path, fps)       # ffmpeg / opencv
    analyses = await gather(*[chat_with_image(prompt, f, provider) for f in frames])
    return aggregate_timeline(analyses, fps)
```

---

## 8. OS 感知设计

### 8.1 剪贴板监控

基于 `pyperclip` + `watchdog` 的自动感知，识别有价值信息并触发处理：

```python
class ClipboardMonitor:
    """
    剪贴板变化监听：
    - 轮询 pyperclip 检测内容变化（间隔可配，默认 500ms）
    - 变化时调用 ValueClassifier 判断信息价值
    - 有价值内容自动存入记忆层 / 触发技能
    """

    def __init__(self, poll_interval_ms: int = 500):
        self.poll_interval = poll_interval_ms
        self.classifier = ValueClassifier()  # 规则+AI混合分类

    async def start(self): ...
    async def stop(self): ...
```

ValueClassifier 分类规则：
- URL → 自动提取网页摘要
- 代码片段 → 识别语言，存入代码记忆
- 邮箱/电话 → 存入联系人记忆
- 普通文本 → AI 判断是否值得记忆（> 50 字且含事实性信息）

### 8.2 文件夹监控

基于 `watchdog` 的文件系统事件监听，自动处理新文件：

```python
class FolderMonitor:
    """
    指定文件夹的文件事件监控：
    - 支持 created / modified / moved 事件
    - 按文件扩展名路由到不同处理器
    - 示例：新PDF → 解析入库；新图片 → OCR识别
    """

    handlers: dict[str, FileHandler] = {
        ".pdf": PDFHandler(),
        ".png": ImageOCRHandler(),
        ".md": MarkdownImportHandler(),
        ...
    }
```

### 8.3 系统托盘

基于 `pystray` 的常驻系统托盘 + 全局快捷键：

```python
class SystemTray:
    """
    系统托盘常驻：
    - 图标 + 右键菜单（打开主界面 / 快速对话 / 暂停监控 / 退出）
    - 全局快捷键：
      - Ctrl+Shift+Space: 快速对话窗口
      - Ctrl+Shift+M: 切换监控开关
      - Ctrl+Shift+C: 剪贴板内容直接对话
    """
```

### 8.4 屏幕实时感知

基于 PIL/mss 截屏 + AI 分析的实时屏幕理解：

```python
class ScreenAwareness:
    """
    屏幕实时感知：
    - 截屏引擎：PIL ImageGrab / mss（高性能多显示器支持）
    - 分析频率：可配置，默认 5s（金融分析等场景可设为 1s）
    - 可开关：全局开关 + 场景级开关
    - 隐私保护：敏感窗口（银行/密码管理器）自动跳过
    """

    def __init__(self, config: ScreenAwarenessConfig):
        self.enabled: bool = False
        self.interval_seconds: float = 5.0
        self.exclude_patterns: list[str] = ["*银行*", "*密码*", "*1Password*"]
        self.scene_presets: dict[str, float] = {
            "default": 5.0,
            "finance": 1.0,      # 金融分析高频感知
            "coding": 10.0,     # 编码低频感知
        }
```

工作流程：截屏 → OCR/图像理解 → 与当前上下文关联 → 主动推送信息/提醒

---

## 9. 安全架构设计

### 9.1 E2EE 端到端加密

全链路加密方案，确保用户数据在传输和存储中均不可被第三方读取：

```
密钥交换：X25519（Curve25519 ECDH）
    ↓
密钥派生：HKDF-SHA256（salt = 随机32字节, info = "pangu-nebula-v1"）
    ↓
数据加密：AES-256-GCM（12字节 nonce, 16字节 tag）
```

```python
class E2EEManager:
    """端到端加密管理器"""

    @staticmethod
    async def generate_keypair() -> tuple[bytes, bytes]:
        """生成 X25519 密钥对 (private_key, public_key)"""

    @staticmethod
    async def derive_session_key(
        my_private: bytes, peer_public: bytes
    ) -> bytes:
        """ECDH 密钥交换 + HKDF 派生 → 32字节 AES 密钥"""

    @staticmethod
    async def encrypt(plaintext: bytes, session_key: bytes) -> EncryptedData:
        """AES-256-GCM 加密，返回 (nonce, ciphertext, tag)"""

    @staticmethod
    async def decrypt(data: EncryptedData, session_key: bytes) -> bytes:
        """AES-256-GCM 解密 + 完整性验证"""
```

### 9.2 密钥轮换

定期自动轮换，前向安全性保障：

```python
class KeyRotation:
    """
    密钥轮换策略：
    - 轮换周期：默认 24h（可配置）
    - 旧密钥保留：2 个周期（解密历史数据用）
    - 轮换触发：定时 / 手动 / 会话重建
    - 过程：生成新密钥对 → 交换 → 新旧并存 → 旧密钥过期
    """

    rotation_interval_hours: int = 24
    retain_old_keys: int = 2
```

### 9.3 ACL 权限控制

记忆/技能/角色的细粒度访问控制：

```python
class ACLRule:
    """
    访问控制规则：
    - resource_type: memory / skill / persona
    - resource_id: 具体资源 ID
    - principal: user / agent / group
    - permissions: read / write / execute / delete
    - conditions: 时间段/IP/上下文等条件
    """

    resource_type: str
    resource_id: str
    principal: str
    permissions: set[str]
    conditions: dict | None

class ACLManager:
    async def check(self, principal: str, resource: str, action: str) -> bool: ...
    async def grant(self, rule: ACLRule) -> None: ...
    async def revoke(self, rule_id: str) -> None: ...
```

### 9.4 注入防护

Prompt 注入检测与防御：

```python
class InjectionGuard:
    """
    Prompt 注入防护：
    - 检测层1：规则引擎 — 已知注入模式正则匹配
      （ignore previous / system override / 你是一个...）
    - 检测层2：AI 分类 — 轻量模型判断意图是否为注入
    - 防御策略：
      - sanitize: 清除注入指令后继续
      - reject: 拒绝整个请求
      - sandbox: 在沙箱上下文中执行（隔离影响范围）
    """

    patterns: list[str] = [
        r"ignore\s+(previous|above|all)\s+instructions",
        r"you\s+are\s+(now|a)\s+",
        r"system\s*:\s*override",
        ...
    ]
```

### 9.5 SSRF 防护

URL 白名单机制，防止服务端请求伪造：

```python
class SSRFGuard:
    """
    SSRF 防护：
    - URL 白名单：仅允许访问已配置的域名
    - 禁止内网地址：127.0.0.x / 10.x / 172.16-31.x / 192.168.x
    - 禁止非 HTTP(S) 协议：file:// / ftp:// 等
    - DNS 重绑定检测：解析后 IP 仍需通过内网检查
    """

    allowed_domains: set[str]  # 配置的白名单域名
    blocked_cidrs: list[str] = ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]

    async def validate_url(self, url: str) -> bool: ...
```

---

## 10. IM 渠道设计

### 10.1 微信渠道

基于 WeChat webhook + 回调的消息收发：

```python
class WeChatChannel:
    """
    微信消息渠道：
    - 接收：企业微信 webhook 回调 → 消息解析 → 投递至 Router
    - 发送：Router 投递 → 格式化 → 企业微信 API 发送
    - 支持：文本 / 图片 / Markdown 卡片
    - 安全：回调签名验证（Token + EncodingAESKey）
    """

    async def handle_callback(self, request: Request) -> Response: ...
    async def send_message(self, chat_id: str, content: str, msg_type: str = "text") -> None: ...
```

### 10.2 飞书渠道

基于飞书 webhook + 事件回调的消息收发：

```python
class FeishuChannel:
    """
    飞书消息渠道：
    - 接收：飞书事件订阅（im.message.receive_v1）→ 消息解析 → 投递至 Router
    - 发送：Router 投递 → 格式化 → 飞书 API 发送
    - 支持：文本 / 富文本 / 交互卡片 / 图片
    - 安全：事件验证签名（Verification Token + Encrypt Key）
    """

    async def handle_event(self, request: Request) -> Response: ...
    async def send_message(self, chat_id: str, content: str, msg_type: str = "text") -> None: ...
```

### 10.3 消息路由分发

统一消息路由器，多渠道消息归一化处理：

```python
class MessageRouter:
    """
    消息路由分发：
    - 注册渠道：微信 / 飞书 / CLI / WebUI 等
    - 消息归一化：各渠道消息格式统一为 InternalMessage
    - 路由策略：
      - 按 Persona 路由：不同渠道可绑定不同角色
      - 按技能路由：消息内容匹配技能触发词
      - 按优先级路由：紧急消息优先处理
    - 回复分发：处理结果投递回原始渠道
    """

    channels: dict[str, Channel]  # channel_name → channel instance

    async def register(self, name: str, channel: Channel) -> None: ...
    async def dispatch(self, message: InternalMessage) -> Response: ...
    async def reply(self, original: InternalMessage, response: str) -> None: ...
```

---

## 11. Loop 循环迭代设计

### 11.1 预算控制

三维度预算约束，防止无限循环和资源浪费：

```python
class BudgetController:
    """
    预算控制，三维度：
    - Token 预算：限制单次循环总 Token 消耗
    - 时间预算：限制单次循环总执行时间
    - 金额预算：限制单次循环总 API 调用费用

    每轮迭代前检查预算余量，不足时终止循环并汇报。
    """

    token_budget: int = 100_000       # 默认 10 万 token
    time_budget_seconds: float = 300   # 默认 5 分钟
    money_budget_usd: float = 1.0      # 默认 1 美元

    token_consumed: int = 0
    time_elapsed: float = 0.0
    money_spent: float = 0.0

    def check(self) -> BudgetStatus:
        """返回当前预算状态，任一维度耗尽即标记 exceeded"""

    def consume(self, tokens: int, time_s: float, cost_usd: float) -> None:
        """记录一轮迭代的消耗"""
```

### 11.2 审计日志

每轮迭代的完整输入输出记录：

```python
class AuditLogger:
    """
    循环迭代审计日志：
    - 每轮记录：iteration_id / timestamp / input / output / tokens / duration / cost
    - 不可篡改：追加写入，不支持删除/修改
    - 查询支持：按会话/时间范围/迭代轮次查询
    """

    async def log_iteration(self, record: IterationRecord) -> None: ...
    async def query(self, session_id: str, **filters) -> list[IterationRecord]: ...

class IterationRecord:
    iteration_id: str
    session_id: str
    round_number: int
    timestamp: datetime
    input_summary: str        # 输入摘要（脱敏后）
    output_summary: str       # 输出摘要
    tokens_used: int
    duration_ms: int
    cost_usd: float
    status: str               # success / budget_exceeded / error
```

### 11.3 Phase Ring 多阶段循环控制

多阶段环形迭代控制器：

```python
class PhaseRing:
    """
    多阶段循环控制：
    - 定义一组 Phase，按环形顺序依次执行
    - 每轮迭代经过所有 Phase 为一个完整 cycle
    - 支持条件跳转：某 Phase 结果满足条件时跳过后续 Phase
    - 支持提前终止：某 Phase 返回终止信号时结束循环

    典型 Phases：
    - THINK: 理解当前状态，制定计划
    - ACT: 执行计划中的动作
    - OBSERVE: 观察执行结果
    - REFLECT: 评估结果质量，决定是否继续
    """

    phases: list[Phase] = [Phase.THINK, Phase.ACT, Phase.OBSERVE, Phase.REFLECT]
    current_phase: Phase
    current_cycle: int
    max_cycles: int = 10

    async def run(self, initial_input: Any) -> LoopResult:
        """
        执行循环：
        while budget.ok() and cycle < max_cycles:
            for phase in phases:
                result = await phase.execute(context)
                if result.should_terminate: return
                if result.should_skip_remaining: break
                context.update(result)
            cycle += 1
        """
```

---

## 12. 记忆双向链接设计

### 12.1 [[标题]] 语法解析

Obsidian 风格的双链语法，在记忆内容中支持 `[[标题]]` 链接：

```python
class WikiLinkParser:
    """
    [[标题]] 语法解析：
    - 正则匹配：\[\[([^\]]+)\]\]
    - 支持别名：[[目标标题|显示文本]]
    - 解析为 WikiLink 对象：{ target: str, alias: str | None }
    - 渲染时转换为可点击链接
    """

    PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

    def parse(self, content: str) -> list[WikiLink]:
        """从内容中提取所有 [[链接]]"""

    def render(self, content: str, resolver: Callable) -> str:
        """将 [[链接]] 渲染为可点击 HTML/Markdown 链接"""
```

### 12.2 反向链接自动发现

自动发现并维护反向链接关系：

```python
class BacklinkIndex:
    """
    反向链接索引：
    - 正向链接：记忆 A 包含 [[B]] → A → B
    - 反向链接：B 的反向链接列表包含 A → B ← A
    - 增量更新：记忆内容变更时，自动 diff 链接变化并更新索引
    - 存储：SQLite 表 backlinks(source_id, target_id, position, context)
    """

    async def on_memory_created(self, memory: Memory) -> None:
        """新记忆创建时，解析链接并建立双向关系"""

    async def on_memory_updated(self, memory: Memory) -> None:
        """记忆更新时，diff 链接变化并更新索引"""

    async def get_backlinks(self, memory_id: str) -> list[Backlink]:
        """获取指定记忆的所有反向链接"""

    async def get_forward_links(self, memory_id: str) -> list[ForwardLink]:
        """获取指定记忆的所有正向链接"""
```

### 12.3 图谱可视化

记忆网络图谱可视化：

```python
class MemoryGraph:
    """
    记忆图谱可视化：
    - 节点：每条记忆为一个节点
      - 按层级着色：core(金色) / domain(蓝色) / session(绿色) / ephemeral(灰色)
      - 节点大小：按 importance + access_count 加权
    - 连线：记忆间的链接关系
      - 按关联强度着色：强关联(实线/深色) / 弱关联(虚线/浅色)
      - 关联强度 = 1/距离（链接跳数）
    - 交互：
      - 点击节点 → 展开记忆详情
      - 拖拽节点 → 调整布局
      - 搜索 → 高亮匹配节点及邻居
      - 双击节点 → 进入该记忆的子图
    - 渲染：前端 D3.js force-directed graph
    """

    node_colors = {
        "core": "#FFD700",       # 金色
        "domain": "#4A90D9",     # 蓝色
        "session": "#50C878",    # 绿色
        "ephemeral": "#B0B0B0",  # 灰色
    }

    async def build_graph(self, center_id: str | None = None, depth: int = 2) -> GraphData: ...
    async def export_dot(self, graph: GraphData) -> str: ...
    async def export_json(self, graph: GraphData) -> dict: ...
```

### 12.4 智能推荐

基于语义相似度自动推荐可链接的记忆：

```python
class LinkRecommender:
    """
    智能链接推荐：
    - 基础：ChromaDB 语义相似度检索
    - 触发时机：
      1. 记忆创建/编辑时：推荐已有记忆供链接
      2. 对话中：推荐相关记忆供引用
    - 推荐策略：
      - 语义相似度 > 阈值（默认 0.7）的 Top-K 记忆
      - 排除已链接的记忆
      - 排除同一次会话的短命记忆（ephemeral）
      - 按相似度 * importance 排序
    - 用户操作：
      - 接受推荐 → 自动插入 [[标题]] 链接
      - 忽略 → 降低类似推荐权重
    """

    similarity_threshold: float = 0.7
    top_k: int = 5

    async def recommend(
        self, memory: Memory, exclude_ids: set[str] | None = None
    ) -> list[Recommendation]:
        """
        为给定记忆推荐可链接的其他记忆
        """
```

推荐结果数据结构：

```python
class Recommendation:
    target_memory: Memory
    similarity: float          # ChromaDB 余弦相似度
    reason: str               # 推荐理由（AI 生成的一句话解释）
    suggested_link_text: str  # 建议的 [[标题]] 文本
```
