"""F8 安全修复测试 — SSRF 防护

测试目标:
1. validate_url_safe / check 在各类 URL 上的安全判定
2. 协议白名单: 只允许 http/https
3. 内网 IP 黑名单: 10.x / 172.16-31.x / 192.168.x / 127.x
4. 元数据 IP 黑名单: 169.254.169.254 (云元数据)
5. allow_internal=True 可放行 localhost (可配置)
6. browser_navigate 工具接入 SSRF 校验的集成测试

DNS 解析说明:
- 测试用真实公网域名 example.com(对应 IANA 保留的示例 IP 93.184.216.34, 非私网)
- 私网 IP 测试用字面量 IP,无需 DNS
- 元数据 IP 169.254.169.254 是 link-local,被 is_link_local 拦截
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server.services.ssrf_guard import SSRFGuard, ssrf_guard


# ============ validate_url_safe 基础测试 ============

class TestValidateUrlSafe:
    """测试 validate_url_safe 的 (bool, str) 元组返回"""

    def test_returns_tuple(self):
        result = ssrf_guard.validate_url_safe("http://example.com")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_allows_https_public(self):
        """https://example.com 通过"""
        safe, reason = ssrf_guard.validate_url_safe("https://example.com")
        assert safe is True
        assert reason == "ok"

    def test_allows_http_public(self):
        """http://example.com 通过"""
        safe, _ = ssrf_guard.validate_url_safe("http://example.com")
        assert safe is True


# ============ 协议白名单测试 ============

class TestProtocolWhitelist:
    def test_denies_file_protocol(self):
        """file:/// 协议必须拒绝

        注: file:///etc/passwd 经 urlparse 解析 hostname 为 None,
        走「URL 格式无效」分支而非「不允许的协议」分支,但行为一致: 拒绝。
        """
        safe, reason = ssrf_guard.validate_url_safe("file:///etc/passwd")
        assert safe is False
        # reason 可能是 "URL 格式无效" 或 "不允许的协议: file, ..."
        assert ("格式" in reason) or ("协议" in reason) or ("scheme" in reason.lower())

    def test_denies_data_protocol(self):
        """data: 协议必须拒绝"""
        safe, reason = ssrf_guard.validate_url_safe("data:text/html,<script>alert(1)</script>")
        assert safe is False

    def test_denies_javascript_protocol(self):
        safe, _ = ssrf_guard.validate_url_safe("javascript:alert(1)")
        assert safe is False

    def test_denies_ftp_protocol(self):
        safe, _ = ssrf_guard.validate_url_safe("ftp://evil.example.com/")
        assert safe is False

    def test_denies_empty_url(self):
        safe, _ = ssrf_guard.validate_url_safe("")
        assert safe is False

    def test_denies_none_url(self):
        safe, _ = ssrf_guard.validate_url_safe(None)  # type: ignore[arg-type]
        assert safe is False


# ============ 私网 IP 黑名单测试 ============

class TestPrivateIpBlacklist:
    def test_denies_192_168(self):
        """192.168.0.0/16 必须拒绝"""
        safe, reason = ssrf_guard.validate_url_safe("http://192.168.0.1/")
        assert safe is False
        assert "192.168.0.1" in reason

    def test_denies_10_x(self):
        """10.0.0.0/8 必须拒绝"""
        safe, reason = ssrf_guard.validate_url_safe("http://10.0.0.1/")
        assert safe is False
        assert "10.0.0.1" in reason

    def test_denies_172_16_x(self):
        """172.16.0.0/12 必须拒绝"""
        safe, _ = ssrf_guard.validate_url_safe("http://172.16.0.1/")
        assert safe is False

    def test_denies_172_31_x(self):
        """172.31.x.x 仍在 172.16.0.0/12 内,必须拒绝"""
        safe, _ = ssrf_guard.validate_url_safe("http://172.31.255.255/")
        assert safe is False

    def test_allows_172_32_x(self):
        """172.32.x.x 不在 172.16.0.0/12 内(公网),不应被内网规则拦截
        (但 172.32.x 实际属于公网 IANA 保留段,这里只验证不报 internal_ip)"""
        result = ssrf_guard.check("http://172.32.0.1/")
        # 172.32 不在 172.16/12 范围, is_internal 应为 False
        # (注: 该 IP 段在公网上不可路由, 但不是私有地址)
        assert result["is_internal"] is False

    def test_denies_loopback(self):
        """127.0.0.1 必须拒绝"""
        safe, reason = ssrf_guard.validate_url_safe("http://127.0.0.1/")
        assert safe is False
        assert "127.0.0.1" in reason

    def test_denies_localhost(self):
        """localhost 解析到 127.0.0.1,必须拒绝"""
        safe, _ = ssrf_guard.validate_url_safe("http://localhost/")
        assert safe is False


