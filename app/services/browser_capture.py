"""学生摄像头的短期授权与时间槽；永久业务结果保持匿名。"""

import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import HTTPException
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core.ai_auth import naive, require_current, utc_now, wall, wire
from app.models import BrowserBudget, BrowserCapture, BrowserFrame, ClassSession, Course, ScheduleUser, User
from app.models.ai import AIDevice, AIJob, AILease
from app.services import ai_jobs
from app.settings import settings

TOKEN = re.compile(r"bcc_([a-f0-9]{32})\.[A-Za-z0-9_-]{43}\Z")
TTL = 60


def upload_url():
    url = settings.AI_BROWSER_UPLOAD_URL
    if url == "/ai-stream/frames":
        return url
    parsed = urlsplit(url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1"))
    ):
        raise HTTPException(503, "浏览器推理服务需要有效HTTPS入口")
    return url


async def student_for(user, session_id, db=None):
    session = await ClassSession.filter(id=session_id).using_db(db).first()
    if not session:
        raise HTTPException(404, "课堂不存在")
    if not user.is_active or not await user.roles.filter(name="STUDENT").using_db(db).exists():
        raise HTTPException(403, "仅学生可开启自己的摄像头")
    if not await ScheduleUser.filter(user_id=user.id, session_id=session_id).using_db(db).exists():
        raise HTTPException(403, "不在此课堂排课名单")
    return session


async def latest_job(session_id, db=None):
    return await AIJob.filter(session_id=session_id, input_kind="browser").using_db(db).order_by("-id").first()


async def policy_view(session_id, student=None):
    if student:
        session = await student_for(student, session_id)
    else:
        session = await ClassSession.get(id=session_id)
    job = await latest_job(session_id)
    now = wall(utc_now())
    device = await AIDevice.get_or_none(id=settings.AI_BROWSER_DEVICE_ID) if settings.AI_BROWSER_DEVICE_ID else None
    online = bool(
        device and device.enabled and device.last_seen and now - naive(device.last_seen) < timedelta(seconds=45)
    )
    enabled = bool(job and job.desired == "running" and naive(session.start_time) <= now < naive(session.end_time))
    return {
        "session_id": session_id,
        "revision": job.generation if job else 0,
        "enabled": enabled,
        "service_ready": online,
        "sample_interval": int(job.sample_interval) if job else 10,
        "threshold": job.threshold if job else 0.7,
        "profile": job.profile if job else (device.capabilities[0] if device and device.capabilities else "edge"),
        "metrics": job.metrics if job and not student else {},
        "session_end": wire(session.end_time),
        "server_time": wire(now),
        "active_captures": (
            await BrowserCapture.filter(job_id=job.id, active_key__not_isnull=True, expires_at__gt=now).count()
            if job and not student
            else None
        ),
    }


async def stop_capture(capture, db=None):
    # 停止即清除账号关联与授权，临时票据随后清理；结果无账号外键。
    capture.active_key = None
    capture.owner_id = None
    capture.token_hash = ""
    capture.stopped_at = wall(utc_now())
    await capture.save(using_db=db)


async def stop_job_captures(job_id, db=None):
    await BrowserCapture.filter(job_id=job_id, active_key__not_isnull=True).using_db(db).update(
        active_key=None, owner_id=None, token_hash="", stopped_at=wall(utc_now())
    )


