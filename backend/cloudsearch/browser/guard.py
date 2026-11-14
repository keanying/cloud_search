"""出口防护（SSRF）：只允许 http/https 访问公网地址。

每个请求（含重定向每一跳、子资源、iframe、弹窗）都经 BrowserContext.route 检查；
主机名解析出的任一地址落在环回/私网/链路本地/保留/云元数据范围即拒绝。结果按主机短期缓存。
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import time
from urllib.parse import urlsplit

from ..core.config import get_settings

_CACHE_TTL_S = 300
_cache: dict[str, tuple[float, bool]] = {}

BLOCKED_HOSTS = {"metadata.google.internal", "metadata", "localhost"}
# 代理软件 TUN/fake-ip 模式（Clash 等）把所有域名解析到 198.18.0.0/15，真实连接由代理完成，不是内网地址
FAKE_IP_NET = ipaddress.ip_network("198.18.0.0/15")
log = logging.getLogger(__name__)
_logged: set[str] = set()


class UrlNotAllowed(Exception):
    pass


def _ip_allowed(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    if addr in FAKE_IP_NET:
        return True
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
                or addr.is_reserved or addr.is_unspecified or str(addr) == "100.100.100.200")


async def host_allowed(host: str) -> bool:
    host = host.strip("[]").lower().rstrip(".")
    if get_settings().browser_allow_private_network:
        return True
    if not host or host in BLOCKED_HOSTS or host.endswith(".internal") or host.endswith(".local"):
        return False
    now = time.monotonic()
    hit = _cache.get(host)
    if hit and hit[0] > now:
        return hit[1]
    why = ""
    try:
        ipaddress.ip_address(host)
        ok = _ip_allowed(host)
        why = "内网/保留地址"
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
            ips = {i[4][0] for i in infos}
            ok = bool(ips) and all(_ip_allowed(ip) for ip in ips)
            why = f"解析到内网/保留地址 {', '.join(sorted(ips))[:80]}"
        except OSError as e:
            # 配置了代理时由代理在远端解析域名：本机 DNS 解析不到（如被污染、只走代理）不代表是内网地址
            ok = bool(get_settings().browser_proxy)
            why = f"本机无法解析域名（{type(e).__name__}），且未配置 browser.proxy"
    _cache[host] = (now + _CACHE_TTL_S, ok)
    if not ok and host not in _logged:
        _logged.add(host)
        log.warning("出口防护拦截了对 %s 的访问：%s。如果这是正常网站（例如验证码组件所需资源），"
                    "请检查网络/DNS 或在 config.yaml 中设置 browser.proxy", host, why)
    return ok


async def check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UrlNotAllowed(f"不允许的协议: {parts.scheme or '空'}")
    if parts.port not in (None, 80, 443, 8080, 8443):
        raise UrlNotAllowed(f"不允许的端口: {parts.port}")
    if not await host_allowed(parts.hostname or ""):
        raise UrlNotAllowed(f"目标地址不在允许的公网范围: {parts.hostname}")


async def request_allowed(url: str) -> bool:
    """子资源级检查（data:/blob: 等不发网络请求的协议放行）。"""
    parts = urlsplit(url)
    if parts.scheme in ("data", "blob", "about"):
        return True
    if parts.scheme not in ("http", "https", "ws", "wss"):
        return False
    return await host_allowed(parts.hostname or "")
