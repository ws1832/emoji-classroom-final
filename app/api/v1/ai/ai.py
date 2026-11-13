"""AI 推理服务入库 REST API。"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.controllers.ai import ai_controller
from app.core.ai_auth import DeviceIdentity, authenticate_device
from app.core.dependency import AuthControl, DependPermission
from app.models import User
from app.schemas.ai import (
    AIIngestEvent,
    AIResultBatch,
    CredentialCreate,
    DeviceCreate,
    DeviceUpdate,
    JobAction,
    JobCreate,
    WorkerAck,
    WorkerHeartbeat,
)
from app.schemas.base import Success
from app.services import ai_jobs
from app.services.ai_ingest import ingest_event

router = APIRouter(prefix="/ai", tags=["AI控制"])
worker_router = APIRouter(prefix="/ai", tags=["AI设备服务"])


@router.get("/model-profiles", dependencies=[DependPermission], summary="获准模型配置")
async def profiles(user: User = Depends(AuthControl.is_authed)):
    await ai_jobs.require_teacher(user)
    return Success(data=[{"id": key, "model_version": value} for key, value in ai_jobs.PROFILES.items()])


@router.get("/devices", dependencies=[DependPermission], summary="授权 AI 设备列表")
async def devices(user: User = Depends(AuthControl.is_authed)):
    return Success(data=await ai_controller.list_devices(user))


@router.post("/devices", dependencies=[DependPermission], summary="注册 AI 采集设备")
async def create_device(payload: DeviceCreate, user: User = Depends(AuthControl.is_authed)):
    return Success(data=await ai_controller.create_device(user, payload))


@router.put("/devices/{device_id}", dependencies=[DependPermission], summary="启用/分配 AI 设备")
async def update_device(device_id: int, payload: DeviceUpdate, user: User = Depends(AuthControl.is_authed)):
    return Success(data=await ai_controller.update_device(user, device_id, payload))


@router.post("/devices/{device_id}/credentials", dependencies=[DependPermission], summary="一次性签发/轮换设备凭证")
async def credential(device_id: int, payload: CredentialCreate, user: User = Depends(AuthControl.is_authed)):
    return Success(
        data=await ai_jobs.issue_credential(user, device_id, payload.valid_days), headers={"Cache-Control": "no-store"}
    )


@router.delete("/devices/{device_id}/credentials", dependencies=[DependPermission], summary="撤销设备凭证与任务")
async def revoke(device_id: int, user: User = Depends(AuthControl.is_authed)):
    await ai_jobs.revoke_credentials(user, device_id)
    return Success()


@router.get("/jobs", dependencies=[DependPermission], summary="课堂 AI 任务列表")
async def jobs(session_id: int | None = Query(None, gt=0), user: User = Depends(AuthControl.is_authed)):
    return Success(data=await ai_controller.list_jobs(user, session_id))


@router.post("/jobs", dependencies=[DependPermission], summary="创建课堂任务/预检")
async def create_job(payload: JobCreate, user: User = Depends(AuthControl.is_authed)):
    return Success(data=await ai_controller.create_job(user, payload))


@router.get("/jobs/{job_id}", dependencies=[DependPermission], summary="课堂任务状态")
async def job(job_id: int, user: User = Depends(AuthControl.is_authed)):
    return Success(data=await ai_jobs.job_view(await ai_jobs.job_for(user, job_id)))


@router.post("/jobs/{job_id}/actions", dependencies=[DependPermission], summary="开始/暂停/停止课堂采集")
async def control(job_id: int, payload: JobAction, user: User = Depends(AuthControl.is_authed)):
    return Success(data=await ai_controller.control_job(user, job_id, payload))


@worker_router.post("/worker/heartbeat", summary="节点心跳/任务领取/续租")
async def heartbeat(payload: WorkerHeartbeat, identity: DeviceIdentity = Depends(authenticate_device)):
    return Success(data=await ai_jobs.heartbeat(identity, payload))


@worker_router.post("/worker/jobs/{job_id}/ack", summary="节点预检/状态确认")
async def ack(job_id: int, payload: WorkerAck, identity: DeviceIdentity = Depends(authenticate_device)):
    return Success(data=await ai_jobs.acknowledge(identity, job_id, payload))


@worker_router.post("/emoji-results", summary="匿名表情可靠入库")
async def ingest(payload: AIIngestEvent, identity: DeviceIdentity = Depends(authenticate_device)):
    return Success(data=await ingest_event(identity, payload))


@worker_router.post("/emoji-results/batch", summary="有界批次/逐事件回执")
async def batch(payload: AIResultBatch, identity: DeviceIdentity = Depends(authenticate_device)):
    results = []
    for event in payload.events:
        try:
            results.append(await ingest_event(identity, event))
        except HTTPException as exc:
            if exc.status_code in (401, 403):
                raise
            results.append(
                {"event_id": str(event.event_id), "status": "rejected", "code": exc.status_code, "reason": exc.detail}
            )
    return Success(data=results)