async def configure(user, session_id, payload):
    await ai_jobs.require_admin(user)
    initial = await ai_jobs.session_for(user, session_id)
    async with in_transaction() as db:
        await Course.filter(id=initial.course_id).using_db(db).select_for_update().first()
        session = await ClassSession.filter(id=session_id).using_db(db).select_for_update().first()
        await ai_jobs.session_for(user, session_id, db)
        job = await latest_job(session_id, db)
        if payload.revision != (job.generation if job else 0):
            raise HTTPException(409, "课堂采集配置已更新，请刷新")
        if payload.enabled:
            now = wall(utc_now())
            if not naive(session.start_time) <= now < naive(session.end_time):
                raise HTTPException(422, "只能在课堂时间范围内开启采集")
            device = await AIDevice.filter(id=settings.AI_BROWSER_DEVICE_ID).using_db(db).select_for_update().first()
            if (
                not device
                or not device.enabled
                or not device.last_seen
                or now - naive(device.last_seen) > timedelta(seconds=45)
                or not device.capabilities
            ):
                raise HTTPException(503, "管理员尚未启动独立AI服务")
            if (
                await AIJob.filter(session_id=session_id, input_kind="legacy", active_slot__not_isnull=True)
                .using_db(db)
                .exists()
            ):
                raise HTTPException(409, "请先停止旧采集任务")
            upload_url()
            if not job:
                job = await AIJob.create(
                    session_id=session_id,
                    device_id=device.id,
                    creator_id=user.id,
                    request_id=uuid4(),
                    input_kind="browser",
                    profile=device.capabilities[0],
                    model_version=ai_jobs.PROFILES[device.capabilities[0]],
                    threshold=payload.threshold,
                    detection_threshold=0.85,
                    sample_interval=payload.sample_interval,
                    max_faces=1,
                    active_slot=f"browser:{session_id}",
                    desired="running",
                    using_db=db,
                )
            else:
                job = await AIJob.filter(id=job.id).using_db(db).select_for_update().first()
                if payload.revision != job.generation:
                    raise HTTPException(409, "课堂采集配置已更新，请刷新")
                if job.device_id != device.id:
                    raise HTTPException(409, "AI服务身份已改变，请管理员重新配置")
                await ai_jobs.close_leases(job, db, now, revoke=True)
                await stop_job_captures(job.id, db)
                job.generation += 1
                job.config_revision += 1
                job.threshold, job.sample_interval = payload.threshold, payload.sample_interval
                job.desired, job.observed, job.active_slot = "running", "prechecking", f"browser:{session_id}"
                await job.save(using_db=db)
        elif job:
            await AIDevice.filter(id=job.device_id).using_db(db).select_for_update().first()
            job = await AIJob.filter(id=job.id).using_db(db).select_for_update().first()
            if payload.revision != job.generation:
                raise HTTPException(409, "课堂采集配置已更新，请刷新")
            await ai_jobs.close_leases(job, db, wall(utc_now()), revoke=True)
            await stop_job_captures(job.id, db)
            job.generation += 1
            job.desired, job.observed, job.active_slot = "stopped", "stopped", None
            await job.save(using_db=db)
    return await policy_view(session_id)


async def open_capture(user, session_id):
    session = await student_for(user, session_id)
    key = hmac.new(settings.SECRET_KEY.encode(), f"capture:{user.id}:{session_id}".encode(), hashlib.sha256).hexdigest()
    try:
        async with in_transaction() as db:
            await Course.filter(id=session.course_id).using_db(db).select_for_update().first()
            await ClassSession.filter(id=session_id).using_db(db).select_for_update().first()
            await User.filter(id=user.id).using_db(db).select_for_update().first()
            await student_for(user, session_id, db)
            job = await latest_job(session_id, db)
            if job:
                await AIDevice.filter(id=job.device_id).using_db(db).select_for_update().first()
                job = await AIJob.filter(id=job.id).using_db(db).select_for_update().first()
            await require_running(job, db)
            old = await BrowserCapture.filter(active_key=key).using_db(db).select_for_update().first()
            now = wall(utc_now())
            if old:
                if naive(old.expires_at) > now:
                    raise HTTPException(409, "此课堂已有一个采集页面，请先停止原页面或等待60秒超时")
                await stop_capture(old, db)
            identifier = uuid4()
            token = f"bcc_{identifier.hex}.{secrets.token_urlsafe(32)}"
            budget = await BrowserBudget.filter(key=key).using_db(db).select_for_update().first()
            if not budget:
                budget = await BrowserBudget.create(
                    key=key,
                    expires_at=naive(session.end_time) + timedelta(minutes=15),
                    phase_ms=secrets.randbelow(30000),
                    using_db=db,
                )
            capture = await BrowserCapture.create(
                capture_id=identifier,
                job_id=job.id,
                owner_id=user.id,
                active_key=key,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=min(now + timedelta(seconds=TTL), naive(session.end_time)),
                phase_ms=budget.phase_ms % int(job.sample_interval * 1000),
                using_db=db,
            )
            return {**capture_view(capture, job), "capture_token": token, "upload_url": upload_url()}
    except IntegrityError as exc:
        raise HTTPException(409, "此课堂已有活动采集会话") from exc


def capture_view(capture, job):
    now = wall(utc_now())
    return {
        "capture_id": str(capture.capture_id),
        "expires_at": wire(capture.expires_at),
        "sample_interval": int(job.sample_interval),
        "phase_ms": capture.phase_ms,
        "server_time": wire(now),
        "session_id": job.session_id,
        "session_end": None,  # 结束时间由expires_at及renew控制，不向上传授权携带用户身份。
    }


async def require_running(job, db=None):
    now = wall(utc_now())
    if not job or job.input_kind != "browser" or job.desired != "running":
        raise HTTPException(410, "课堂自动采集已停止")
    session = await ClassSession.filter(id=job.session_id).using_db(db).first()
    if not naive(session.start_time) <= now < naive(session.end_time):
        raise HTTPException(410, "课堂不在采集时间范围")
    device = await AIDevice.filter(id=job.device_id).using_db(db).first()
    if not device or not device.enabled:
        raise HTTPException(410, "AI服务已停止")
    return session


