# 技能生态 + MCP 市场化深入设计文档

> **版本**: v1.0
> **日期**: 2026-07-17
> **范围**: D1 技能市场 / D2 MCP 管理的端到端市场化重构
> **约束**: 设计文档,不含实际修复代码(含 schema / 伪代码 / 流程图)
> **原则**: 工程可行性优先;复用已有基础设施(`marketplace.py` / `distiller.py` / `skills` ORM 表);保持向后兼容

---

## 0. 诊断校验结论(对原始诊断的修正)

在产出设计前,对原始代码诊断做了重新核实,有两处关键修正,直接影响设计选型:

| 原诊断 | 实际情况 | 设计影响 |
|---|---|---|
| "无 skills 数据表(idx_skills_enabled 索引为死代码)" | `server/db/orm.py:87-96` **存在 `Skill` ORM 表**(含 `enabled/source/path` 字段),只是 `SkillLoader` 未使用,表为空壳 | enabled 持久化优先复用此表,而非新建 |
| "需借鉴 Hermes 自动机能生成" | `server/services/distiller.py` **已有 `SkillDistiller`(Phase 5C)**,从 `TaskRecord` 蒸馏技能并写入 `data/skills/`,阈值 3 次连续成功 | 自动沉淀基于此扩展,不另起炉灶 |

其余诊断全部核实属实:
- `SkillUpdate`(`models.py:130-134`)无 `enabled` 字段 ✅
- `SkillLoader.update_skill`(`skill_loader.py:224-269`)不接受 `enabled` ✅
- `Skill.enabled` 硬编码 `True`(`skill_loader.py:14`) ✅
- `execute_skill`(`skills.py:155-164`)不检查 enabled ✅
- `McpConnectRequest`(`models_mcp.py:9-15`)无 `transport` 字段 ✅
- `Settings.tsx:217` 发送 transport,后端 Pydantic 静默丢弃 ✅
- `mcp_client.connect_server`(`mcp_client.py:123-199`)仅 stdio 路径 ✅
- `skill_market.py` 进程内存 mock,不联网 ✅

---

## 1. 技能格式标准化设计

### 1.1 SKILL.md frontmatter 完整 schema

设计目标:**三兼容**——agentskills.io 标准 + Claude Code marketplace 字段 + Pangu 扩展字段。已有 `marketplace.py:parse_frontmatter()` 的简易 KV 解析器,扩展为支持列表/嵌套的轻量 YAML 子集(不引入 pyyaml 依赖,沿用逗号分隔列表 + JSON 内联的混合策略)。

```yaml
---
# ===== 必填字段(agentskills.io 标准) =====
name: code-reviewer                    # 唯一标识,英文蛇形命名,与文件名一致
description: 对代码进行安全/质量/可维护性三维度评审

# ===== Claude Code 兼容字段 =====
version: 1.2.0                          # 语义化版本
license: MIT                            # SPDX 标识符
allowed-tools:                          # 工具白名单,可为内建工具或 mcp:server/tool 引用
  - Read
  - Grep
  - mcp:filesystem/read_file
  - mcp:git/diff
when_to_use: 当用户提交 PR 或请求代码评审时主动建议执行
tags: [code-review, security, quality]  # 标签(逗号分隔或 JSON 数组)
author: pangu-team
homepage: https://github.com/pangu/skill-code-reviewer

# ===== Pangu 扩展字段(差异化能力) =====
enabled: true                           # 启用开关(竞品普遍缺失)
scope: user                             # user / project / local(三层层级覆盖)
priority: 50                            # 0-100,自动调度时的优先级权重
min_pangu_version: 2.3.0                # 最低兼容版本
category: development                   # 分类(用于 UI 分组)

# 权限清单(差异化安全字段)
permissions:
  network:                              # 网络访问域名白贴
    - api.github.com
    - raw.githubusercontent.com
  filesystem:                           # 文件系统范围
    read: ["./**"]
    write: ["./reviews/**"]
  sandbox: false                        # 是否强制沙箱执行
  mcp_servers: [filesystem, git]        # 依赖的 MCP 服务器

# 技能来源元数据(由 RegistrySource 安装时回填,不应手填)
source_type: github                     # builtin/custom/extension/github/url/npm/pip/registry
source_ref: owner/repo@v1.2.0           # 来源引用(ref/sha/tag)
install_path: data/skills/registry/     # 安装目录
checksum: sha256:abc123...              # 完整性校验
installed_at: 2026-07-17T10:00:00Z
---

# Code Reviewer

正文为 prompt_template,支持 {{variable}} 与 {{variable|default:"x"}} 占位符...
```

**字段兼容矩阵**:

| 字段 | agentskills.io | Claude Code | Pangu | 已有 `marketplace.py` |
|---|---|---|---|---|
| name | ✅ | ✅ | ✅ | ✅ |
| description | ✅ | ✅ | ✅ | ✅ |
| version | ✅ | ✅ | ✅ | ✅(默认 1.0.0) |
| tags | ✅ | ✅ | ✅ | ✅ |
| allowed-tools | ❌ | ✅ | ✅(兼容) | ❌ |
| when_to_use | ❌ | ✅ | ✅(兼容) | ❌ |
| **enabled** | ❌ | ❌ | ✅(**差异化**) | ❌ |
| **scope** | ❌ | ❌ | ✅(**差异化**) | ❌ |
| **permissions** | ❌ | ❌ | ✅(**差异化**) | ❌ |
| **priority** | ❌ | ❌ | ✅ | ❌ |

### 1.2 与现有 SkillLoader 三大来源的兼容

`SkillLoader.sources` 现有 3 个来源(`skill_loader.py:126-132`),保持接口不变,通过 `_MarkdownSource._parse()` 增强 + 新增 `RegistrySource` 扩展:

```python
# 伪代码: _MarkdownSource._parse 增强(向后兼容)
class _MarkdownSource(SkillSource):
    def _parse(self, f: Path) -> Skill:
        content = f.read_text(encoding="utf-8")
        fm, body = parse_extended_frontmatter(content)  # 复用 marketplace.py 解析器扩展版
        return Skill(
            name=fm.get("name", f.stem),
            description=fm.get("description", ""),
            source=self._source_tag,            # builtin / custom
            path=str(f),
            content=content,
            enabled=_resolve_enabled(fm),       # 新增:见 1.3
            tags=_as_list(fm.get("tags", [])),
            # 扩展字段(可选,通过 Skill dataclass 新增字段)
            version=fm.get("version", "1.0.0"),
            scope=fm.get("scope", "user"),
            priority=int(fm.get("priority", 50)),
            allowed_tools=_as_list(fm.get("allowed-tools", [])),
            when_to_use=fm.get("when_to_use", ""),
            permissions=fm.get("permissions", {}),
            source_type=self._source_tag,
        )
```

**`ExtensionSource` 兼容**: Python entry point 的 `get_skill_info()` 返回值扩展支持新字段;旧 entry point 不返回新字段时使用默认值,**不破坏现有扩展**。

**`BuiltinSource` 兼容**: `server/skills/*.md` 文件保持现有最小 frontmatter(name/description/tags),缺失字段走默认值(`enabled=True / scope=user / priority=50`),**零改动可用**。

### 1.3 enabled 字段持久化方案

**核心矛盾**: frontmatter 是文件级共享的(随 git 分发),而 enabled 是用户私有状态。直接写回 frontmatter 会导致:
- 同步时覆盖用户选择
- git 提交噪声
- 多设备状态冲突

**决策: 双层模型——frontmatter 声明默认值,状态文件覆盖**

#### 持久化层级(优先级从高到低)

```
1. ~/.pangu-nebula/skills-state.local.json   (本机覆盖,不入 git,最高优先级)
2. ./.pangu/skills-state.json                (项目级,入项目 git)
3. ~/.pangu-nebula/skills-state.json         (用户级,跨项目默认)
4. frontmatter.enabled                       (技能自带默认值)
5. Skill.enabled = True                      (硬编码兜底)
```

**为什么三层状态文件?**
- 用户级:用户在所有项目中的偏好(如禁用某个 builtin 技能)
- 项目级:某个项目的特殊需求(如某项目必须启用 `legacy-migration` 技能),可随项目分发
- 本机级:临时实验性开关,不影响他人

#### 状态文件 schema(`skills-state.json`)

```json
{
  "version": 1,
  "skills": {
    "code-reviewer": {
      "enabled": false,
      "scope": "user",
      "updated_at": "2026-07-17T10:00:00Z",
      "updated_by": "cli"
    },
    "legacy-migration": {
      "enabled": true,
      "scope": "project",
      "updated_at": "2026-07-17T10:00:00Z"
    }
  },
  "active_profile": "developer"
}
```

#### `_resolve_enabled()` 合并逻辑(伪代码)

