"""P2P 技能市场 API (Phase 5 v2.0.0 T5.4)

非中心化的 P2P 技能市场:
- 任何实例都可以发布技能到本地市场
- 通过 E2EE 同步通道与其他实例共享市场索引
- 评分机制记录用户对技能的反馈

注意: 此路由不注册到 server/main.py(由 T5.8 集成测试或独立场景启用),
通过直接导入 `from server.api.skill_market import router` 使用。

端点总览:
- GET  /skill-market                 模块信息
- POST /skill-market/publish         发布技能到市场
- GET  /skill-market/search          搜索技能
- POST /skill-market/install         安装技能(从市场拉取并安装)
- POST /skill-market/rate            为技能评分
- GET  /skill-market/ratings/{name}  查看技能评分
- GET  /skill-market/list            列出所有已发布技能

实现说明:
- 市场数据存储在内存 dict 中(进程级单例)
- 评分按 skill_name 维度聚合,记录 {rater, score, comment, ts}
- 不实际联网,跨实例同步通过 T5.5 的 gift 协议在 E2EE 通道上完成
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.community_registry import get_community_registry
from ..services.skill_package import SkillManifest, SkillPackager, SkillInstaller
# v2.3.1 P0-7: 技能持久化与共享 loader 单例抽取到 skill_persistence
# (此前 skills.py / skill_market.py 各自实例化 _loader, 导致内存缓存不一致)
from ..services.skill_persistence import (
    loader as _loader,
    load_enabled_map,
    persist_skill_enabled,
    publish_skill_toggled,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/skill-market", tags=["skill-market"])


# ===== 内存市场存储(进程级单例) =====
#
# _MARKET: skill_name -> {manifest, published_at, publisher, ratings: []}
# _PUBLISHED_DATA: skill_name -> bytes (打包后的 .skill 内容,用于安装)

_MARKET: dict[str, dict] = {}
_PUBLISHED_DATA: dict[str, bytes] = {}


# ===== Phase 3-C: 内置/社区技能市场端点 =====
# v2.3.1 P0-7: 三个持久化函数已抽取到 skill_persistence, 此处保留向后兼容别名
# (source 参数维持原差异: builtin / skill_market_api)


async def _load_enabled_map() -> dict[str, bool]:
    """[P0-7 委托] 从 DB 读取 {name: enabled} 映射"""
    return await load_enabled_map()


async def _persist_skill_enabled(name: str, enabled: bool) -> None:
    """[P0-7 委托] 持久化 enabled (source=builtin, 与原实现一致)"""
    await persist_skill_enabled(name, enabled, source="builtin")


async def _publish_skill_toggled(name: str, enabled: bool) -> None:
    """[P0-7 委托] 发布 skill.enabled.toggled 事件 (source=skill_market_api)"""
    await publish_skill_toggled(name, enabled, source="skill_market_api")


class CommunityInstallRequest(BaseModel):
    """从社区安装技能请求"""

    skill_url: str = Field(..., description="技能资源 URL (git/pip/npm/registry)")
    install_type: str = Field(default="git", description="安装类型: git/pip/npm/registry")
    name: str | None = Field(default=None, description="可选: 自定义技能名")


class ToggleEnabledRequest(BaseModel):
    """切换技能 enabled 状态请求"""

    enabled: bool = Field(..., description="目标启用状态")


# ===== Pydantic 模型 =====


class PublishRequest(BaseModel):
    """发布技能到市场请求"""

    name: str = Field(..., description="技能名")
    version: str = Field(default="1.0.0", description="版本号")
    description: str = Field(default="", description="技能描述")
    author: str = Field(default="", description="作者")
    dependencies: list[str] = Field(default_factory=list, description="依赖列表")
    capabilities: list[str] = Field(default_factory=lambda: ["text"], description="能力标签")
    config: dict = Field(default_factory=dict, description="配置")
    entry_point: str = Field(default="main.handler", description="入口点")
    code: str = Field(default="", description="base64 编码的代码(可选)")
    publisher: str = Field(default="anonymous", description="发布者标识")


class SearchRequest(BaseModel):
    """搜索请求(可选,主走 GET 查询参数)"""

    query: str = Field(default="", description="搜索关键词")
    capability: str | None = Field(default=None, description="能力筛选")
    limit: int = Field(default=20, description="返回数量上限")


class InstallFromMarketRequest(BaseModel):
    """从市场安装技能请求"""

    name: str = Field(..., description="要安装的技能名")
    target_dir: str | None = Field(default=None, description="安装目录(可选)")


class RateRequest(BaseModel):
    """技能评分请求"""

    name: str = Field(..., description="技能名")
    score: float = Field(..., ge=0.0, le=5.0, description="评分 0-5")
    comment: str = Field(default="", description="评价内容")
    rater: str = Field(default="anonymous", description="评分者标识")


# ===== 内部辅助 =====


def _now_iso() -> str:
    """当前 UTC 时间 ISO 字符串"""
    return datetime.now(timezone.utc).isoformat()


def _manifest_to_summary(manifest: SkillManifest, entry: dict) -> dict:
    """将 manifest + 市场条目转换为搜索结果摘要"""
    ratings = entry.get("ratings", [])
    avg_score = (
        sum(r["score"] for r in ratings) / len(ratings) if ratings else 0.0
    )
    return {
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "author": manifest.author,
        "capabilities": manifest.capabilities,
        "dependencies": manifest.dependencies,
        "publisher": entry.get("publisher", "anonymous"),
        "published_at": entry.get("published_at"),
        "rating_count": len(ratings),
        "avg_score": round(avg_score, 2),
    }


# ===== 端点实现 =====


@router.get("", summary="技能市场模块信息")
async def market_info():
    """获取技能市场模块信息"""
    return {
        "ok": True,
        "data": {
            "module": "skill-market",
            "phase": "T5.4",
            "features": ["publish", "search", "install", "rate"],
            "decentralized": True,
            "skills_count": len(_MARKET),
            "note": "P2P 技能市场(内存 mock,跨实例同步走 T5.5 gift 协议)",
        },
        "error": None,
    }


@router.post("/publish", summary="发布技能到市场")
async def publish_skill(req: PublishRequest):
    """发布技能到本地市场

    - 验证 manifest
    - 打包为 .skill 格式
    - 存储到内存市场(_MARKET 与 _PUBLISHED_DATA)
    """
    # 构建 manifest 并验证
    manifest = SkillManifest(
        name=req.name,
        version=req.version,
        description=req.description,
        author=req.author,
        dependencies=req.dependencies,
        capabilities=req.capabilities,
        config=req.config,
        entry_point=req.entry_point,
        code=req.code,
    )
    valid, err = SkillPackager.validate(manifest)
    if not valid:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": f"validation failed: {err}"},
        )

    # 打包
    packed = SkillPackager.pack(manifest)

    # 存储到市场
    _MARKET[req.name] = {
        "manifest": manifest,
        "published_at": _now_iso(),
        "publisher": req.publisher,
        "ratings": [],
    }
    _PUBLISHED_DATA[req.name] = packed

    return {
        "ok": True,
        "data": {
            "name": req.name,
            "version": req.version,
            "published_at": _MARKET[req.name]["published_at"],
            "size": len(packed),
            "checksum": SkillPackager.calculate_checksum(packed),
        },
        "error": None,
    }


@router.get("/search", summary="搜索技能")
async def search_skills(
    q: str = Query(default="", description="搜索关键词(匹配名称/描述/作者)"),
    capability: str | None = Query(default=None, description="能力筛选"),
    limit: int = Query(default=20, ge=1, le=100, description="返回数量上限"),
):
    """搜索市场中的技能

    - 关键词匹配 name、description、author(子串匹配,不区分大小写)
    - capability 过滤(技能 capabilities 包含指定值)
    - 按 avg_score 降序排序
    """
    q_lower = q.lower()
    results = []
    for name, entry in _MARKET.items():
        manifest: SkillManifest = entry["manifest"]
        # 关键词匹配
        if q_lower:
            text = f"{manifest.name} {manifest.description} {manifest.author}".lower()
            if q_lower not in text:
                continue
        # 能力过滤
        if capability and capability not in manifest.capabilities:
            continue
        results.append(_manifest_to_summary(manifest, entry))

    # 按平均分降序,其次按名称升序
    results.sort(key=lambda r: (-r["avg_score"], r["name"]))
    results = results[:limit]

    return {
        "ok": True,
        "data": {
            "query": q,
            "capability": capability,
            "count": len(results),
            "skills": results,
        },
        "error": None,
    }


@router.post("/install", summary="从市场安装技能")
async def install_from_market(req: InstallFromMarketRequest):
    """从本地市场安装技能到本地技能目录

    - 从 _PUBLISHED_DATA 取出打包好的 .skill 内容
    - 调用 SkillInstaller.install 安装
    """
    if req.name not in _PUBLISHED_DATA:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"skill not in market: {req.name}"},
        )

    packed = _PUBLISHED_DATA[req.name]
    installer = SkillInstaller() if not req.target_dir else SkillInstaller(skills_dir=req.target_dir)
    result = await installer.install(packed)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/rate", summary="为技能评分")
async def rate_skill(req: RateRequest):
    """为已发布的技能评分

    - 技能必须已发布到市场
    - 同一 rater 对同一技能的多次评分会追加(不去重)
    - 评分聚合在 _MARKET[name]["ratings"] 中
    """
    if req.name not in _MARKET:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"skill not in market: {req.name}"},
        )

    rating_entry = {
        "rater": req.rater,
        "score": req.score,
        "comment": req.comment,
        "ts": _now_iso(),
        "rating_id": uuid.uuid4().hex[:12],
    }
    _MARKET[req.name]["ratings"].append(rating_entry)

    ratings = _MARKET[req.name]["ratings"]
    avg = sum(r["score"] for r in ratings) / len(ratings)

    return {
        "ok": True,
        "data": {
            "name": req.name,
            "rating_id": rating_entry["rating_id"],
            "score": req.score,
            "avg_score": round(avg, 2),
            "rating_count": len(ratings),
        },
        "error": None,
    }


@router.get("/ratings/{name}", summary="查看技能评分")
async def get_ratings(name: str):
    """查看指定技能的所有评分"""
    if name not in _MARKET:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"skill not in market: {name}"},
        )
    ratings = _MARKET[name]["ratings"]
    avg = sum(r["score"] for r in ratings) / len(ratings) if ratings else 0.0
    return {
        "ok": True,
        "data": {
            "name": name,
            "ratings": ratings,
            "rating_count": len(ratings),
            "avg_score": round(avg, 2),
        },
        "error": None,
    }


@router.get("/list", summary="列出所有已发布技能")
async def list_market_skills():
    """列出市场中的所有技能(简略信息)"""
    items = []
    for name, entry in _MARKET.items():
        items.append(_manifest_to_summary(entry["manifest"], entry))
    items.sort(key=lambda r: r["name"])
    return {
        "ok": True,
        "data": {"count": len(items), "skills": items},
        "error": None,
    }


# ===== Phase 3-C: 内置/社区技能市场端点 =====
#
# 端点总览:
# - GET  /skill-market/builtin              列出内置技能 + enabled 状态
# - PUT  /skill-market/builtin/{name}/toggle 切换内置技能 enabled (持久化 + 发布事件)
# - GET  /skill-market/community/search     搜索社区技能 (调 community_registry)
# - POST /skill-market/community/install    安装社区技能
# - GET  /skill-market/sources              列出支持的社区源


@router.get("/builtin", summary="列出内置技能", description="列出所有内置技能及其 enabled 状态")
async def list_builtin_skills():
    """列出内置技能 + enabled 状态 (合并 DB 权威值)"""
    all_skills = await _loader.scan_all()
    builtin = [s for s in all_skills if s.source == "builtin"]
    enabled_map = await _load_enabled_map()
    items = []
    for s in builtin:
        item = {
            "name": s.name,
            "description": s.description,
            "source": s.source,
            "path": s.path,
            "tags": s.tags,
            "enabled": enabled_map.get(s.name, True),  # DB 权威, 默认启用
        }
        items.append(item)
    return {"ok": True, "data": {"count": len(items), "skills": items}, "error": None}


@router.put("/builtin/{name}/toggle", summary="切换内置技能 enabled", description="切换内置技能启用状态并持久化到 DB + 发布事件")
async def toggle_builtin_skill(name: str, req: ToggleEnabledRequest):
    """切换内置技能 enabled 状态 (持久化 + 发布 skill.enabled.toggled 事件)"""
    # 验证技能存在
    skill = await _loader.load_skill(name)
    if not skill:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"Skill not found: {name}"},
        )
    await _persist_skill_enabled(name, req.enabled)
    await _publish_skill_toggled(name, req.enabled)
    return {
        "ok": True,
        "data": {"name": name, "enabled": req.enabled},
        "error": None,
    }


@router.get("/community/search", summary="搜索社区技能", description="搜索社区注册表中的技能 (agentskills.io / Claude marketplace / Smithery)")
async def search_community_skills(
    q: str = Query(default="", description="搜索关键词"),
    source: str = Query(default="all", description="指定社区源: all/agentskills/claude/smithery"),
    limit: int = Query(default=20, ge=1, le=100, description="返回数量上限"),
):
    """搜索社区技能 (调 community_registry)"""
    client = get_community_registry()
    results = await client.search(query=q, source=source, limit=limit)
    return {
        "ok": True,
        "data": {"query": q, "source": source, "count": len(results), "skills": results},
        "error": None,
    }


@router.post("/community/install", summary="安装社区技能", description="从社区注册表安装技能 (git/pip/npm/registry)")
async def install_community_skill(req: CommunityInstallRequest):
    """安装社区技能 (调 community_registry)"""
    client = get_community_registry()
    result = await client.install(skill_url=req.skill_url, install_type=req.install_type)
    if not result.get("success", False):
        # 占位实现返回 success=False, 但不抛 HTTPException (前端可显示提示)
        return {"ok": False, "data": result, "error": result.get("error")}
    return {"ok": True, "data": result, "error": None}


@router.get("/sources", summary="列出社区源", description="列出支持的社区注册表源")
async def list_community_sources():
    """列出支持的社区源"""
    client = get_community_registry()
    sources = client.list_sources()
    return {"ok": True, "data": {"count": len(sources), "sources": sources}, "error": None}


# ===== 测试辅助(仅用于重置市场状态,不暴露给生产) =====


def _reset_market_for_testing() -> None:
    """重置市场内存数据(仅用于单元测试隔离)"""
    _MARKET.clear()
    _PUBLISHED_DATA.clear()


def _get_market_state_for_testing() -> tuple[dict, dict]:
    """获取市场内存状态(仅用于测试断言)"""
    return _MARKET, _PUBLISHED_DATA
