"""知识库安全写回服务层 (T2.5 + T2.9)。

提供 Wiki 内容变更审核、diff 生成、合并/丢弃及 URL 快照(含 SSRF 防护)。
所有外部抓取为 mock 实现。
"""

import difflib
import ipaddress
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.wiki_review_models import WikiReviewItem, URLSnapshot


# 允许访问的作用域白名单 (agent_id -> set of scopes)
_SCOPE_WHITELIST: dict[str, set[str]] = {}


def _review_item_to_dict(r: WikiReviewItem) -> dict:
    return {
        "id": r.id,
        "wiki_id": r.wiki_id,
        "title": r.title,
        "proposed_content": r.proposed_content,
        "current_content": r.current_content,
        "status": r.status,
        "scope": r.scope,
        "proposed_by": r.proposed_by,
        "review_note": r.review_note,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
    }


def _snapshot_to_dict(s: URLSnapshot) -> dict:
    return {
        "id": s.id,
        "url": s.url,
        "snapshot_content": s.snapshot_content,
        "snapshot_at": s.snapshot_at.isoformat() if s.snapshot_at else None,
        "content_type": s.content_type,
        "status": s.status,
    }


def _is_ssrf_blocked(url: str) -> bool:
    """SSRF 防护:检查 URL 是否指向内网/保留地址

    拒绝: 127.0.0.1, localhost, 10.*, 192.168.*, 172.16-31.*, 169.254.*
    """
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return True
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return True
    # localhost 直接拒绝
    if hostname in ("localhost",):
        return True
    # 尝试作为 IP 地址解析
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        # 非 IP 字面量(域名),不做 DNS 解析(避免测试环境网络依赖)
        return False
    # IPv4 内网/保留地址检测
    if isinstance(ip, ipaddress.IPv4Address):
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            return True
    # IPv6 内网/保留地址检测
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            return True
        # IPv4-mapped IPv6
        if ip.ipv4_mapped is not None:
            v4 = ip.ipv4_mapped
            if v4.is_private or v4.is_loopback or v4.is_link_local or v4.is_reserved or v4.is_unspecified:
                return True
    return False


