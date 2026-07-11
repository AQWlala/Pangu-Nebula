"""SSRF 防护服务 (Phase 8A)

实现 URL 安全性检查:
- 协议白名单: 只允许 http/https
- 内网 IP 检测: 10.x / 172.16-31.x / 192.168.x / 127.x / 169.254.x / ::1 / fc00::/7
- 域名解析: 将域名解析为 IP 后再判断
- 可选白名单机制

融合来源:
- Nebula 的安全模块设计
- 通用 SSRF 防护最佳实践
"""

import ipaddress
import socket
from urllib.parse import urlparse


# 允许的协议白名单
ALLOWED_SCHEMES = {"http", "https"}

# 域名白名单(可选,为空表示不启用白名单模式)
DOMAIN_WHITELIST: set[str] = set()


class SSRFGuard:
    """SSRF 防护:URL 安全校验"""

    def validate_url(self, url: str) -> bool:
        """验证 URL 格式是否合法

        - 必须能被 urlparse 解析
        - 必须有 scheme 和 hostname
        """
        if not url:
            return False
        try:
            parsed = urlparse(url)
            return bool(parsed.scheme) and bool(parsed.hostname)
        except (ValueError, TypeError):
            return False

    def is_internal_ip(self, ip: str) -> bool:
        """判断是否为内网/保留 IP

        检测范围:
        - IPv4: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8,
                169.254.0.0/16(链路本地), 0.0.0.0/8
        - IPv6: ::1(回环), fc00::/7(唯一本地地址), fe80::/10(链路本地)
        """
        if not ip:
            return True  # 无 IP 视为不安全
        try:
            addr = ipaddress.ip_address(ip)
        except (ValueError, TypeError):
            return True  # 无法解析的 IP 视为不安全

        # IPv4 内网/保留地址
        if isinstance(addr, ipaddress.IPv4Address):
            if addr.is_private:
                return True
            if addr.is_loopback:
                return True
            if addr.is_link_local:
                return True
            if addr.is_unspecified:
                return True
            if addr.is_reserved:
                return True
            # 0.0.0.0/8
            if int(addr) < 0x01000000:
                return True
            return False

        # IPv6 内网/保留地址
        if isinstance(addr, ipaddress.IPv6Address):
            if addr.is_loopback:
                return True
            if addr.is_private:
                return True
            if addr.is_link_local:
                return True
            if addr.is_unspecified:
                return True
            if addr.is_reserved:
                return True
            # IPv4-mapped IPv6 地址 (::ffff:x.x.x.x),检查内嵌的 IPv4
            if addr.ipv4_mapped is not None:
                return self.is_internal_ip(str(addr.ipv4_mapped))
            return False

        return False

    def _resolve_hostname(self, hostname: str) -> list[str]:
        """解析域名为 IP 地址列表

        返回 IP 字符串列表,解析失败返回空列表
        """
        if not hostname:
            return []
        # 如果 hostname 本身就是 IP,直接返回
        try:
            ipaddress.ip_address(hostname)
            return [hostname]
        except ValueError:
            pass

        try:
            # 使用 getaddrinfo 获取所有 A/AAAA 记录
            infos = socket.getaddrinfo(hostname, None)
            ips: list[str] = []
            for family, _, _, _, sockaddr in infos:
                if family == socket.AF_INET:
                    ip = sockaddr[0]
                    if ip not in ips:
                        ips.append(ip)
                elif family == socket.AF_INET6:
                    ip = sockaddr[0]
                    # 去除 IPv6 地址中的 zone index
                    if "%" in ip:
                        ip = ip.split("%")[0]
                    if ip not in ips:
                        ips.append(ip)
            return ips
        except (socket.gaierror, socket.herror, OSError):
            return []

    def _is_hostname_literal_ip(self, hostname: str) -> bool:
        """判断 hostname 是否为字面量 IP"""
        try:
            ipaddress.ip_address(hostname)
            return True
        except ValueError:
            return False

    def check(self, url: str, allow_internal: bool = False) -> dict:
        """检查 URL 安全性

        检查步骤:
        1. 解析 URL
        2. 检查协议(只允许 http/https)
        3. 解析域名 IP 地址
        4. 检查是否为内网 IP
        5. 检查是否在白名单中(可选)

        返回 {"safe": bool, "threats": [...], "ip": "...", "is_internal": bool}
        """
        threats: list[dict] = []
        ip = ""
        is_internal = False

        # 1. URL 格式校验
        if not self.validate_url(url):
            return {
                "safe": False,
                "threats": [{"type": "invalid_url", "severity": "high", "detail": "URL 格式无效"}],
                "ip": None,
                "is_internal": False,
                "hostname": None,
            }

        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()
        hostname = parsed.hostname or ""

        # 2. 协议检查
        if scheme not in ALLOWED_SCHEMES:
            threats.append({
                "type": "dangerous_scheme",
                "severity": "high",
                "detail": f"不允许的协议: {scheme}, 仅允许 http/https",
            })
            return {
                "safe": False,
                "threats": threats,
                "ip": None,
                "is_internal": False,
                "hostname": hostname,
            }

        # 3. 解析 IP
        ips = self._resolve_hostname(hostname)
        if not ips:
            threats.append({
                "type": "unresolvable_hostname",
                "severity": "high",
                "detail": f"无法解析域名: {hostname}",
            })
            return {
                "safe": False,
                "threats": threats,
                "ip": None,
                "is_internal": False,
                "hostname": hostname,
            }

        ip = ips[0]

        # 4. 内网 IP 检测
        for resolved_ip in ips:
            if self.is_internal_ip(resolved_ip):
                is_internal = True
                threats.append({
                    "type": "internal_ip",
                    "severity": "high",
                    "detail": f"内网/保留 IP: {resolved_ip}",
                    "ip": resolved_ip,
                })
                break

        # 5. 白名单检查(如果配置了白名单)
        if DOMAIN_WHITELIST:
            if hostname.lower() not in DOMAIN_WHITELIST:
                threats.append({
                    "type": "not_in_whitelist",
                    "severity": "medium",
                    "detail": f"域名不在白名单中: {hostname}",
                })

        # 决定是否安全
        safe = True
        if is_internal and not allow_internal:
            safe = False
        # 非白名单不算致命威胁,但记录
        if any(t["severity"] == "high" for t in threats):
            if is_internal and allow_internal:
                # 允许内网,降级威胁
                safe = True
            elif is_internal and not allow_internal:
                safe = False
            # unresolvable/dangerous_scheme 已在上面提前返回

        return {
            "safe": safe,
            "threats": threats,
            "ip": ip,
            "is_internal": is_internal,
            "hostname": hostname,
            "all_ips": ips,
        }


# 模块级单例
ssrf_guard = SSRFGuard()
