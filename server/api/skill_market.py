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

import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.skill_package import SkillManifest, SkillPackager, SkillInstaller


router = APIRouter(prefix="/skill-market", tags=["skill-market"])


# ===== 内存市场存储(进程级单例) =====
#
# _MARKET: skill_name -> {manifest, published_at, publisher, ratings: []}
# _PUBLISHED_DATA: skill_name -> bytes (打包后的 .skill 内容,用于安装)

_MARKET: dict[str, dict] = {}
_PUBLISHED_DATA: dict[str, bytes] = {}


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


# ===== 测试辅助(仅用于重置市场状态,不暴露给生产) =====


def _reset_market_for_testing() -> None:
    """重置市场内存数据(仅用于单元测试隔离)"""
    _MARKET.clear()
    _PUBLISHED_DATA.clear()


def _get_market_state_for_testing() -> tuple[dict, dict]:
    """获取市场内存状态(仅用于测试断言)"""
    return _MARKET, _PUBLISHED_DATA
