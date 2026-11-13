import hashlib
import hmac

import jwt

from app.schemas.login import JWTPayload
from app.settings.config import settings


def credential_tag(password_hash: str | None) -> str:
    """密码改变即撤销旧 JWT，不向客户端公开密码哈希，也无需另建会话表。"""
    return hmac.new(settings.SECRET_KEY.encode(), (password_hash or "").encode(), hashlib.sha256).hexdigest()


def create_access_token(*, data: JWTPayload):
    payload = data.model_dump().copy()
    encoded_jwt = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt
