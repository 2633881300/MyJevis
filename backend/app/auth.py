"""认证：密码哈希、JWT 签发与校验。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.harness.config import settings

# auto_error=False：没带 token 时返回 None，由我们自己抛 401（错误信息更可控）
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """bcrypt 加盐哈希。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """校验密码。格式异常时返回 False 而不是抛错。"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int) -> str:
    """签发 JWT，sub 里放 user_id（规范要求字符串）。"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """依赖：从 Authorization: Bearer <token> 解析出当前用户。"""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或登录已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if cred is None:
        raise unauthorized

    try:
        payload = jwt.decode(
            cred.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise unauthorized
        return {"sub": user_id}
    except JWTError:
        raise unauthorized