```python
def _resolve_enabled(fm: dict, name: str, loader: SkillLoader) -> bool:
    # 1. 本机级覆盖
    if name in loader._state_local["skills"]:
        return loader._state_local["skills"][name]["enabled"]
    # 2. 项目级覆盖
    if name in loader._state_project["skills"]:
        return loader._state_project["skills"][name]["enabled"]
    # 3. 用户级覆盖
    if name in loader._state_user["skills"]:
        return loader._state_user["skills"][name]["enabled"]
    # 4. frontmatter 默认值
    if "enabled" in fm:
        return bool(fm["enabled"])
    # 5. 兜底
    return True
```

#### 与 `skills` ORM 表的关系

已存在的 `orm.py:87-96` `Skill` 表(name/source/path/enabled)**作为运行时缓存与跨设备同步的载体**,不作为权威源:
- 启动时由 `SkillLoader.scan_all()` 全量重建
- `enabled` 字段由状态文件计算后写入
- CRDT 同步(Phase 9A)可将 `skills` 表通过 E2EE 通道跨设备同步
- `idx_skills_enabled` 索引从此**不再是死代码**,服务于"列出所有已启用技能"的高频查询

### 1.4 CLI 命令设计

新增 `server/cli/skills_cli.py`,通过 Tauri command 或独立 `pangu-skill` CLI 暴露:

```
/skill list [--source builtin|custom|registry] [--enabled|--disabled] [--tag <t>]
/skill enable <name> [--scope user|project|local]
/skill disable <name> [--scope user|project|local]
/skill info <name>                  # 显示合并后的有效状态与来源层级
/skill install <name|url|owner/repo>   # 见 §2
/skill uninstall <name>
/skill update [name]                # 检查更新
/skill profile save <profile-name>  # 保存当前启用集
/skill profile load <profile-name>
/skill profile list
/skill profile delete <profile-name>
```

`enable/disable` 写入哪一层由 `--scope` 决定,默认 `user`。

### 1.5 Skill Profile 切换设计

**场景**: 开发时启用 `code-reviewer / test-generator / git-helper`;写文档时切换到 `doc-writer / diagram-gen / spell-check`。

#### Profile schema(`~/.pangu-nebula/skill-profiles.json`)

```json
{
  "version": 1,
  "profiles": {
    "developer": {
      "description": "开发场景",
      "skills": ["code-reviewer", "test-generator", "git-helper"],
      "disabled": ["doc-writer"]
    },
    "writer": {
      "description": "文档场景",
      "skills": ["doc-writer", "diagram-gen", "spell-check"],
      "disabled": ["code-reviewer"]
    },
    "minimal": {
      "description": "最小集",
      "skills": [],
      "disabled": []
    }
  },
  "active": "developer"
}
```

#### Profile 加载流程

```
profile load <name>
  ├─ 读取 profiles.json[name].skills 与 .disabled
  ├─ 对所有已扫描技能:
  │   ├─ 在 skills 列表 → set enabled=True (scope=local, 临时)
  │   ├─ 在 disabled 列表 → set enabled=False (scope=local, 临时)
  │   └─ 不在任一列表 → 保持原状态
  ├─ 写入 skills-state.local.json
  ├─ 更新 active_profile 字段
  └─ 触发 SkillLoader 重新扫描 + 广播 UI 刷新事件
```

**重要**: profile 切换只写 `local` 层(本机临时),**不污染 user/project 层**——这是设计关键,避免切换 profile 永久覆盖用户偏好。

---

## 2. 社区联结方案

### 2.1 marketplace.json schema 适配

**直接复用 Claude Code 的 6 种 source 类型**,与 Pangu 现有 `data/skills/*.md` 单文件来源形成互补:

```json
{
  "version": 1,
  "registry": "pangu-official",
  "updated_at": "2026-07-17T00:00:00Z",
  "skills": [
    {
      "name": "code-reviewer",
      "description": "代码三维度评审",
      "version": "1.2.0",
      "author": "pangu-team",
      "tags": ["code-review", "security"],
      "homepage": "https://github.com/pangu/skill-code-reviewer",
      "license": "MIT",
      "safety_level": "official",
      "rating": 4.8,
      "installs": 12345,
      "sources": [
        {"type": "github", "repo": "pangu/skill-code-reviewer", "ref": "v1.2.0", "subdir": "skills/code-reviewer"},
        {"type": "url", "url": "https://raw.githubusercontent.com/pangu/skill-code-reviewer/v1.2.0/SKILL.md"},
        {"type": "npm", "package": "@pangu/skill-code-reviewer", "version": "^1.2.0"},
        {"type": "pip", "package": "pangu-skill-code-reviewer", "version": ">=1.2.0"},
        {"type": "relative", "path": "./skills/code-reviewer"},
        {"type": "git-subdir", "repo": "pangu/skills-monorepo", "ref": "main", "subdir": "code-reviewer"}
      ]
    }
  ]
}
```

**6 种 source 类型映射到 Pangu 安装策略**:

| source.type | 安装路径 | 版本锚定 | 离线可用 |
|---|---|---|---|
| `github` | `git clone` 到 `data/skills/registry/<name>/` | ref (tag/sha/branch) | ✅ |
| `url` | HTTP 下载单文件到 `data/skills/registry/<name>.md` | URL 不变,可加 `?v=` | ❌ |
| `npm` | `npm pack` 解包到 `data/skills/registry/<name>/` | package.json version | ✅ |
| `pip` | `pip download` 解包到 `data/skills/registry/<name>/` | version spec | ✅ |
| `relative` | 软链接或拷贝 | 跟随源目录 | ✅ |
| `git-subdir` | sparse checkout | ref + subdir | ✅ |

### 2.2 CommunityRegistryClient 设计

替代当前 `skill_market.py` 的进程内存 mock,新增 `server/services/registry_client.py`:

```python
# 伪代码
class CommunityRegistryClient:
    """社区技能仓库客户端:拉取索引、缓存、安装、更新检查"""

    DEFAULT_REGISTRIES = [
        "https://registry.pangu-nebula.dev/marketplace.json",   # Pangu 官方
        "https://agentskills.io/index.json",                    # agentskills.io 标准
    ]
    CACHE_TTL = 3600  # 1 小时

    def __init__(self, cache_dir: str = "data/registry-cache"):
        self.cache_dir = Path(cache_dir)
        self._cache: dict[str, dict] = {}    # registry_url -> marketplace.json
        self._index: dict[str, list[dict]] = {}  # name -> [skill entries] (跨 registry 聚合)

    async def fetch_index(self, registry_url: str, force: bool = False) -> dict:
        """拉取单个 registry 的 marketplace.json,带缓存"""
        cache_file = self.cache_dir / f"{hashlib.sha256(registry_url.encode()).hexdigest()}.json"
        if not force and cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < self.CACHE_TTL:
                return json.loads(cache_file.read_text("utf-8"))
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(registry_url)
            resp.raise_for_status()
            data = resp.json()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        return data

    async def sync_all(self) -> dict:
        """同步所有已配置 registry,聚合索引"""
        all_skills = []
        for url in self._configured_registries():
            try:
                mp = await self.fetch_index(url)
                for skill in mp.get("skills", []):
                    skill["_registry"] = url
                    all_skills.append(skill)
            except Exception as e:
                logger.warning(f"registry {url} sync failed: {e}")
        # 聚合:同 name 多 source 合并
        self._index = self._merge_by_name(all_skills)
        return {"synced": len(self._index), "registries": len(self._configured_registries())}

    async def install(self, name: str, source_idx: int = 0, target_scope: str = "user") -> dict:
        """安装技能:按 source 类型分发到对应 installer"""
        if name not in self._index:
            raise KeyError(f"skill '{name}' not in registry")
        skill_meta = self._index[name][0]   # 默认取第一个 source
        source = skill_meta["sources"][source_idx]
        installer = self._get_installer(source["type"])
        result = await installer.install(skill_meta, source, target_dir=f"data/skills/registry/{name}")
        # 完整性校验 + 安全扫描
        await self._verify_integrity(result, skill_meta)
        await self._security_scan(result.path)
        # 写入 skills-state 标记为 registry 来源
        self._mark_installed(name, source, result)
        return result

    def _get_installer(self, source_type: str) -> SkillInstallerBase:
        return {
            "github":     GithubInstaller(),
            "url":        UrlInstaller(),
            "npm":        NpmInstaller(),
            "pip":        PipInstaller(),
            "relative":   RelativeInstaller(),
            "git-subdir": GitSubdirInstaller(),
        }[source_type]
```

### 2.3 4 种安装路径设计

#### 路径 A: GitHub repo 安装(`owner/repo`)