class WikiReviewService:
    """知识库安全写回服务"""

    async def submit_for_review(
        self,
        session: AsyncSession,
        wiki_id: int,
        title: str,
        proposed_content: str,
        current_content: str | None = None,
        scope: str = "default",
    ) -> dict:
        item = WikiReviewItem(
            wiki_id=wiki_id,
            title=title,
            proposed_content=proposed_content,
            current_content=current_content,
            status="pending",
            scope=scope,
            proposed_by="agent",
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return _review_item_to_dict(item)

    async def list_pending(
        self, session: AsyncSession, scope: str | None = None
    ) -> list[dict]:
        stmt = select(WikiReviewItem).where(
            WikiReviewItem.status == "pending"
        ).order_by(WikiReviewItem.created_at.desc())
        if scope:
            stmt = stmt.where(WikiReviewItem.scope == scope)
        result = await session.execute(stmt)
        return [_review_item_to_dict(r) for r in result.scalars().all()]

    async def get_review_item(
        self, session: AsyncSession, item_id: int
    ) -> dict | None:
        item = await session.get(WikiReviewItem, item_id)
        return _review_item_to_dict(item) if item else None

    async def merge(
        self, session: AsyncSession, item_id: int, review_note: str = ""
    ) -> dict:
        item = await session.get(WikiReviewItem, item_id)
        if not item:
            return None
        item.status = "merged"
        item.review_note = review_note
        item.reviewed_at = datetime.utcnow()
        await session.commit()
        await session.refresh(item)
        return _review_item_to_dict(item)

    async def discard(
        self, session: AsyncSession, item_id: int, review_note: str = ""
    ) -> dict:
        item = await session.get(WikiReviewItem, item_id)
        if not item:
            return None
        item.status = "discarded"
        item.review_note = review_note
        item.reviewed_at = datetime.utcnow()
        await session.commit()
        await session.refresh(item)
        return _review_item_to_dict(item)

    async def get_diff(self, session: AsyncSession, item_id: int) -> dict:
        item = await session.get(WikiReviewItem, item_id)
        if not item:
            return None
        current_lines = (item.current_content or "").splitlines(keepends=True)
        proposed_lines = (item.proposed_content or "").splitlines(keepends=True)
        diff = list(
            difflib.unified_diff(
                current_lines,
                proposed_lines,
                fromfile=f"current (wiki_id={item.wiki_id})",
                tofile=f"proposed (review_id={item.id})",
            )
        )
        # 结构化 diff: 行级分类 (T2.6) - 便于前端高亮
        structured = self._build_structured_diff(current_lines, proposed_lines)
        return {
            "id": item.id,
            "wiki_id": item.wiki_id,
            "diff": "".join(diff),
            "has_changes": len(diff) > 0,
            "structured": structured,
            "stats": {
                "added": sum(1 for s in structured if s["type"] == "added"),
                "removed": sum(1 for s in structured if s["type"] == "removed"),
                "context": sum(1 for s in structured if s["type"] == "context"),
            },
        }

    @staticmethod
    def _build_structured_diff(
        old_lines: list[str], new_lines: list[str]
    ) -> list[dict]:
        """构建结构化 diff,每行标记类型: context / added / removed

        使用 difflib.SequenceMatcher 进行行级比对。
        注: 入参的行可能带换行符(keepends=True),内部统一去除换行符后再比对,
            避免"line B" 与 "line B\\n" 被误判为不同行。
        """
        # 去除每行的换行符后比对
        old_stripped = [l.rstrip("\n") for l in old_lines]
        new_stripped = [l.rstrip("\n") for l in new_lines]
        sm = difflib.SequenceMatcher(a=old_stripped, b=new_stripped, autojunk=False)
        result: list[dict] = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    result.append({
                        "type": "context",
                        "old_line_no": i1 + k + 1,
                        "new_line_no": j1 + k + 1,
                        "content": old_stripped[i1 + k],
                    })
            elif tag == "replace":
                # 修改: 先输出删除行, 再输出新增行
                for k in range(i2 - i1):
                    result.append({
                        "type": "removed",
                        "old_line_no": i1 + k + 1,
                        "new_line_no": None,
                        "content": old_stripped[i1 + k],
                    })
                for k in range(j2 - j1):
                    result.append({
                        "type": "added",
                        "old_line_no": None,
                        "new_line_no": j1 + k + 1,
                        "content": new_stripped[j1 + k],
                    })
            elif tag == "delete":
                for k in range(i2 - i1):
                    result.append({
                        "type": "removed",
                        "old_line_no": i1 + k + 1,
                        "new_line_no": None,
                        "content": old_stripped[i1 + k],
                    })
            elif tag == "insert":
                for k in range(j2 - j1):
                    result.append({
                        "type": "added",
                        "old_line_no": None,
                        "new_line_no": j1 + k + 1,
                        "content": new_stripped[j1 + k],
                    })
        return result

    async def check_scope(self, agent_id: str, scope: str) -> bool:
        """作用域校验:检查 agent 是否有权操作该 scope

        默认允许(未配置白名单时);配置了白名单则检查。
        """
        if not _SCOPE_WHITELIST:
            return True
        allowed = _SCOPE_WHITELIST.get(agent_id, set())
        return scope in allowed or "*" in allowed

    async def snapshot_url(self, session: AsyncSession, url: str) -> dict:
        """URL 快照:含 SSRF 防护检查

        - SSRF 防护:拒绝内网/保留地址
        - 实际抓取为 mock:返回占位内容
        """
        if _is_ssrf_blocked(url):
            snapshot = URLSnapshot(
                url=url,
                snapshot_content=None,
                status="ssrf_blocked",
            )
            session.add(snapshot)
            await session.commit()
            await session.refresh(snapshot)
            return {
                **_snapshot_to_dict(snapshot),
                "blocked": True,
                "reason": "SSRF 防护:目标地址为内网/保留地址",
            }

        # mock 抓取:不实际发起 HTTP 请求
        snapshot = URLSnapshot(
            url=url,
            snapshot_content=f"[mock snapshot] {url}",
            status="ok",
        )
        session.add(snapshot)
        await session.commit()
        await session.refresh(snapshot)
        return {
            **_snapshot_to_dict(snapshot),
            "blocked": False,
            "reason": None,
        }