async def own_capture(user, capture_id, db=None):
    capture = await BrowserCapture.filter(capture_id=capture_id, owner_id=user.id).using_db(db).first()
    if not capture or not capture.active_key:
        raise HTTPException(410, "采集会话已结束")
    return capture


async def renew(user, capture_id):
    initial = await own_capture(user, capture_id)
    initial_job = await AIJob.get(id=initial.job_id)
    async with in_transaction() as db:
        await AIDevice.filter(id=initial_job.device_id).using_db(db).select_for_update().first()
        job = await AIJob.filter(id=initial.job_id).using_db(db).select_for_update().first()
        capture = (
            await BrowserCapture.filter(capture_id=capture_id, owner_id=user.id, active_key__not_isnull=True)
            .using_db(db)
            .select_for_update()
            .first()
        )
        if not capture:
            raise HTTPException(410, "采集会话已结束")
        session = await require_running(job, db)
        await student_for(user, job.session_id, db)
        now = wall(utc_now())
        if naive(capture.expires_at) <= now:
            await stop_capture(capture, db)
            # 返回后再raise避免事务回滚清理，由claim/cleanup同时做最终到期限制。
            return None
        capture.expires_at = min(now + timedelta(seconds=TTL), naive(session.end_time))
        await capture.save(using_db=db)
        return capture_view(capture, job)


async def close(user, capture_id):
    async with in_transaction() as db:
        capture = await BrowserCapture.filter(capture_id=capture_id).using_db(db).select_for_update().first()
        if capture and capture.owner_id == user.id:
            await stop_capture(capture, db)
        elif capture and capture.owner_id:
            raise HTTPException(403, "不是当前用户的采集会话")


async def valid_capture(capture, job, db=None):
    if not capture or not capture.active_key or not capture.owner_id or naive(capture.expires_at) <= wall(utc_now()):
        raise HTTPException(410, "采集授权已过期或撤销")
    await require_running(job, db)
    user = await User.filter(id=capture.owner_id, is_active=True).using_db(db).first()
    if not user:
        raise HTTPException(410, "采集授权已失效")
    try:
        await student_for(user, job.session_id, db)
    except HTTPException as exc:
        raise HTTPException(410, "排课或账号权限已失效") from exc


