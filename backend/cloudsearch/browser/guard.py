"""出口防护（SSRF）：只允许 http/https 访问公网地址。

每个请求（含重定向每一跳、子资源、iframe、弹窗）都经 BrowserContext.route 检查；
主机名解析出的任一地址落在环回/私网/链路本地/保留/云元数据范围即拒绝。结果按主机短期缓存。
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from urllib.parse import urlsplit

from ..core.config import get_settings

_CACHE_TTL_S = 300
_cache: dict[str, tuple[float, bool]] = {}

BLOCKED_HOSTS = {"metadata.google.internal", "metadata", "localhost"}


class UrlNotAllowed(Exception):
    pass


def _ip_allowed(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
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
    try:
        ipaddress.ip_address(host)
        ok = _ip_allowed(host)
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
            ips = {i[4][0] for i in infos}
            ok = bool(ips) and all(_ip_allowed(ip) for ip in ips)
        except OSError:
            ok = False
    _cache[host] = (now + _CACHE_TTL_S, ok)
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