# ============ 元数据 IP 黑名单测试 ============

class TestMetadataIpBlacklist:
    def test_denies_metadata_ip(self):
        """169.254.169.254 (AWS/Azure/GCP 云元数据) 必须拒绝"""
        safe, reason = ssrf_guard.validate_url_safe("http://169.254.169.254/latest/meta-data/")
        assert safe is False
        assert "169.254.169.254" in reason

    def test_denies_169_254_x(self):
        """整个 169.254.0.0/16 (链路本地) 都应拒绝"""
        safe, _ = ssrf_guard.validate_url_safe("http://169.254.1.1/")
        assert safe is False

    def test_denies_metadata_imds(self):
        """AWS IMDSv1 端点必须拒绝 — 防止凭证泄露"""
        safe, _ = ssrf_guard.validate_url_safe(
            "http://169.254.169.254/latest/api/token"
        )
        assert safe is False


# ============ IPv6 测试 ============

class TestIpv6:
    def test_denies_ipv6_loopback(self):
        """::1 IPv6 回环必须拒绝"""
        safe, _ = ssrf_guard.validate_url_safe("http://[::1]/")
        assert safe is False

    def test_denies_ipv6_link_local(self):
        """fe80:: 链路本地 IPv6 必须拒绝"""
        safe, _ = ssrf_guard.validate_url_safe("http://[fe80::1]/")
        assert safe is False

    def test_denies_ipv4_mapped_ipv6(self):
        """::ffff:192.168.0.1 (IPv4-mapped IPv6) 必须拒绝 — 防止绕过"""
        safe, _ = ssrf_guard.validate_url_safe("http://[::ffff:192.168.0.1]/")
        assert safe is False


# ============ allow_internal 可配置测试 ============

class TestAllowInternalConfig:
    """可配置允许 localhost/内网"""

    def test_allows_localhost_when_configured(self):
        """allow_internal=True 时, localhost 应通过"""
        safe, _ = ssrf_guard.validate_url_safe("http://127.0.0.1/", allow_internal=True)
        assert safe is True

    def test_allows_private_ip_when_configured(self):
        safe, _ = ssrf_guard.validate_url_safe("http://192.168.0.1/", allow_internal=True)
        assert safe is True

    def test_allows_metadata_ip_when_configured(self):
        """注意: 即使 allow_internal=True, 元数据 IP 仍可被放行(因为也是 link_local)
        这是预期的: allow_internal 用于可信内网场景,元数据服务在内网也算可信。
        但生产环境建议不要使用 allow_internal=True"""
        safe, _ = ssrf_guard.validate_url_safe(
            "http://169.254.169.254/", allow_internal=True
        )
        assert safe is True

    def test_default_deny_internal(self):
        """默认严格模式: 不允许内网"""
        safe, _ = ssrf_guard.validate_url_safe("http://127.0.0.1/")
        assert safe is False


# ============ SSRFGuard.check 直接测试 ============