```python
class GithubInstaller(SkillInstallerBase):
    async def install(self, meta, source, target_dir):
        repo = source["repo"]            # owner/repo
        ref = source.get("ref", "main")
        subdir = source.get("subdir", "")
        # 浅克隆到临时目录,检出指定 ref
        tmp = Path(tempfile.mkdtemp())
        await run(["git", "clone", "--depth=1", "--branch", ref,
                   f"https://github.com/{repo}.git", str(tmp)])
        src = tmp / subdir if subdir else tmp
        # 定位 SKILL.md
        skill_file = self._find_skill_md(src)
        # 拷贝到目标目录
        dest = Path(target_dir)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_file, dest / "SKILL.md")
        # 锚定版本:记录 commit sha
        sha = (await run(["git", "-C", str(tmp), "rev-parse", "HEAD"])).strip()
        return InstallResult(path=dest / "SKILL.md", ref=ref, sha=sha, source_type="github")
```

#### 路径 B: URL 安装(`.git` 结尾或直链)

```python
class UrlInstaller(SkillInstallerBase):
    async def install(self, meta, source, target_dir):
        url = source["url"]
        if url.endswith(".git"):
            # 当作 git URL 处理
            return await GitUrlInstaller().install(meta, source, target_dir)
        # 单文件下载
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
        dest = Path(target_dir)
        dest.mkdir(parents=True, exist_ok=True)
        skill_file = dest / "SKILL.md"
        skill_file.write_text(resp.text, "utf-8")
        return InstallResult(path=skill_file, ref=url, sha=sha256(resp.content).hexdigest(),
                             source_type="url")
```

#### 路径 C: npm / pip 安装

```python
class NpmInstaller(SkillInstallerBase):
    async def install(self, meta, source, target_dir):
        pkg = source["package"]          # @pangu/skill-code-reviewer
        ver = source.get("version", "latest")
        tmp = Path(tempfile.mkdtemp())
        # npm pack 下载 tarball(不全局安装)
        await run(["npm", "pack", f"{pkg}@{ver}"], cwd=tmp)
        tarball = next(tmp.glob("*.tgz"))
        # 解包提取 skills/ 目录
        await run(["tar", "-xzf", str(tarball)], cwd=tmp)
        src = tmp / "package" / "skills"
        # 拷贝到目标
        dest = Path(target_dir)
        shutil.copytree(src, dest, dirs_exist_ok=True)
        return InstallResult(path=dest, ref=f"{pkg}@{ver}", source_type="npm")
```

#### 路径 D: 从文档自动生成(借鉴 Hermes)

**这是 Pangu 的差异化创新**,基于已有 `distiller.py` 扩展:

```python
class DocToSkillGenerator:
    """从对话/文档/Wiki 自动生成技能(扩展自 Phase 5C SkillDistiller)"""

    async def from_conversation(self, conversation_id: int) -> dict:
        """任务完成时自动触发:从成功对话提取技能"""
        # 1. 加载对话历史
        conv = await self._load_conversation(conversation_id)
        # 2. 判断是否值得沉淀(任务成功 + 步骤≥3 + 包含工具调用)
        if not self._is_distillable(conv):
            return {"ok": False, "reason": "对话不满足沉淀条件"}
        # 3. 复用 distiller 的 LLM 蒸馏流程
        distiller = SkillDistiller()
        result = await distiller.distill_from_success([self._conv_to_record(conv)])
        if not result.success:
            return {"ok": False, "reason": result.reason}
        # 4. 增强 frontmatter(Pangu 扩展字段)
        enhanced = self._enhance_frontmatter(result.skill_content, conv)
        # 5. 写入 data/skills/auto/<name>.md(隔离目录,不污染主目录)
        dest = Path("data/skills/auto") / f"{result.skill_name}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(enhanced, "utf-8")
        return {"ok": True, "skill_name": result.skill_name, "path": str(dest),
                "needs_review": True}
```

**与 `distiller.py` 的关系**: `distiller.py` 基于 `TaskRecord` 蒸馏(3 次连续成功阈值);本设计扩展为单次对话级即时沉淀,降低阈值、增加隔离目录 `data/skills/auto/`、强制 `needs_review: true`,**等用户在 UI 确认后才提升到 `data/skills/custom/`**。

### 2.4 SkillLoader.sources 扩展:新增 RegistrySource

```python
class RegistrySource(_MarkdownSource):
    """从 data/skills/registry/ 加载社区安装的技能"""

    def __init__(self, base_dir: str = "data/skills/registry"):
        super().__init__(base_dir, "registry")
        # registry 子目录递归扫描(每个技能一个子目录)
    async def scan(self) -> list[Skill]:
        if not self.base_dir.exists():
            return []
        skills = []
        for skill_md in self.base_dir.rglob("SKILL.md"):
            skills.append(self._parse(skill_md))
        return skills

class AutoSource(_MarkdownSource):
    """从 data/skills/auto/ 加载自动生成的技能(needs_review)"""
    def __init__(self):
        super().__init__("data/skills/auto", "auto")
```

`SkillLoader.sources` 更新为 5 个:`[BuiltinSource, CustomSource, AutoSource, RegistrySource, ExtensionSource]`,**保留原顺序优先级**(builtin 不可被同名覆盖)。

### 2.5 安装后验证与版本管理

#### 完整性校验

```python
async def _verify_integrity(self, install_result, meta):
    """三层校验"""
    # 1. frontmatter 合法性(name 必填,description 必填)
    content = Path(install_result.path).read_text("utf-8")
    fm, _ = parse_extended_frontmatter(content)
    if not fm.get("name"):
        raise SkillValidationError("missing name in frontmatter")
    if not fm.get("description"):
        raise SkillValidationError("missing description in frontmatter")
    # 2. checksum 校验(若 meta 提供)
    if meta.get("checksum"):
        actual = sha256(Path(install_result.path).read_bytes()).hexdigest()
        expected = meta["checksum"].split(":", 1)[-1]
        if actual != expected:
            raise SkillValidationError(f"checksum mismatch: {actual} != {expected}")
    # 3. min_pangu_version 兼容性
    min_ver = fm.get("min_pangu_version")
    if min_ver and not _version_satisfied(min_ver):
        raise SkillValidationError(f"requires pangu >= {min_ver}, current {PANGU_VERSION}")
```

#### 安全扫描(伪代码,与 §3.7 安全审计共享规则引擎)

```python
async def _security_scan(self, skill_path: str):
    """轻量静态扫描"""
    content = Path(skill_path).read_text("utf-8")
    # 1. prompt injection 模式检测(复用 Phase 8A InjectionChecker)
    from ..services.security import InjectionChecker
    checker = InjectionChecker()
    issues = checker.scan(content, context="skill")
    # 2. 危险工具调用模式(如 mcp:shell/exec)
    dangerous = self._scan_dangerous_tools(content)
    # 3. 网络域名白名单校验(与 permissions.network 比对)
    # 扫描结果记录但不阻塞(除非 critical 级)
    if any(i["severity"] == "critical" for i in issues + dangerous):
        raise SkillSecurityError("critical security issues detected")
```

#### 版本管理

每个安装记录写入 `data/skills/registry/.installed.json`:

```json
{
  "code-reviewer": {
    "source_type": "github",
    "source_ref": "v1.2.0",
    "source_sha": "abc123def456...",
    "installed_version": "1.2.0",
    "installed_at": "2026-07-17T10:00:00Z",
    "auto_update": false,
    "checksum": "sha256:..."
  }
}
```

#### 更新通知机制

```python
class UpdateChecker:
    """启动时 + 定时(每日 cron)检查 registry 中已安装技能是否有新版本"""
    async def check_updates(self) -> list[dict]:
        updates = []
        installed = self._load_installed_index()
        await self.registry_client.sync_all()
        for name, info in installed.items():
            latest = self.registry_client._index.get(name, [{}])[0]
            if self._is_newer(latest.get("version"), info["installed_version"]):
                updates.append({
                    "name": name,
                    "current": info["installed_version"],
                    "latest": latest["version"],
                    "changelog_url": latest.get("homepage", "") + "/releases",
                })
        # 通过 WebSocket 推送到前端(复用现有事件总线)
        await self._broadcast("skill.update.available", updates)
        return updates
```

---

## 3. MCP 市场化方案

### 3.1 McpConnectRequest 模型扩展

