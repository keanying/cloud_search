"""数据不出域（privacy.data_local_only）：用户数据只发往本机/内网服务。

开启后：
- 大模型只能使用本机或内网地址的供应方（localhost、私网 IP、*.local/*.internal/*.lan、privacy.allowed_hosts 中的域名）；
  外部供应方（DeepSeek、OpenAI 等公网地址）会被拒绝调用；
- 文件解析不使用 mineru.net 云端/轻量接口，只用自部署 MinerU、本机命令行或内置解析；
- 涉及上传文件的任务不联网搜索（避免文件内容通过搜索词外泄）；不涉及文件的公开信息搜索仍可使用。
注意：代理软件的 fake-ip 网段（198.18.0.0/15）不视为内网——外部域名在 TUN 模式下也会解析到这里。
"""

from __future__ import annotations

import ipaddress
import socket
import time
from urllib.parse import urlsplit

from .config import get_settings

FAKE_IP_NET = ipaddress.ip_network("198.18.0.0/15")
_cache: dict[str, tuple[float, bool]] = {}


def enabled() -> bool:
    return bool(get_settings().privacy_data_local_only)


def _ip_internal(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    if a in FAKE_IP_NET:
        return False
    return a.is_loopback or a.is_private or a.is_link_local


def host_internal(host: str) -> bool:
    host = (host or "").strip("[]").lower().rstrip(".")
    if not host:
        return False
    if host == "localhost" or host.endswith((".local", ".internal", ".lan", ".localhost")):
        return True
    for d in get_settings().privacy_allowed_hosts:
        d = d.lower().lstrip(".")
        if host == d or host.endswith("." + d):
            return True
    try:
        ipaddress.ip_address(host)
        return _ip_internal(host)
    except ValueError:
        pass
    hit = _cache.get(host)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    try:
        ips = {i[4][0] for i in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
        ok = bool(ips) and all(_ip_internal(ip) for ip in ips)
    except OSError:
        ok = False
    _cache[host] = (time.monotonic() + 300, ok)
    return ok


def url_internal(url: str) -> bool:
    return host_internal(urlsplit(url or "").hostname or "")