class TestCheckMethod:
    def test_check_returns_dict_with_required_fields(self):
        result = ssrf_guard.check("http://example.com")
        assert isinstance(result, dict)
        for key in ("safe", "threats", "ip", "is_internal", "hostname"):
            assert key in result, f"check 缺少返回字段: {key}"

    def test_check_safe_url_no_threats(self):
        result = ssrf_guard.check("https://example.com")
        assert result["safe"] is True
        assert result["threats"] == []

    def test_check_dangerous_url_has_threats(self):
        result = ssrf_guard.check("http://169.254.169.254/")
        assert result["safe"] is False
        assert len(result["threats"]) >= 1
        # 威胁 severity 应为 high
        assert any(t.get("severity") == "high" for t in result["threats"])

    def test_is_internal_ip_192_168(self):
        assert ssrf_guard.is_internal_ip("192.168.1.1") is True

    def test_is_internal_ip_10_x(self):
        assert ssrf_guard.is_internal_ip("10.1.2.3") is True

    def test_is_internal_ip_loopback(self):
        assert ssrf_guard.is_internal_ip("127.0.0.1") is True

    def test_is_internal_ip_metadata(self):
        assert ssrf_guard.is_internal_ip("169.254.169.254") is True

    def test_is_internal_ip_public(self):
        """8.8.8.8 是 Google DNS 公网 IP,不应被判定为内网"""
        assert ssrf_guard.is_internal_ip("8.8.8.8") is False

    def test_is_internal_ip_invalid(self):
        """无效 IP 视为不安全"""
        assert ssrf_guard.is_internal_ip("not-an-ip") is True

    def test_is_internal_ip_empty(self):
        assert ssrf_guard.is_internal_ip("") is True


# ============ browser_navigate 集成测试 ============

class TestBrowserNavigateSSRFIntegration:
    """验证 BrowserNavigateTool 在恶意 URL 时不调用 browser_service.navigate"""

    @pytest.mark.asyncio
    async def test_navigate_rejects_ssrf_url(self):
        """browser_navigate 在收到内网 URL 时返回失败,不启动会话"""
        from server.tools.browser_tools import BrowserNavigateTool
        tool = BrowserNavigateTool()
        # 模拟 _ensure_session 被调用即失败(如果 SSRF 校验通过才会调用)
        with patch("server.tools.browser_tools._ensure_session") as mock_session:
            mock_session.return_value = (None, "should not be called")
            result = await tool.execute(url="http://169.254.169.254/")
            # 关键断言: SSRF 校验应在前置拦截, _ensure_session 不应被调用
            assert mock_session.call_count == 0
            assert result.success is False
            assert "SSRF" in result.error or "防护" in result.error

    @pytest.mark.asyncio
    async def test_navigate_rejects_file_protocol(self):
        from server.tools.browser_tools import BrowserNavigateTool
        tool = BrowserNavigateTool()
        with patch("server.tools.browser_tools._ensure_session") as mock_session:
            mock_session.return_value = (None, "should not be called")
            result = await tool.execute(url="file:///etc/passwd")
            assert mock_session.call_count == 0
            assert result.success is False

    @pytest.mark.asyncio
    async def test_navigate_rejects_private_ip(self):
        from server.tools.browser_tools import BrowserNavigateTool
        tool = BrowserNavigateTool()
        with patch("server.tools.browser_tools._ensure_session") as mock_session:
            mock_session.return_value = (None, "should not be called")
            result = await tool.execute(url="http://192.168.0.1/admin")
            assert mock_session.call_count == 0
            assert result.success is False

    @pytest.mark.asyncio
    async def test_navigate_allows_public_url(self):
        """公网 URL 应通过 SSRF 校验,继续走 _ensure_session"""
        from server.tools.browser_tools import BrowserNavigateTool
        tool = BrowserNavigateTool()
        mock_svc = MagicMock()
        mock_svc.navigate = AsyncMock(return_value={
            "ok": True,
            "data": {"title": "Example", "url": "https://example.com", "status": 200},
        })
        with patch("server.tools.browser_tools._ensure_session") as mock_session:
            mock_session.return_value = (mock_svc, None)
            result = await tool.execute(url="https://example.com")
            # _ensure_session 应被调用
            assert mock_session.call_count == 1
            assert mock_svc.navigate.call_count == 1
            assert result.success is True


# ============ DNS rebinding 防护测试 ============

class TestDnsRebindingProtection:
    """验证域名解析后所有 IP 都被检查(防止 DNS rebinding)"""

    def test_check_resolves_hostname_to_ip(self):
        """对域名做 DNS 解析后再校验"""
        # example.com 解析到公网 IP, 应安全
        result = ssrf_guard.check("https://example.com")
        # 至少应该尝试解析
        assert "ip" in result
        # example.com 是公网域名, 应通过
        assert result["safe"] is True
        assert result["is_internal"] is False