```python
# server/api/models_mcp.py(扩展)
from typing import Literal
from pydantic import BaseModel, Field

class McpConnectRequest(BaseModel):
    """连接 MCP 服务器请求(扩展 transport + scope + 安全字段)"""
    name: str
    transport: Literal["stdio", "sse", "http"] = "stdio"   # 新增,默认 stdio 向后兼容
    # stdio 模式字段
    command: str | None = None
    args: list[str] = []
    env: dict = {}
    # sse / http 模式字段
    url: str | None = None                                  # sse/http 端点
    headers: dict[str, str] = {}                            # http 认证头
    # 层级与安全
    scope: Literal["user", "project", "local"] = "user"     # 新增,见 §3.6
    safety_level: Literal["official", "verified", "community", "unknown"] = "unknown"
    auto_start: bool = True                                 # 启动时是否自动连接
    permissions: dict = {}                                  # 见 §3.7

# 新增: MCP 安装记录(从市场安装时使用)
class McpInstallRequest(BaseModel):
    """从 MCP 市场安装"""
    name: str
    transport: Literal["stdio", "sse", "http"]
    source: str                          # smithery / pangu-official / manual
    source_ref: str                      # npx package / url / pip package
    category: str = "general"
    auto_start: bool = True
```

### 3.2 mcp_client.connect_server 分支处理

现有 `mcp_client.py:123-199` 仅 stdio。重构为三 transport 分发,**保持原 stdio 路径行为完全不变**(向后兼容):

```python
class MCPClient:
    async def connect_server(self, name, command=None, args=None, env=None,
                             transport="stdio", url=None, headers=None) -> dict:
        # 路由到对应 transport handler
        if transport == "stdio":
            return await self._connect_stdio(name, command, args, env)
        elif transport == "sse":
            return await self._connect_sse(name, url, headers)
        elif transport == "http":
            return await self._connect_http(name, url, headers)
        raise ValueError(f"unsupported transport: {transport}")

    async def _connect_stdio(self, name, command, args, env):
        """原 connect_server 逻辑(保持不变)"""
        # ... 现有 asyncio.create_subprocess_exec + initialize 握手 ...

    async def _connect_http(self, name, url, headers):
        """HTTP transport:使用 httpx 长连接,Streamable JSON-RPC"""
        conn = _ServerConnection(name, transport="http", url=url, headers=headers)
        client = httpx.AsyncClient(base_url=url, headers=headers, timeout=None)
        # HTTP initialize 握手
        result = await self._http_request(client, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pangu-nebula", "version": "1.0.0"},
        })
        conn.client = client
        conn.server_info = result
        conn.connected = True
        self._servers[name] = conn
        return {"name": name, "transport": "http", "url": url,
                "connected": True, "server_info": result}

    async def _connect_sse(self, name, url, headers):
        """SSE transport:EventSource 长连接 + POST 请求"""
        conn = _ServerConnection(name, transport="sse", url=url, headers=headers)
        # SSE 端点接收事件,POST 端点发送请求(标准 MCP SSE 双通道)
        sse_client = httpx.AsyncClient(timeout=None)
        post_url = await self._sse_handshake(sse_client, url, headers)
        conn.sse_client = sse_client
        conn.post_url = post_url
        conn.connected = True
        self._servers[name] = conn
        return {"name": name, "transport": "sse", "connected": True}
```

**`_ServerConnection` 扩展**: 增加 `transport / url / headers / client / post_url` 字段;原 `process` 字段仅在 stdio 时存在。

### 3.3 预置 MCP 目录设计

#### 双源目录策略

```python
class McpDirectory:
    """MCP 目录聚合:Smithery + Pangu 精选"""

    SOURCES = {
        "smithery": "https://registry.smithery.ai/v1/servers.json",   # 3000+ servers
        "pangu-official": "https://registry.pangu-nebula.dev/mcp-directory.json",
    }

    async def sync(self) -> dict:
        """同步两个目录源,去重合并"""
        smithery = await self._fetch_smithery()
        official = await self._fetch_pangu_official()
        merged = self._merge_by_name(official + smithery)   # official 优先
        return {"total": len(merged), "official": len(official), "smithery": len(smithery)}
```

#### 目录数据结构

```json
{
  "name": "filesystem",
  "description": "安全文件系统访问 MCP 服务器",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/allowed/path"],
  "category": "filesystem",
  "rating": 4.9,
  "installs": 89234,
  "safety_level": "official",
  "homepage": "https://github.com/modelcontextprotocol/servers",
  "source": "smithery",
  "capabilities": ["read", "write", "search"],
  "install_command": "npx @smithery/cli install filesystem",
  "verified_at": "2026-07-01T00:00:00Z",
  "permissions_required": {
    "filesystem": { "read": ["**"], "write": ["/allowed/path/**"] }
  }
}
```

#### Smithery 客户端集成(伪代码)

```python
class SmitheryClient:
    """Smithery 注册中心客户端"""
    BASE = "https://registry.smithery.ai/v1"

    async def list_servers(self, q: str = "", category: str = "", limit: int = 50) -> list[dict]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(f"{self.BASE}/servers",
                               params={"q": q, "category": category, "limit": limit})
            return resp.json()["servers"]

    async def install(self, name: str, config: dict = None) -> dict:
        """一键安装 Smithery MCP(走 npx @smithery/cli)"""
        cmd = ["npx", "@smithery/cli", "install", name]
        if config:
            cmd.extend(["--config", json.dumps(config)])
        result = await run(cmd)
        return {"installed": True, "name": name, "log": result.stdout}

    async def get_install_command(self, name: str) -> str:
        """返回可直接复制的安装命令(供 UI 展示)"""
        return f"npx @smithery/cli install {name}"
```

### 3.4 前端 MCP 市场卡片网格设计

替代 `Settings.tsx:1020-1049` 的手动表单(保留为高级入口):

```
┌────────────────────────────────────────────────────────────────┐
│ 🔌 MCP 市场                              [🔍 搜索] [分类 ▼]    │
│ ────────────────────────────────────────────────────────────── │
│ [浏览市场] [已安装] [手动添加 ↓]                              │
│                                                                │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│ │ 📁 filesystem│ │ 🐙 github    │ │ 🌐 web-fetch │            │
│ │ ⭐ 4.9 (89k) │ │ ⭐ 4.8 (45k) │ │ ⭐ 4.7 (23k) │            │
│ │ 🟢 official  │ │ 🟢 official  │ │ 🟡 verified  │            │
│ │ stdio        │ │ stdio        │ │ http         │            │
│ │ 安全文件访问 │ │ GitHub 仓库  │ │ 网页抓取     │            │
│ │              │ │              │ │              │            │
│ │ [详情] [安装]│ │ [详情] [安装]│ │ [详情] [安装]│            │
│ └──────────────┘ └──────────────┘ └──────────────┘            │
│                                                                │
│ --- 已安装 (3) ---                                             │
│ ✅ filesystem  🟢 healthy  [启用] [配置] [日志] [卸载]        │
│ ✅ github      🟡 degraded [启用] [配置] [日志] [卸载]        │
│ ⚪ database    🔴 offline   [启用] [配置] [日志] [卸载]       │
└────────────────────────────────────────────────────────────────┘
```

**卡片字段**: 名称 / 图标 / 描述 / 来源徽章(official🟢 / verified🟡 / community🔵 / unknown⚪) / 评分 / 安装数 / transport 标签 / 健康状态点 / 操作按钮。

### 3.5 MCP 健康状态设计

#### 启动时自动 ping

```python
class McpHealthMonitor:
    """MCP 服务器健康监控"""

    PING_INTERVAL = 60   # 秒
    PING_TIMEOUT = 5

    async def ping(self, server_name: str) -> dict:
        """ping = 调用 tools/list 并测量延迟"""
        start = time.monotonic()
        try:
            await asyncio.wait_for(
                mcp_client.list_tools(server_name),
                timeout=self.PING_TIMEOUT
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            status = "healthy" if latency_ms < 1000 else "degraded"
            return {"status": status, "latency_ms": latency_ms}
        except asyncio.TimeoutError:
            return {"status": "degraded", "latency_ms": self.PING_TIMEOUT * 1000}
        except Exception as e:
            return {"status": "offline", "error": str(e), "latency_ms": None}

    async def start_monitoring(self):
        """后台定时 ping 所有已连接服务器,广播状态变化"""
        while True:
            for name in mcp_client.list_server_names():
                result = await self.ping(name)
                await self._record(name, result)
                if self._status_changed(name, result["status"]):
                    await self._broadcast("mcp.health.changed", {"name": name, **result})
            await asyncio.sleep(self.PING_INTERVAL)
```

#### UI 状态映射

| 状态 | 颜色 | 触发条件 |
|---|---|---|
| `healthy` | 🟢 绿 | ping 成功且 latency < 1s |
| `degraded` | 🟡 黄 | ping 成功但 latency ≥ 1s,或 tools/list 失败但连接存在 |
| `offline` | 🔴 红 | ping 失败,连接断开 |
| `starting` | ⚪ 灰 | 正在连接中 |

#### CLI 命令

```
/mcp status                  # 列出所有 MCP + 健康状态
/mcp doctor [name]           # 诊断单个 MCP(连接/握手/工具列表/延迟)
/mcp restart <name>          # 重启 MCP 连接
/mcp logs <name> [--follow]  # 查看 MCP 服务器日志(stderr)
/mcp tools <name>            # 列出 MCP 暴露的工具
```

