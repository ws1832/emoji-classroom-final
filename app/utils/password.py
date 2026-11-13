import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

password_hasher = PasswordHasher()

# 密码策略：8~128 位，至少包含一个字母和一个数字，且不含空白字符。
_PASSWORD_POLICY_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)\S{8,128}\Z")


def is_password_strong(password: str) -> bool:
    """返回密码是否满足系统强度要求。"""
    return bool(_PASSWORD_POLICY_RE.match(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return password_hasher.verify(hashed_password, plain_password)
    except (InvalidHashError, VerificationError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    return password_hasher.hash(password)
