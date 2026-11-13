"""不透明ID与时间工具。ID 形如 `conv_01JC...`（前缀 + 时间有序的 Crockford base32）。"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid() -> str:
    ts = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ts << 80) | rand
    out = []
    for _ in range(26):
        out.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(out))


def new_id(prefix: str) -> str:
    return f"{prefix}_{_ulid()}"


def utcnow() -> datetime:
    """UTC 时间（naive，数据库统一按 UTC 存储）。"""
    return datetime.now(UTC).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.replace(microsecond=(dt.microsecond // 1000) * 1000).isoformat(timespec="milliseconds") + "Z"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(obj) -> str:
    """规范 JSON（键排序、无空白、UTF-8）的 SHA-256。"""
    return sha256_bytes(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