### 3.6 scope 三层设计(user/project/local)

复用 §1.3 的状态文件模式,MCP 配置同样三层覆盖:

```
~/.pangu-nebula/mcp-servers.json          (user 级,所有项目共享)
./.pangu/mcp-servers.json                  (project 级,入 git)
~/.pangu-nebula/mcp-servers.local.json     (local 级,临时,不入 git)
```

#### 配置文件 schema

```json
{
  "version": 1,
  "servers": {
    "filesystem": {
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/allowed"],
      "scope": "user",
      "auto_start": true,
      "safety_level": "official",
      "enabled": true,
      "permissions": {"filesystem": {"read": ["/allowed/**"], "write": []}}
    }
  }
}
```

#### 启动时加载流程

```
应用启动
  ├─ 合并三层配置(user < project < local 优先级)
  ├─ 对每个 enabled=true 且 auto_start=true 的 server:
  │   ├─ 调用 mcp_client.connect_server(transport, ...)
  │   ├─ 失败则记录 offline 状态,不阻塞其他
  │   └─ 成功则启动健康监控
  └─ 广播 mcp.ready 事件给前端
```

### 3.7 安全审计设计

#### 安装时权限清单弹窗

MCP 市场卡片点击「安装」时,先弹出权限确认(类似手机 App 权限请求):

```
┌──────────────────────────────────────────────────┐
│ ⚠️ 安装 filesystem MCP                           │
│ ──────────────────────────────────────────────── │
│ 来源: 🟢 official (modelcontextprotocol)        │
│ 评分: ⭐ 4.9 (89,234 次安装)                    │
│                                                  │
│ 此 MCP 将获得以下权限:                          │
│ 📁 文件系统读取: /home/user/**                  │
│ 📁 文件系统写入: /home/user/docs/**             │
│ 🌐 网络: 无                                     │
│ 🔧 工具数: 8 (read_file, write_file, ...)      │
│                                                  │
│ [查看完整 SKILL.md] [查看源码]                  │
│                                                  │
│         [取消]  [仅本次启用]  [永久启用并信任] │
└──────────────────────────────────────────────────┘
```

#### 来源可信度徽章体系

```python
def compute_safety_level(meta: dict) -> str:
    """四级可信度计算"""
    # official: Pangu 官方维护 + 通过安全审计
    if meta.get("source") == "pangu-official" and meta.get("verified_at"):
        return "official"
    # verified: Smithery/agentskills.io 验证 + ≥1000 installs + rating ≥4.0
    if (meta.get("source") == "smithery" and meta.get("installs", 0) >= 1000
            and meta.get("rating", 0) >= 4.0 and meta.get("verified_at")):
        return "verified"
    # community: 已知社区来源但未达 verified 标准
    if meta.get("source") in ("smithery", "github", "npm", "pip"):
        return "community"
    # unknown: 未知来源
    return "unknown"
```

#### 工具调用审计日志

复用已有 `audit_logs` 表(`orm.py` + `models.py:225-250 AuditLogCreate`):

```python
class McpAuditLogger:
    """所有 MCP 工具调用写入 audit_logs"""

    async def log_call(self, server_name, tool_name, arguments, result, duration_ms):
        await audit_log_create(AuditLogCreate(
            action=f"mcp.tool.call",
            resource=f"mcp:{server_name}/{tool_name}",
            input_summary=_truncate(json.dumps(arguments, ensure_ascii=False), 500),
            output_summary=_truncate(_extract_text(result), 500),
            duration_ms=duration_ms,
            success=not result.get("isError", False),
            details={"server": server_name, "tool": tool_name, "transport": "..."}
        ))

    async def log_install(self, name, source, permissions):
        await audit_log_create(AuditLogCreate(
            action="mcp.install",
            resource=f"mcp:{name}",
            details={"source": source, "permissions": permissions}
        ))
```

**MCP 调用拦截**: 在 `mcp_client.call_tool` 前后注入审计 hook;若 `permissions` 不允许当前调用(如该 MCP 试图访问未授权路径),拦截并记录。

---

## 4. 技能/MCP/角色联动设计

### 4.1 技能与 Persona 关联

#### 数据模型(新增 `persona_skills` 关联表)

```python
# server/db/orm.py(新增)
class PersonaSkill(Base):
    """Persona ↔ Skill 多对多绑定"""
    __tablename__ = "persona_skills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"))
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False)  # 引用 Skill.name
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)          # 该 persona 下是否启用
    priority_override: Mapped[int | None] = mapped_column(Integer)        # persona 内优先级覆盖
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("persona_id", "skill_name", name="uq_persona_skill"),)
```

#### Persona 激活时的技能加载流程

```
Persona 激活 (POST /personas/{id}/activate)
  ├─ 读取 persona_skills WHERE persona_id = X AND enabled = true
  ├─ 对每个绑定技能:
  │   ├─ 在 SkillLoader 缓存中查找
  │   ├─ 若全局 enabled=False 但 persona 绑定 enabled=True → persona 内临时启用
  │   └─ 应用 priority_override(影响自动调度顺序)
  ├─ 构建 active_skill_set = {全局启用 ∪ persona 绑定启用} - persona 显式禁用
  └─ 缓存到内存,供 SkillEngine.execute_skill 与 LLM tool 选择使用
```

#### Persona model 扩展

```python
# models.py 新增
class PersonaSkillBindRequest(BaseModel):
    """为 Persona 绑定技能集"""
    skills: list[str]                    # skill names
    enabled: bool = True
    priority_override: int | None = None

class PersonaSkillProfileRequest(BaseModel):
    """保存为 persona 技能 profile"""
    profile_name: str
    skills: list[str]
```

### 4.2 MCP 作为技能的工具来源

#### allowed-tools 字段引用 MCP 工具的语法

frontmatter 中 `allowed-tools` 支持 `mcp:<server>/<tool>` 命名空间:

```yaml
allowed-tools:
  - Read                                    # Pangu 内建工具
  - Grep
  - mcp:filesystem/read_file                # 引用 filesystem MCP 的 read_file 工具
  - mcp:git/*                               # 引用 git MCP 的所有工具(通配)
  - mcp:github/create_pull_request          # 引用 github MCP 的特定工具
```

#### 运行时工具解析与绑定

```python
class SkillToolResolver:
    """解析技能的 allowed-tools,聚合内建 + MCP 工具"""

    async def resolve(self, skill: Skill) -> list[ToolDefinition]:
        tools = []
        for entry in skill.allowed_tools:
            if entry.startswith("mcp:"):
                # MCP 工具引用
                _, server, tool = entry.split("/", 1) if "/" in entry else (entry, "*", "*")
                # 等价于: mcp:<server>/<tool>
                server_name = entry[4:].split("/")[0]
                tool_pattern = entry[4:].split("/", 1)[1] if "/" in entry[4:] else "*"
                mcp_tools = await self._load_mcp_tools(server_name, tool_pattern)
                tools.extend(mcp_tools)
            else:
                # 内建工具
                builtin = self._get_builtin_tool(entry)
                if builtin:
                    tools.append(builtin)
        return tools

    async def _load_mcp_tools(self, server_name, pattern):
        """从已连接的 MCP 服务器加载匹配工具"""
        all_tools = await mcp_client.list_tools(server_name)
        if pattern == "*":
            return [self._adapt_mcp_tool(server_name, t) for t in all_tools]
        return [self._adapt_mcp_tool(server_name, t)
                for t in all_tools if t["name"] == pattern]
```

#### MCP 缺失时的降级策略

```
技能执行时解析 allowed-tools:
  ├─ mcp:filesystem/read_file
  ├─ filesystem MCP 未连接?
  │   ├─ 是 auto_start 配置 → 尝试自动连接
  │   ├─ 连接成功 → 注入工具
  │   └─ 连接失败 → 该工具缺失,记录 warning
  └─ 技能仍可执行,但告知 LLM "工具不可用"
```

### 4.3 Skill Profile 与 Persona Profile 联动

#### 双向绑定模式

提供两种联动模式,由用户选择:

**模式 A: Persona 主导(推荐)**
切换 Persona → 自动应用该 Persona 绑定的技能集(§4.1)。Skill profile 是 Persona 的子属性。

**模式 B: Profile 独立切换**
`/skill profile load developer` 独立切换技能集,不改变当前 Persona。适用于"在同一个 Persona 下临时切换工作场景"。

#### 联动状态机

```
                    ┌─────────────────────┐
                    │  Persona 切换事件    │
                    └──────────┬──────────┘
                               │
                  ┌────────────┼────────────┐
                  ▼            ▼            ▼
        ┌──────────────┐ ┌──────────┐ ┌──────────────┐
        │ 加载 persona │ │ 加载     │ │ 广播 UI 刷新 │
        │ _skills 绑定 │ │ MCP 配置 │ │ (技能+MCP)   │
        └──────────────┘ └──────────┘ └──────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Persona 也可绑定    │
                    │ MCP 服务器子集       │
                    │ (persona_mcp_servers)│
                    └─────────────────────┘
```

