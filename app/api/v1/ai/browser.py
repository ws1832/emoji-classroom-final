"""元数据控制面；图片只送到独立AI服务，不进入业务API/audit。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.ai_auth import DeviceIdentity, authenticate_device
from app.core.dependency import AuthControl, DependPermission
from app.models import User
from app.schemas.ai import BrowserClaim, BrowserOpen, BrowserOutcome, BrowserPolicy
from app.schemas.base import Success
from app.services import ai_jobs, browser_capture

router = APIRouter(prefix="/ai/browser")


@router.get("/classrooms/{session_id}", summary="学生自己的课堂摄像头配置", tags=["学生摄像头"])
async def student_policy(session_id: int, user: User = Depends(AuthControl.is_authed)):
    return Success(data=await browser_capture.policy_view(session_id, student=user))


@router.get("/manage/{session_id}", summary="所属教师只读/管理员课堂匿名摄像头汇总", tags=["AI控制"])
async def teacher_policy(session_id: int, user: User = Depends(AuthControl.is_authed)):
    await ai_jobs.require_teacher(user)
    await ai_jobs.session_for(user, session_id)
    return Success(
        data={
            **await browser_capture.policy_view(session_id),
            "can_configure": await ai_jobs.is_admin(user),
        }
    )


@router.put(
    "/manage/{session_id}", summary="管理员统一配置/启停课堂采集", dependencies=[DependPermission], tags=["AI控制"]
)
async def configure(session_id: int, payload: BrowserPolicy, user: User = Depends(AuthControl.is_authed)):
    return Success(data={**await browser_capture.configure(user, session_id, payload), "can_configure": True})


@router.post("/classrooms/{session_id}/captures", summary="明确授权后申请单一学生采集会话", tags=["学生摄像头"])
async def open_capture(session_id: int, payload: BrowserOpen, user: User = Depends(AuthControl.is_authed)):
    return Success(data=await browser_capture.open_capture(user, session_id), headers={"Cache-Control": "no-store"})


@router.post("/captures/{capture_id}/renew", summary="当前学生延续短期摄像头授权", tags=["学生摄像头"])
async def renew(capture_id: UUID, user: User = Depends(AuthControl.is_authed)):
    result = await browser_capture.renew(user, capture_id)
    if result is None:
        raise HTTPException(410, "采集授权已过期")
    return Success(data=result, headers={"Cache-Control": "no-store"})


@router.post("/captures/{capture_id}/stop", summary="停止摄像头授权并清除临时账号关联", tags=["学生摄像头"])
async def stop(capture_id: UUID, user: User = Depends(AuthControl.is_authed)):
    await browser_capture.close(user, capture_id)
    return Success()


@router.post("/worker/claim", summary="独立AI服务领取单帧时间槽票据", tags=["AI设备服务"])
async def claim(payload: BrowserClaim, identity: DeviceIdentity = Depends(authenticate_device)):
    return Success(data=await browser_capture.claim(identity, payload))


@router.post("/worker/outcomes", summary="独立AI服务上报单人检查/过滤元数据", tags=["AI设备服务"])
async def outcome(payload: BrowserOutcome, identity: DeviceIdentity = Depends(authenticate_device)):
    return Success(data=await browser_capture.outcome(identity, payload))