async def claim(identity, payload):
    match = TOKEN.fullmatch(payload.capture_token)
    if not match:
        raise HTTPException(410, "无效采集授权")
    now = wall(utc_now())
    async with in_transaction() as db:
        await AIDevice.filter(id=identity.device_id).using_db(db).select_for_update().first()
        _, device = await require_current(identity, db)
        if str(device.incarnation) != str(payload.incarnation):
            raise HTTPException(409, "AI服务代际已失效")
        initial = await BrowserCapture.filter(capture_id=UUID(match.group(1))).using_db(db).first()
        job = (
            await AIJob.filter(id=initial.job_id, device_id=device.id).using_db(db).select_for_update().first()
            if initial
            else None
        )
        capture = (
            await BrowserCapture.filter(id=initial.id).using_db(db).select_for_update().first() if initial else None
        )
        digest = hashlib.sha256(payload.capture_token.encode()).hexdigest()
        if not capture or not hmac.compare_digest(capture.token_hash, digest):
            raise HTTPException(410, "无效采集授权")
        if not job:
            raise HTTPException(403, "采集授权不属于此AI服务")
        await valid_capture(capture, job, db)
        prior = await BrowserFrame.filter(event_id=payload.event_id).using_db(db).first()
        if prior:
            if prior.capture_id != capture.id or prior.payload_hash != payload.payload_hash:
                raise HTTPException(409, "重复请求内容冲突")
            if prior.generation != job.generation:
                raise HTTPException(410, "采样代际已失效")
            return {"duplicate": True, "reason": prior.reason, "state": prior.state}
        lease = (
            await AILease.filter(
                job_id=job.id,
                generation=job.generation,
                incarnation=payload.incarnation,
                credential_id=identity.credential_id,
                revoked=False,
                capture_end=None,
                expires_at__gt=now,
            )
            .using_db(db)
            .first()
        )
        if not lease:
            raise HTTPException(503, "AI服务正在重新领取租约")
        budget = await BrowserBudget.filter(key=capture.active_key).using_db(db).select_for_update().first()
        if not budget:
            raise HTTPException(410, "采集配额已到期")
        # 明确使用UTC epoch，不依赖服务器操作系统时区。重开页面不重置配额/相位。
        slot = int((utc_now().timestamp() * 1000 - capture.phase_ms) // (job.sample_interval * 1000))
        if (budget.sample_interval == job.sample_interval and slot <= budget.last_slot) or (
            budget.sample_interval != job.sample_interval
            and budget.last_claim_at
            and now - naive(budget.last_claim_at) < timedelta(seconds=job.sample_interval)
        ):
            raise HTTPException(429, "尚未到下一个采样时间槽")
        budget.last_slot, budget.last_claim_at, budget.sample_interval = slot, now, int(job.sample_interval)
        await budget.save(using_db=db)
        capture.last_slot = slot
        await capture.save(using_db=db)
        frame = await BrowserFrame.create(
            event_id=payload.event_id,
            capture_id=capture.id,
            job_id=job.id,
            lease_id=lease.id,
            generation=job.generation,
            slot=slot,
            payload_hash=payload.payload_hash,
            captured_at=now,
            using_db=db,
        )
        return {
            "duplicate": False,
            "event_id": str(frame.event_id),
            "job_id": job.id,
            "generation": job.generation,
            "lease_id": str(lease.lease_id),
            "captured_at": wire(frame.captured_at),
            "model_version": job.model_version,
            "config_revision": job.config_revision,
            "mapping_version": job.mapping_version,
            "threshold": job.threshold,
            "detection_threshold": job.detection_threshold,
            "profile": job.profile,
        }


def count_outcome(job, frame, reason):
    if frame.counted:
        return
    metrics = dict(job.metrics)
    metrics["sampled"] = metrics.get("sampled", 0) + 1
    if reason in ("no_face", "multi_face"):
        metrics[reason] = metrics.get(reason, 0) + 1
    elif reason != "ready":
        metrics["filtered"] = metrics.get("filtered", 0) + 1
    metrics["inference_ms"] = frame.inference_ms
    job.metrics, frame.counted = metrics, True


async def outcome(identity, payload):
    async with in_transaction() as db:
        await AIDevice.filter(id=identity.device_id).using_db(db).select_for_update().first()
        await require_current(identity, db)
        initial = await BrowserFrame.filter(event_id=payload.event_id).using_db(db).first()
        job = (
            await AIJob.filter(id=initial.job_id, device_id=identity.device_id).using_db(db).select_for_update().first()
            if initial
            else None
        )
        frame = await BrowserFrame.filter(id=initial.id).using_db(db).select_for_update().first() if initial else None
        if not job:
            raise HTTPException(410, "采样票据不存在")
        capture = await BrowserCapture.filter(id=frame.capture_id).using_db(db).select_for_update().first()
        await valid_capture(capture, job, db)
        if frame.generation != job.generation:
            raise HTTPException(410, "课堂配置已改变")
        if (
            (payload.reason == "ready" and payload.faces != 1)
            or (payload.reason == "no_face" and payload.faces != 0)
            or (payload.reason == "multi_face" and payload.faces < 2)
            or (payload.reason == "filtered" and payload.faces != 1)
        ):
            raise HTTPException(422, "单人采样规则不匹配")
        if frame.state != "claimed":
            return {"reason": frame.reason}
        frame.reason, frame.inference_ms = payload.reason, payload.inference_ms
        frame.state = "ready" if payload.reason == "ready" else "filtered"
        count_outcome(job, frame, payload.reason)
        await frame.save(using_db=db)
        await job.save(using_db=db)
        return {"reason": frame.reason}


async def validate_event(job, event, db):
    frame = await BrowserFrame.filter(event_id=event.event_id, job_id=job.id).using_db(db).select_for_update().first()
    if not frame or frame.state not in ("ready", "accepted") or frame.generation != event.generation:
        raise HTTPException(410, "没有单人推理确认的采样票据")
    capture = await BrowserCapture.filter(id=frame.capture_id).using_db(db).select_for_update().first()
    await valid_capture(capture, job, db)
    if frame.generation != job.generation or wire(frame.captured_at) != event.captured_at.isoformat().replace(
        "+00:00", "Z"
    ):
        raise HTTPException(410, "采样配置或时间已失效")
    return frame


async def cleanup():
    now = wall(utc_now())
    await BrowserCapture.filter(active_key__not_isnull=True, expires_at__lte=now).update(
        active_key=None, owner_id=None, token_hash="", stopped_at=now
    )
    # 身份信息清除立即生效，票据保留15分钟供安全幂等/拒绝，之后删除有限批次。
    stale = (
        await BrowserFrame.filter(captured_at__lt=now - timedelta(minutes=15)).limit(200).values_list("id", flat=True)
    )
    await BrowserFrame.filter(id__in=stale).delete()
    captures = (
        await BrowserCapture.filter(active_key=None, stopped_at__lt=now - timedelta(minutes=15))
        .limit(200)
        .values_list("id", flat=True)
    )
    await BrowserCapture.filter(id__in=captures).delete()
    budgets = await BrowserBudget.filter(expires_at__lt=now).limit(200).values_list("id", flat=True)
    await BrowserBudget.filter(id__in=budgets).delete()