#### Persona-MCP 绑定(可选,模式 A 扩展)

```python
class PersonaMcpServer(Base):
    """Persona ↔ MCP 服务器绑定"""
    __tablename__ = "persona_mcp_servers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"))
    server_name: Mapped[str] = mapped_column(String(255))
    auto_connect: Mapped[bool] = mapped_column(Boolean, default=True)
```

### 4.4 自动 Skill 生成(借鉴 Hermes,基于 distiller.py 扩展)

#### 任务完成自动沉淀流程

扩展现有 `distiller.py` 的触发点(从"3 次连续成功"放宽到"单次成功 + 高质量信号"):

```python
class AutoSkillGenerator:
    """扩展自 SkillDistiller(Phase 5C)"""

    # 即时沉淀触发条件(比 distiller.py 的 3 次阈值更宽松)
    INSTANT_DISTILL_CONDITIONS = {
        "min_steps": 3,              # 对话至少 3 轮工具调用
        "min_tools_used": 2,         # 至少使用 2 个工具
        "must_succeed": True,        # 任务必须成功
        "task_type_whitelist": ["code_edit", "research", "data_analysis"]
    }

    async def on_task_complete(self, conversation_id: int, task_record: TaskRecord):
        """任务完成事件钩子(由 conversation API 触发)"""
        # 1. 评估是否值得沉淀
        conv = await self._load_conversation(conversation_id)
        if not self._meets_conditions(conv, task_record):
            return {"distilled": False, "reason": "不满足沉淀条件"}

        # 2. 复用 distiller 的 LLM 蒸馏
        distiller = SkillDistiller()
        result = await distiller.distill_from_success([task_record])
        if not result.success:
            return {"distilled": False, "reason": result.reason}

        # 3. 增强 frontmatter(Pangu 扩展字段)
        enhanced_content = self._enhance_frontmatter(
            result.skill_content,
            source_conversation=conversation_id,
            allowed_tools=self._extract_tools_used(conv),
            when_to_use=self._infer_when_to_use(task_record),
            auto_generated=True,
        )

        # 4. 写入 data/skills/auto/<name>.md(隔离目录)
        dest = Path("data/skills/auto") / f"{result.skill_name}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(enhanced_content, "utf-8")

        # 5. 通知前端弹窗"新技能已沉淀,是否采纳"
        await self._broadcast("skill.auto.generated", {
            "skill_name": result.skill_name,
            "path": str(dest),
            "preview": enhanced_content[:500],
            "needs_review": True,
        })
        return {"distilled": True, "skill_name": result.skill_name, "needs_review": True}

    async def promote_auto_skill(self, skill_name: str) -> dict:
        """用户确认采纳:从 auto/ 提升到 custom/"""
        src = Path("data/skills/auto") / f"{skill_name}.md"
        dest = Path("data/skills/custom") / f"{skill_name}.md"
        shutil.move(str(src), str(dest))
        # 清理 needs_review 标记
        return {"promoted": True, "path": str(dest)}
```

**与 distiller.py 的差异**:

| 维度 | `distiller.py`(现有) | `AutoSkillGenerator`(扩展) |
|---|---|---|
| 触发阈值 | 3 次连续同类成功 | 单次高质量成功 |
| 触发时机 | 显式 `check_and_distill` 调用 | 任务完成事件钩子 |
| 写入目录 | `data/skills/`(直接生效) | `data/skills/auto/`(待审核) |
| 用户介入 | 二次确认后写入 | 先写入再通知,可采纳/丢弃 |
| frontmatter | 最小字段 | Pangu 扩展字段齐全 |

### 4.5 Dream 机制(借鉴 OpenClaw,空闲整理)

#### 设计:Pangu Dream 守护进程

```python
class DreamScheduler:
    """空闲时整理技能库,借用 OS cron / 应用内调度器"""

    IDLE_THRESHOLD = 30 * 60   # 30 分钟无活动触发
    SCHEDULE = "0 3 * * *"     # 每日凌晨 3 点深度整理

    async def run_idle_dream(self):
        """轻量 Dream:空闲时整理"""
        tasks = [
            self._deduplicate_skills(),         # 去重相似技能
            self._update_tags_consistency(),    # 标签一致性检查
            self._check_stale_registry_skills(),# registry 更新检查
            self._archive_unused_skills(),      # 归档 30 天未使用技能
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def run_deep_dream(self):
        """深度 Dream:每日凌晨,LLM 辅助"""
        # 1. 扫描所有 auto/ 待审技能,LLM 评估质量
        auto_skills = list(Path("data/skills/auto").glob("*.md"))
        for skill_file in auto_skills:
            assessment = await self._llm_assess_quality(skill_file)
            if assessment["score"] >= 0.8:
                await self._auto_promote(skill_file)
            elif assessment["score"] < 0.3:
                await self._archive_low_quality(skill_file)
        # 2. 跨技能知识图谱构建(技能间引用关系)
        await self._build_skill_graph()
        # 3. 生成"技能健康报告"
        report = await self._generate_health_report()
        await self._notify_user(report)

    async def _deduplicate_skills(self):
        """检测重复/相似技能,提示合并"""
        skills = await SkillLoader().scan_all()
        clusters = await self._cluster_by_embedding(skills)   # 向量聚类
        for cluster in clusters:
            if len(cluster) > 1 and cluster["similarity"] > 0.92:
                await self._broadcast("skill.duplicate.detected", {
                    "skills": cluster["names"],
                    "suggestion": "merge"
                })
```

**Dream 触发条件**:
- 空闲 Dream: 30 分钟无对话活动 + 应用在前台
- 深度 Dream: 每日凌晨 3:00(若应用开启)
- 手动触发: `/skill dream` 命令

---

## 5. 前端 UI 设计

### 5.1 SkillMarketplace.tsx 改造

现有 `SkillMarketplace.tsx` 已有卡片网格 + toggle,但 toggle 调用失败(后端不接 enabled)。改造分四块:

#### 5.1.1 顶部 Tab 切换:市场浏览 vs 已安装

```tsx
// 伪代码:Tab 结构
type Tab = 'market' | 'installed' | 'profiles' | 'auto'

<div className="tabs">
  <Tab active={tab==='market'} onClick={()=>setTab('market')}>🌐 市场浏览</Tab>
  <Tab active={tab==='installed'} onClick={()=>setTab('installed')}>📦 已安装 ({installedCount})</Tab>
  <Tab active={tab==='auto'} onClick={()=>setTab('auto')}>🤖 自动沉淀 ({autoCount}) {autoCount>0 && <Badge>待审</Badge>}</Tab>
  <Tab active={tab==='profiles'} onClick={()=>setTab('profiles')}>⚙️ Profiles</Tab>
</div>
```

#### 5.1.2 市场浏览 Tab

```
┌──────────────────────────────────────────────────────────┐
│ [🔍 搜索技能...] [来源▼] [分类▼] [标签▼] [🔄 同步]      │
│ ──────────────────────────────────────────────────────── │
│ 来源: 🟢 official  🟡 verified  🔵 community  ⚪ unknown │
│                                                          │
│ ┌────────────────┐ ┌────────────────┐ ┌────────────────┐│
│ │ 💬 code-review │ │ 🐍 test-gen    │ │ 📊 data-analysis││
│ │ 代码三维度评审 │ │ 自动测试生成  │ │ 数据分析助手  ││
│ │ v1.2.0         │ │ v2.0.1        │ │ v0.9.5        ││
│ │ 🟢 official    │ │ 🟡 verified   │ │ 🔵 community  ││
│ │ ⭐4.8 12k 安装 │ │ ⭐4.6 8k 安装 │ │ ⭐4.2 1k 安装 ││
│ │ #code #security│ │ #test #python │ │ #data #pandas ││
│ │ [详情][安装]   │ │ [详情][安装]  │ │ [详情][安装]  ││
│ └────────────────┘ └────────────────┘ └────────────────┘│
└──────────────────────────────────────────────────────────┘
```

#### 5.1.3 已安装 Tab(增强现有卡片)

在现有卡片(`SkillMarketplace.tsx:316-481`)基础上**增量**新增字段:
- 来源徽章(builtin/custom/registry/auto + 可信度色块)
- 版本号 `v1.2.0`
- 更新提示(若有新版本,显示 ↑ 箭头 + 最新版本号)
- scope 标签(👤 user / 📁 project / 💻 local)
- enabled toggle **真正可用**(后端 §1.3 支撑后)

#### 5.1.4 自动沉淀 Tab(新增)

