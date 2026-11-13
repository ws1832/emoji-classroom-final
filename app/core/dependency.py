import hmac
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, Request

from app.core.ctx import CTX_USER_ID
from app.models import Course, Role, User
from app.settings import settings
from app.utils.jwt_utils import credential_tag


class AuthControl:
    # 认证层负责确认当前用户身份，并把用户 ID 放入请求上下文。
    @classmethod
    async def is_authed(cls, token: str | None = Header(None, description="token验证")) -> Optional["User"]:
        if not token or len(token) > 4096:
            raise HTTPException(status_code=401, detail="无效的Token")
        try:
            try:
                decode_data = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM],
                    options={"require": ["exp", "user_id", "credential_tag"]},
                )
            except jwt.ExpiredSignatureError:
                raise HTTPException(status_code=401, detail="登录已过期") from None
            except (jwt.InvalidTokenError, TypeError, ValueError, OverflowError):
                raise HTTPException(status_code=401, detail="无效的Token") from None
            user_id = decode_data.get("user_id")
            tag = decode_data.get("credential_tag")
            if (
                type(user_id) is not int
                or user_id < 1
                or not isinstance(tag, str)
                or len(tag) != 64
                or any(char not in "0123456789abcdef" for char in tag)
            ):
                raise HTTPException(status_code=401, detail="无效的Token")
            user = await User.filter(id=user_id).first()
            if not user or not user.is_active or not hmac.compare_digest(tag, credential_tag(user.password)):
                raise HTTPException(status_code=401, detail="Authentication failed")
            CTX_USER_ID.set(int(user_id))
            return user
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=503, detail="认证服务暂不可用") from None


async def require_admin_user(user: User = Depends(AuthControl.is_authed)) -> User:
    """动态 API 授权不能将学生/教师提升为用户、角色、审计管理员。"""
    if not user.is_superuser and not await user.roles.filter(name="ADMIN").exists():
        raise HTTPException(403, "仅管理员可管理用户、角色和审计")
    return user


class PermissionControl:
    # 权限层根据 HTTP 方法和完整路径匹配角色拥有的 API 权限。
    @classmethod
    async def has_permission(cls, request: Request, current_user: User = Depends(AuthControl.is_authed)) -> None:
        if current_user.is_superuser:
            return
        method = request.method
        # 以匹配到的 APIRoute 模板授权，不能用字符串前缀放行任意资源。
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        # 与 B 的 legacy course owner 身份一致，仅开放 D 教师功能，数据归属仍由服务强制。
        if (
            "AI控制" in getattr(route, "tags", [])
            and method == "GET"
            and await Course.filter(teacher_id=current_user.id).exists()
        ):
            return
        roles: list[Role] = await current_user.roles
        if not roles:
            raise HTTPException(status_code=403, detail="The user is not bound to a role")
        apis = [await role.apis for role in roles]
        permission_apis = list(set((api.method, api.path) for api in sum(apis, [])))
        # path = "/api/v1/auth/userinfo"
        # method = "GET"
        if (method, path) not in permission_apis:
            raise HTTPException(status_code=403, detail=f"Permission denied method:{method} path:{path}")


DependAuth = Depends(AuthControl.is_authed)
DependPermission = Depends(PermissionControl.has_permission)
