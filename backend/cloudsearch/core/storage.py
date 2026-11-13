"""私有对象存储抽象。P0 为本地目录实现；S3/OSS/TOS 兼容实现保持同一接口。

storage_ref 形如 `local://artifacts/task_x/report.md`，对外永不暴露真实路径。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from .config import get_settings
from .ids import sha256_bytes


class LocalStorage:
    scheme = "local://"

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError("非法存储路径")
        return p

    def _key(self, ref: str) -> str:
        if not ref.startswith(self.scheme):
            raise ValueError(f"不支持的存储引用: {ref}")
        return ref[len(self.scheme):]

    async def put(self, key: str, data: bytes) -> tuple[str, str]:
        """写入对象，返回 (storage_ref, sha256)。先写临时文件再原子改名。"""
        p = self._path(key)

        def _write():
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(p)

        await asyncio.to_thread(_write)
        return self.scheme + key, sha256_bytes(data)

    async def get(self, ref: str) -> bytes:
        return await asyncio.to_thread(self._path(self._key(ref)).read_bytes)

    async def exists(self, ref: str) -> bool:
        return await asyncio.to_thread(self._path(self._key(ref)).exists)


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    global _storage
    if _storage is None:
        _storage = LocalStorage(get_settings().storage_dir)
    return _storage