```
┌──────────────────────────────────────────────────────────┐
│ 🤖 自动沉淀技能 (待审核)                                │
│ ──────────────────────────────────────────────────────── │
│ ℹ️ 这些技能由 AI 从你的对话中自动生成,确认后才会启用。│
│                                                          │
│ ┌──────────────────────────────────────────────────────┐│
│ │ refactor-extractor (生成于 2026-07-17)               ││
│ │ 从对话"重构用户认证模块"中提取                       ││
│ │ 预览: ---\nname: refactor-extractor\n...            ││
│ │ 工具: [Read] [Grep] [mcp:git/diff]                   ││
│ │ [👁 查看完整内容] [✅ 采纳] [🗑 丢弃] [✏ 编辑后采纳]││
│ └──────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

#### 5.1.5 Profiles 面板(新增)

```
┌──────────────────────────────────────────────────────────┐
│ ⚙️ Skill Profiles                                        │
│ ──────────────────────────────────────────────────────── │
│ 当前激活: 🟢 developer                                  │
│                                                          │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐         │
│ │ developer   │ │ writer      │ │ minimal     │         │
│ │ 3 技能      │ │ 3 技能      │ │ 0 技能      │         │
│ │ [切换] [编辑]│ │ [切换] [编辑]│ │ [切换] [编辑]│         │
│ └─────────────┘ └─────────────┘ └─────────────┘         │
│                                                          │
│ [+ 保存当前为 profile]                                   │
└──────────────────────────────────────────────────────────┘
```

### 5.2 Settings.tsx MCP 分类重构

现有 `Settings.tsx:1020-1049` 是单弹窗手动表单。重构为分类标签页:

#### 5.2.1 主布局重构

```tsx
// Settings.tsx MCP 区域改为:
<div className="mcp-section">
  <h3>🔌 MCP 服务器</h3>
  <Tabs>
    <Tab label={`🌐 市场 (${directoryCount})`} />
    <Tab label={`📦 已安装 (${installedCount})`} />
    <Tab label="⚙️ 高级(手动添加)" />  {/* 折叠原表单到这里 */}
  </Tabs>

  {/* 市场 Tab */}
  <McpMarketGrid
    directory={directory}
    onInstall={handleInstall}
    safetyFilter={safetyFilter}
  />

  {/* 已安装 Tab */}
  <McpInstalledList
    servers={installedServers}
    healthStatus={healthStatus}
    onToggle={handleToggle}
    onConfigure={handleConfigure}
    onUninstall={handleUninstall}
    onRestart={handleRestart}
  />

  {/* 高级 Tab:保留原手动表单(transport 选择增强) */}
  <details>
    <summary>手动添加 MCP 服务器(高级)</summary>
    <McpManualForm transport={["stdio", "sse", "http"]} />
  </details>
</div>
```

#### 5.2.2 transport 选择增强

现有 `Settings.tsx:1033-1036` 只有 stdio/sse 两选项且后端忽略。改为三选项 + 动态字段:

```tsx
<select value={form.transport}>
  <option value="stdio">stdio(本地进程)</option>
  <option value="sse">sse(Server-Sent Events)</option>
  <option value="http">http(Streamable HTTP)</option>
</select>

{form.transport === 'stdio' && (
  <>
    <input placeholder="命令,如 npx" {...bind('command')} />
    <input placeholder="参数,逗号分隔" {...bind('args')} />
    <input placeholder="环境变量 JSON" {...bind('env')} />
  </>
)}
{form.transport === 'sse' && (
  <input placeholder="SSE 端点 URL,如 https://mcp.example.com/sse" {...bind('url')} />
)}
{form.transport === 'http' && (
  <>
    <input placeholder="HTTP 端点 URL" {...bind('url')} />
    <input placeholder="认证头 JSON,如 {'Authorization':'Bearer xxx'}" {...bind('headers')} />
  </>
)}
```

#### 5.2.3 MCP 市场卡片网格组件

```tsx
interface McpCardProps {
  name: string
  description: string
  transport: 'stdio' | 'sse' | 'http'
  rating: number
  installs: number
  safetyLevel: 'official' | 'verified' | 'community' | 'unknown'
  category: string
  installed: boolean
  healthStatus?: 'healthy' | 'degraded' | 'offline' | 'starting'
  onInstall: () => void
  onConfigure: () => void
}

// 卡片视觉:
// - 左上角图标(根据 category 自动选择 📁🐙🌐📊)
// - 右上角可信度徽章(🟢🟡🔵⚪)
// - 健康状态点(仅已安装显示)
// - 底部按钮:已安装显示 [配置][卸载];未安装显示 [详情][安装]
```

#### 5.2.4 已安装 MCP 列表组件

```tsx
// 替代当前简单的 list_servers 显示
{installedServers.map(s => (
  <div className="mcp-server-row">
    <span className="health-dot" data-status={healthStatus[s.name]} />  {/* 🟢🟡🔴 */}
    <span className="name">{s.name}</span>
    <span className="transport-badge">{s.transport}</span>
    <span className="scope-badge">{s.scope}</span>  {/* 👤📁💻 */}
    <span className="tools-count">{s.tools?.length || 0} 工具</span>
    <div className="actions">
      <Toggle checked={s.enabled} onChange={()=>toggleMcp(s.name)} />
      <button onClick={()=>configureMcp(s.name)}>⚙️</button>
      <button onClick={()=>restartMcp(s.name)}>🔄</button>
      <button onClick={()=>showLogs(s.name)}>📋</button>
      <button onClick={()=>uninstallMcp(s.name)}>🗑️</button>
    </div>
  </div>
))}
```

---

## 6. 数据模型与文件清单

### 6.1 数据模型决策

#### 6.1.1 `skills` 表(已存在,启用)

**决策**: 复用现有 `orm.py:87-96` 的 `Skill` 表作为**运行时缓存**,不作为权威源。权威源是 markdown 文件 + 状态文件。

**理由**: 已有表存在且 `idx_skills_enabled` 索引已建;改用文件持久化会浪费现有基础设施;CRDT 跨设备同步需要 DB 表载体。

**字段扩展**:

```python
class Skill(Base):  # 扩展自 orm.py:87
    __tablename__ = "skills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="builtin")  # builtin/custom/auto/registry/extension
    path: Mapped[str | None] = mapped_column(String(512))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 新增字段
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    scope: Mapped[str] = mapped_column(String(16), default="user")
    priority: Mapped[int] = mapped_column(Integer, default=50)
    source_type: Mapped[str | None] = mapped_column(String(32))  # github/url/npm/pip/...
    source_ref: Mapped[str | None] = mapped_column(String(255))
    checksum: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[str | None] = mapped_column(String(64))
    tags: Mapped[list | None] = mapped_column(JSON)
    permissions: Mapped[dict | None] = mapped_column(JSON)
    allowed_tools: Mapped[list | None] = mapped_column(JSON)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
```

#### 6.1.2 `mcp_installations` 表(新增)

**决策**: 新增。理由:MCP 安装元数据需要持久化(transport/scope/permissions/source),状态文件不足以承载复杂查询与审计。

```python
class McpInstallation(Base):
    """MCP 服务器安装记录(权威源,与状态文件双写)"""
    __tablename__ = "mcp_installations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    transport: Mapped[str] = mapped_column(String(16))              # stdio/sse/http
    command: Mapped[str | None] = mapped_column(String(512))
    args: Mapped[list | None] = mapped_column(JSON)
    env: Mapped[dict | None] = mapped_column(JSON)
    url: Mapped[str | None] = mapped_column(String(512))
    headers: Mapped[dict | None] = mapped_column(JSON)
    scope: Mapped[str] = mapped_column(String(16), default="user")
    safety_level: Mapped[str] = mapped_column(String(16), default="unknown")
    source: Mapped[str] = mapped_column(String(32))                  # smithery/pangu-official/manual/github
    source_ref: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_start: Mapped[bool] = mapped_column(Boolean, default=True)
    permissions: Mapped[dict | None] = mapped_column(JSON)
    health_status: Mapped[str] = mapped_column(String(16), default="unknown")  # healthy/degraded/offline
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime)
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

#### 6.1.3 `skill_profiles` 表(新增)

**决策**: 新增。理由:profile 是结构化数据,需支持跨设备同步与查询;文件方式不足以承载。

