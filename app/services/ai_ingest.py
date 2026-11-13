"""AI 设备范围、租约采集窗口和幂等事务入库；不提供无鉴权写库入口。"""

import hashlib
import json
from datetime import datetime, timedelta

from app.schemas.ai import AIIngestEvent
from app.utils.time import BEIJING
from app.core.ai_auth import naive, require_current, utc_now, wall
from app.models.ai import AIDevice, AIJob, AILease, AIReceipt, AIRecordMetadata
from app.models.classroom import ClassSession, EmojiRecord
from app.models.enums import EmojiSource
from fastapi import HTTPException
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction


def canonical_event(event: AIIngestEvent) -> str:
    """归一化 UUID/UTC/浮点字段，为相同事件的重试生成稳定内容。"""

    return json.dumps(
        event.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def event_payload_hash(event: AIIngestEvent) -> str:
    return hashlib.sha256(canonical_event(event).encode("utf-8")).hexdigest()


def business_timestamp(event: AIIngestEvent) -> datetime:
    """仅在新 AI 边界将 UTC 转为旧 A/B/C 使用的北京 wall-clock。"""

    return event.captured_at.astimezone(BEIJING).replace(tzinfo=None)


def validate_capture_time(
    event: AIIngestEvent,
    *,
    session_start: datetime,
    session_end: datetime,
    now: datetime,
    max_lateness: timedelta = timedelta(minutes=15),
    future_skew: timedelta = timedelta(seconds=30),
) -> datetime:
    """校验课堂 [start,end) 与实时补交窗；租约采集窗须额外校验。

    课堂输入沿用已有无时区北京时间，now 必须有时区。阈值是协议初值，
    不意味着允许绕过任务、已撤销设备或 generation/fencing 校验。
    """

    if session_start.utcoffset() is not None or session_end.utcoffset() is not None:
        raise ValueError("Session times must use Beijing wall-clock")
    if now.utcoffset() is None:
        raise ValueError("Server time must be timezone-aware")
    if session_end <= session_start or max_lateness < timedelta(0) or future_skew < timedelta(0):
        raise ValueError("Invalid capture time policy")
    timestamp = business_timestamp(event)
    if not session_start <= timestamp < session_end:
        raise ValueError("Capture is outside the classroom time window")
    if event.captured_at > now + future_skew:
        raise ValueError("Capture is too far in the future")
    if event.captured_at < now - max_lateness:
        raise ValueError("Capture is outside the realtime retry window")
    return timestamp


async def ingest_event(identity, event: AIIngestEvent):
    """授权后事务 receipt + 业务记录 + metadata；重试保持原过滤决定。"""
    now_utc = utc_now()
    now = wall(now_utc)
    try:
        async with in_transaction() as db:
            # 同设备 control/heartbeat/credential/ingest 共用行锁，避免撤销竞态。
            await AIDevice.filter(id=identity.device_id).using_db(db).select_for_update().first()
            credential, device = await require_current(identity, db)
            job = await AIJob.filter(id=event.job_id, device_id=device.id).using_db(db).select_for_update().first()
            if not job:
                raise HTTPException(403, "Event is outside device job scope")
            browser_frame = None
            if job.input_kind == "browser":
                from app.services.browser_capture import validate_event
                browser_frame = await validate_event(job, event, db)
            session = await ClassSession.filter(id=job.session_id).using_db(db).first()
            lease = (
                await AILease.filter(
                    job_id=job.id,
                    lease_id=event.lease_id,
                    generation=event.generation,
                    credential_id=credential.id,
                )
                .using_db(db)
                .first()
            )
            if not lease or lease.revoked:
                raise HTTPException(403, "Event lease is invalid or revoked")
            captured = business_timestamp(event)
            end = naive(lease.capture_end) if lease.capture_end else naive(lease.expires_at)
            if not naive(lease.acquired_at) <= captured < end:
                raise HTTPException(422, "Capture is outside the authorized lease window")
            if (
                event.model_version != job.model_version
                or event.mapping_version != job.mapping_version
                or event.config_revision != job.config_revision
            ):
                raise HTTPException(409, "Event does not match the approved model/config snapshot")
            try:
                validate_capture_time(
                    event, session_start=naive(session.start_time), session_end=naive(session.end_time), now=now_utc
                )
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            digest = event_payload_hash(event)
            receipt = await AIReceipt.filter(event_id=event.event_id).using_db(db).first()
            if receipt:
                if receipt.payload_hash != digest or receipt.job_id != job.id:
                    raise HTTPException(409, "Event ID has conflicting payload")
                return {
                    "event_id": str(event.event_id),
                    "status": "duplicate",
                    "decision": receipt.decision,
                    "reason": receipt.reason,
                    "record_id": receipt.record_id,
                }
            # DB 持久限速，跨 API 进程同设备 lock 生效；不依赖内存限流。
            if (
                await AIReceipt.filter(job__device_id=device.id, received_at__gte=now - timedelta(seconds=1))
                .using_db(db)
                .count()
                >= 100
            ):
                raise HTTPException(429, "Device ingest rate exceeded")
            reason = "accepted"
            if event.confidence < job.threshold:
                reason = "low_emotion_confidence"
            detection = event.quality.detection_confidence
            if detection is None or detection < job.detection_threshold:
                reason = "low_detection_confidence"
            decision = "accepted" if reason == "accepted" else "filtered"
            record = None
            if decision == "accepted":
                record = await EmojiRecord.create(
                    session_id=job.session_id,
                    user_id=None,
                    source=EmojiSource.AI,
                    emoji_type=event.emoji_type,
                    confidence=event.confidence,
                    device_source=device.source_alias,
                    timestamp=captured,
                    using_db=db,
                )
                await AIRecordMetadata.create(
                    record_id=record.id,
                    job_id=job.id,
                    lease_id=lease.id,
                    model_version=job.model_version,
                    mapping_version=job.mapping_version,
                    config_revision=job.config_revision,
                    quality=event.quality.model_dump(exclude_none=True),
                    using_db=db,
                )
            await AIReceipt.create(
                event_id=event.event_id,
                job_id=job.id,
                payload_hash=digest,
                decision=decision,
                reason=reason,
                record_id=record.id if record else None,
                received_at=now,
                using_db=db,
            )
            if browser_frame:
                browser_frame.state, browser_frame.reason = "accepted", decision
                await browser_frame.save(using_db=db)
                metrics = dict(job.metrics)
                key = "published" if decision == "accepted" else "filtered"
                metrics[key] = metrics.get(key, 0) + 1
                job.metrics = metrics
                await job.save(using_db=db)
            return {
                "event_id": str(event.event_id),
                "status": decision,
                "decision": decision,
                "reason": reason,
                "record_id": record.id if record else None,
            }
    except IntegrityError as exc:
        # unique 是最终兜底；重试由原 event ID 再读取决定，不盲建第二条记录。
        raise HTTPException(409, "Concurrent event conflict; retry the original event") from exc
