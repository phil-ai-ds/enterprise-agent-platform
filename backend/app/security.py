"""M2-lite: 身份与授权。生产可替换为 Keycloak(OIDC) + OpenFGA；此处为本地可跑的内部 JWT 实现，
保留同样的调用语义：当前用户 + 角色（user / platform_admin）+ 团队。"""
import hashlib
import hmac
import time

import jwt

from .config import settings


def hash_password(pw: str) -> str:
    return hashlib.sha256(("eap::" + pw).encode()).hexdigest()


def verify_password(pw: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_password(pw), hashed)


def create_token(user_id: int, username: str, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": int(time.time()) + settings.token_ttl_minutes * 60,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