```python
class SkillProfile(Base):
    """技能 profile(保存的技能启用集)"""
    __tablename__ = "skill_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(255))
    enabled_skills: Mapped[list] = mapped_column(JSON)    # ["code-reviewer", ...]
    disabled_skills: Mapped[list] = mapped_column(JSON)
    scope: Mapped[str] = mapped_column(String(16), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

#### 6.1.4 `persona_skills` 与 `persona_mcp_servers` 表(新增)

见 §4.1 与 §4.3,均为关联表。

#### 6.1.5 状态文件清单(不入 DB)

| 文件路径 | 用途 | 是否入 git |
|---|---|---|
| `~/.pangu-nebula/skills-state.json` | 用户级技能 enabled 状态 | ❌ |
| `./.pangu/skills-state.json` | 项目级技能 enabled 状态 | ✅(项目内) |
| `~/.pangu-nebula/skills-state.local.json` | 本机临时技能状态 | ❌ |
| `~/.pangu-nebula/skill-profiles.json` | profile 定义(可选,亦可走 DB) | ❌ |
| `~/.pangu-nebula/mcp-servers.json` | 用户级 MCP 配置 | ❌ |
| `./.pangu/mcp-servers.json` | 项目级 MCP 配置 | ✅ |
| `~/.pangu-nebula/mcp-servers.local.json` | 本机临时 MCP 配置 | ❌ |
| `data/skills/registry/.installed.json` | registry 技能安装元数据 | ❌ |
| `data/registry-cache/` | registry 索引缓存 | ❌ |

### 6.2 新增/修改文件清单

#### 新增文件(15 个)

| 路径 | 改动摘要 |
|---|---|
| `server/services/registry_client.py` | CommunityRegistryClient 实现(§2.2),替代 skill_market.py 内存 mock |
| `server/services/skill_installers.py` | 6 种 source installer(GithubInstaller / UrlInstaller / NpmInstaller / PipInstaller / RelativeInstaller / GitSubdirInstaller) |
| `server/services/mcp_directory.py` | McpDirectory + SmitheryClient(§3.3),双源目录聚合 |
| `server/services/mcp_health.py` | McpHealthMonitor(§3.5),定时 ping + 状态广播 |
| `server/services/mcp_audit.py` | McpAuditLogger(§3.7),复用 audit_logs 表 |
| `server/services/skill_state.py` | 三层状态文件读写与合并(§1.3),_resolve_enabled 实现 |
| `server/services/skill_profiles.py` | SkillProfileManager(§1.5),profile CRUD + 切换 |
| `server/services/skill_tool_resolver.py` | SkillToolResolver(§4.2),allowed-tools 解析与 MCP 工具绑定 |
| `server/services/auto_skill_generator.py` | AutoSkillGenerator(§4.4),扩展自 distiller.py |
| `server/services/dream_scheduler.py` | DreamScheduler(§4.5),空闲整理 + 深度 Dream |
| `server/api/skill_market_v2.py` | 新版市场 API:`/skill-market/sync`、`/skill-market/install/{name}`、`/skill-market/updates`,替代 skill_market.py |
| `server/api/mcp_directory.py` | MCP 目录 API:`/mcp/directory/list`、`/mcp/directory/install/{name}` |
| `server/cli/skills_cli.py` | `/skill` CLI 命令实现(§1.4) |
| `server/cli/mcp_cli.py` | `/mcp` CLI 命令实现(§3.5) |
| `frontend/src/components/McpMarketGrid.tsx` | MCP 市场卡片网格组件(§5.2.3) |
| `frontend/src/components/McpInstalledList.tsx` | 已安装 MCP 列表组件(§5.2.4) |
| `frontend/src/components/SkillProfiles.tsx` | Skill profile 管理面板(§5.1.5) |
| `frontend/src/components/SkillAutoReview.tsx` | 自动沉淀技能审核面板(§5.1.4) |

#### 修改文件(10 个)

| 路径 | 改动摘要 |
|---|---|
| `server/services/skill_loader.py` | Skill dataclass 扩展字段(version/scope/priority/allowed_tools/permissions/source_type);`_MarkdownSource._parse` 增强;新增 `RegistrySource`/`AutoSource`;`update_skill` 接受 `enabled` 参数;`scan_all` 加载三层状态文件合并 |
| `server/services/skill_engine.py` | `PromptSkillEngine.execute_skill` 增加 enabled 检查;集成 SkillToolResolver |
| `server/services/mcp_client.py` | `connect_server` 分支处理 stdio/sse/http;`_ServerConnection` 扩展 transport/url/client 字段;`call_tool` 注入审计 hook |
| `server/services/marketplace.py` | `parse_frontmatter` 升级为支持列表/嵌套的轻量 YAML 子集;`export_skill` 输出完整 Pangu 扩展 frontmatter |
| `server/api/models.py` | `SkillUpdate` 新增 `enabled: bool \| None` 字段;新增 `PersonaSkillBindRequest`/`PersonaSkillProfileRequest` |
| `server/api/models_mcp.py` | `McpConnectRequest` 新增 `transport`/`url`/`headers`/`scope`/`safety_level`/`auto_start`/`permissions` 字段;新增 `McpInstallRequest` |
| `server/api/skills.py` | `update_skill` 端点传递 `enabled`;`execute_skill` 端点检查 enabled;新增 `/skills/{name}/enable` `/skills/{name}/disable` 端点 |
| `server/api/mcp.py` | `connect_server` 端点传递 transport;新增 `/mcp/directory/*` 路由挂载;新增 `/mcp/servers/{name}/restart` `/mcp/servers/{name}/health` 端点 |
| `server/db/orm.py` | `Skill` 表字段扩展(version/scope/priority/source_type/source_ref/checksum/category/tags/permissions/allowed_tools/needs_review/installed_at);新增 `McpInstallation`/`SkillProfile`/`PersonaSkill`/`PersonaMcpServer` 4 个表 |
| `server/db/indexes.sql` | 新增 `idx_mcp_installations_scope`、`idx_skill_profiles_active`、`idx_persona_skills_persona_id` 等索引 |
| `frontend/src/components/SkillMarketplace.tsx` | 顶部 Tab(市场/已安装/自动/Profiles);来源徽章;版本号;scope 标签;更新提示;enabled toggle 真正可用 |
| `frontend/src/components/Settings.tsx` | MCP 区域重构为三 Tab(市场/已安装/高级);transport 选择增强(stdio/sse/http + 动态字段);保留手动表单为高级入口 |
| `frontend/src/lib/types.ts` | `Skill` interface 扩展;新增 `McpInstallation`/`SkillProfile`/`McpDirectoryEntry` 类型 |

#### 废弃/降级文件(1 个)

| 路径 | 处理方式 |
|---|---|
| `server/api/skill_market.py` | 保留但标记 `@deprecated`,功能由 `skill_market_v2.py` 替代;P2P 内存 mock 逻辑保留(供 T5.5 gift 协议测试) |

---

## 附录 A: 实施阶段建议

考虑工程可行性,建议分四阶段渐进交付(每阶段可独立验证):

| 阶段 | 范围 | 关键交付 | 预估工作量 |
|---|---|---|---|
| **P1: enabled 闭环** | §1.3 + §1.4 + `SkillUpdate.enabled` + `execute_skill` 检查 | toggle 真正可用;CLI enable/disable | 小 |
| **P2: MCP transport 修复** | §3.1 + §3.2 + §5.2.2 | 三 transport 后端分支 + 前端动态字段 | 中 |
| **P3: 社区联结 + 市场 UI** | §2.1-2.5 + §5.1.1-5.1.3 | RegistrySource + 6 种 installer + 市场浏览 | 大 |
| **P4: 联动 + 自动化** | §4 + §5.1.4-5.1.5 + §3.3-3.7 | Persona 绑定 + 自动沉淀 + Dream + MCP 市场 + 健康监控 | 大 |

P1 是最小可交付闭环,直接修复 D1 的 enabled 链路;P2 修复 D2 的 transport bug;P3/P4 是市场化能力建设。

## 附录 B: 风险与缓解

| 风险 | 缓解 |
|---|---|
| 三层状态文件合并复杂导致 enabled 不一致 | `_resolve_enabled` 单一入口 + 单元测试覆盖所有组合;UI 显示"有效状态 + 来源层级"便于排查 |
| MCP HTTP/SSE transport 实现复杂(httpx 长连接管理) | 先 stdio 完整可用,P2 仅交付 transport 字段透传 + http 基础握手,sse 后置 |
| Smithery API 限流或下线 | 目录双源(official + smithery),官方源兜底;缓存 1 小时 |
| 自动沉淀产生大量低质量技能污染目录 | 强制 `data/skills/auto/` 隔离 + `needs_review` 标记 + Dream 定期清理 |
| frontmatter 解析器不兼容标准 YAML | 保持现有简易解析器为主,仅扩展列表/JSON 内联;复杂 YAML 后续按需引入 `pyyaml`(已是常见依赖) |
| MCP 工具调用审计日志量爆炸 | audit_logs 已有清理机制(Phase 6D);MCP 调用默认仅记录 metadata,arguments 截断到 500 字符 |

---

**文档结束**。本设计已基于实际代码诊断校验,所有引用的文件路径与行号均经核实,所有扩展点保持向后兼容。
