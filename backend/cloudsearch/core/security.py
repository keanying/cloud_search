"""密码哈希、JWT 与 API Key 加密（密钥只在后端，前端与智能体只见引用/掩码）。"""

from __future__ import annotations

import base64
import hashlib
from datetime import timedelta

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings
from .ids import utcnow


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: str, project_id: str) -> str:
    s = get_settings()
    now = utcnow()
    payload = {"sub": user_id, "prj": project_id, "iat": now, "exp": now + timedelta(minutes=s.access_token_minutes)}
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])


def _fernet() -> Fernet:
    s = get_settings()
    key = s.master_key
    if not key:
        # 开发兜底：由 secret_key 派生。生产必须配置独立 CS_MASTER_KEY。
        key = base64.urlsafe_b64encode(hashlib.sha256(("mk:" + s.secret_key).encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:  # 主密钥变更或数据损坏
        raise ValueError("无法解密已保存的密钥，请检查 CS_MASTER_KEY 是否变更") from e


def mask_secret(plain: str) -> str:
    if len(plain) <= 8:
        return "****"
    return f"{plain[:3]}****{plain[-4:]}"
