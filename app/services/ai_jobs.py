"""设备/课堂任务控制与租约；DB 行锁和唯一活动 slot 而非进程内字典。"""

import hashlib
import secrets
from datetime import timedelta
from uuid import uuid4
from contextlib import asynccontextmanager

from fastapi import HTTPException
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core.ai_auth import naive, require_current, utc_now, wall, wire
from app.models import Course, User
from app.models.ai import AICredential, AIDevice, AIDeviceGrant, AIJob, AILease
from app.models.classroom import ClassSession
from app.schemas.ai import DeviceCreate, DeviceUpdate, JobCreate

PROFILES = {
    "edge": "opencv-zoo-mobilefacenet-2022july-fp32",
    "standard": "deepface-emotion-0.0.104-onnx",
}
LEASE_SECONDS = 45


@asynccontextmanager
async def classroom_mutation(session_id=None, course_id=None):
    """课程→课堂锁顺序与 create_job 相同，覆盖 guard 与实际修改之间的竞态。"""
    async with in_transaction() as db:
        if session_id is not None:
            session = await ClassSession.filter(id=session_id).using_db(db).first()
            if not session:
                raise HTTPException(404, "Class session not found")
            course_id = session.course_id
        await Course.filter(id=course_id).using_db(db).select_for_update().first()
        if session_id is not None:
            await ClassSession.filter(id=session_id).using_db(db).select_for_update().first()
        yield db


async def is_admin(user):
    return user.is_superuser or await user.roles.filter(name="ADMIN").exists()


async def require_admin(user):
    if not await is_admin(user):
        raise HTTPException(403, "Only administrators can manage AI services and classroom capture")


async def require_teacher(user):
    if not await is_admin(user) and not (
        await user.roles.filter(name="TEACHER").exists() or await Course.filter(teacher_id=user.id).exists()
    ):
        raise HTTPException(403, "Only teachers and administrators can view classroom AI")


async def session_for(user, session_id, db=None):
    session = await ClassSession.filter(id=session_id).using_db(db).select_related("course").first()
    if not session:
        raise HTTPException(404, "Class session not found")
    if not await is_admin(user) and session.course.teacher_id != user.id:
        raise HTTPException(403, "Class session does not belong to the teacher")
    return session


async def job_for(user, job_id, db=None):
    job = await AIJob.filter(id=job_id).using_db(db).first()
    if not job:
        raise HTTPException(404, "AI job not found")
    await session_for(user, job.session_id, db)
    return job


async def _teacher_ids(ids, db=None):
    for identifier in set(ids):
        user = await User.filter(id=identifier, is_active=True).using_db(db).first()
        if not user or not (
            await user.roles.filter(name="TEACHER").using_db(db).exists()
            or await Course.filter(teacher_id=identifier).using_db(db).exists()
        ):
            raise HTTPException(422, "Device grants require active teachers")


async def device_view(device):
    return {
        "id": device.id,
        "name": device.name,
        "source_alias": device.source_alias,
        "enabled": device.enabled,
        "teacher_ids": await AIDeviceGrant.filter(device_id=device.id).values_list("teacher_id", flat=True),
        "health": device.health,
        "online": bool(device.last_seen and wall(utc_now()) - naive(device.last_seen) < timedelta(seconds=60)),
        "last_seen": wire(device.last_seen) if device.last_seen else None,
        "profiles": device.capabilities,
    }


async def job_view(job):
    session = await ClassSession.get(id=job.session_id).select_related("course")
    return {
        "id": job.id,
        "session_id": job.session_id,
        "device_id": job.device_id,
        "profile": job.profile,
        "input_kind": job.input_kind,
        "model_version": job.model_version,
        "mapping_version": job.mapping_version,
        "threshold": job.threshold,
        "detection_threshold": job.detection_threshold,
        "sample_interval": job.sample_interval,
        "max_faces": job.max_faces,
        "generation": job.generation,
        "config_revision": job.config_revision,
        "desired": job.desired,
        "observed": job.observed,
        "health": job.health,
        "metrics": job.metrics,
        "last_ack": wire(job.last_ack) if job.last_ack else None,
        "session_start": wire(session.start_time),
        "session_end": wire(session.end_time),
        "active": job.active_slot is not None,
    }


async def list_devices(user):
    await require_teacher(user)
    query = AIDevice.all()
    if not await is_admin(user):
        query = query.filter(grants__teacher_id=user.id)
    return [await device_view(item) for item in await query.order_by("id").limit(200)]


async def create_device(user, payload: DeviceCreate):
    await require_admin(user)
    async with in_transaction() as db:
        await _teacher_ids(payload.teacher_ids, db)
        device = await AIDevice.create(name=payload.name, source_alias=payload.source_alias, using_db=db)
        for teacher_id in set(payload.teacher_ids):
            await AIDeviceGrant.create(device_id=device.id, teacher_id=teacher_id, using_db=db)
    return await device_view(device)


async def close_leases(job, db, now, revoke=False):
    for lease in await AILease.filter(job_id=job.id, capture_end=None).using_db(db).select_for_update():
        lease.capture_end = min(now, naive(lease.expires_at))
        lease.revoked = revoke
        await lease.save(using_db=db)
    if revoke:
        await AILease.filter(job_id=job.id).using_db(db).update(revoked=True)


async def cancel_device(device_id, db, now):
    for job in await AIJob.filter(device_id=device_id, active_slot__not_isnull=True).using_db(db).select_for_update():
        await close_leases(job, db, now, revoke=True)
        job.desired, job.observed, job.health = "stopped", "stopped", "credential_revoked"
        job.active_slot, job.stopped_at = None, now
        job.generation += 1
        await job.save(using_db=db)
        if job.input_kind == "browser":
            from app.services.browser_capture import stop_job_captures
            await stop_job_captures(job.id, db)


async def update_device(user, device_id, payload: DeviceUpdate):
    await require_admin(user)
    async with in_transaction() as db:
        device = await AIDevice.filter(id=device_id).using_db(db).select_for_update().first()
        if not device:
            raise HTTPException(404, "Device not found")
        await _teacher_ids(payload.teacher_ids, db)
        old_grants = set(
            await AIDeviceGrant.filter(device_id=device.id).using_db(db).values_list("teacher_id", flat=True)
        )
        if not payload.enabled or not old_grants.issubset(set(payload.teacher_ids)):
            await cancel_device(device.id, db, wall(utc_now()))
        await AIDeviceGrant.filter(device_id=device.id).using_db(db).delete()
        for teacher_id in set(payload.teacher_ids):
            await AIDeviceGrant.create(device_id=device.id, teacher_id=teacher_id, using_db=db)
        device.enabled = payload.enabled
        await device.save(using_db=db)
    return await device_view(device)


async def issue_credential(user, device_id, valid_days):
    await require_admin(user)
    now = wall(utc_now())
    async with in_transaction() as db:
        device = await AIDevice.filter(id=device_id).using_db(db).select_for_update().first()
        if not device or not device.enabled:
            raise HTTPException(404, "Enabled device not found")
        await cancel_device(device.id, db, now)
        await AICredential.filter(device_id=device.id).using_db(db).update(revoked=True)
        key = uuid4().hex
        token = f"aic_{key}.{secrets.token_urlsafe(32)}"
        item = await AICredential.create(
            key_id=key,
            secret_hash=hashlib.sha256(token.encode()).hexdigest(),
            device_id=device.id,
            expires_at=now + timedelta(days=valid_days),
            using_db=db,
        )
    return {"credential_id": item.id, "expires_at": wire(item.expires_at), "token": token}


async def revoke_credentials(user, device_id):
    await require_admin(user)
    async with in_transaction() as db:
        device = await AIDevice.filter(id=device_id).using_db(db).select_for_update().first()
        if not device:
            raise HTTPException(404, "Device not found")
        await AICredential.filter(device_id=device.id).using_db(db).update(revoked=True)
        await cancel_device(device.id, db, wall(utc_now()))


async def _reap(job, db, now):
    if job.desired != "stopped":
        return
    live = await AILease.filter(job_id=job.id, expires_at__gt=now, revoked=False).using_db(db).exists()
    if not live:
        job.active_slot = None
        job.observed = "stopped"
        await job.save(using_db=db)


async def create_job(user, payload: JobCreate):
    await require_admin(user)
    try:
        async with in_transaction() as db:
            initial = await ClassSession.filter(id=payload.session_id).using_db(db).first()
            if not initial:
                raise HTTPException(404, "Class session not found")
            await Course.filter(id=initial.course_id).using_db(db).select_for_update().first()
            await ClassSession.filter(id=payload.session_id).using_db(db).select_for_update().first()
            session = await session_for(user, payload.session_id, db)
            if await AIJob.filter(
                session_id=payload.session_id, input_kind="browser", active_slot__not_isnull=True
            ).using_db(db).exists():
                raise HTTPException(409, "Student browser capture already owns this classroom")
            if naive(session.end_time) <= wall(utc_now()):
                raise HTTPException(422, "Classroom has already ended")
            device = await AIDevice.filter(id=payload.device_id).using_db(db).select_for_update().first()
            if not device or not device.enabled:
                raise HTTPException(404, "Enabled device not found")
            if (
                not await is_admin(user)
                and not await AIDeviceGrant.filter(device_id=device.id, teacher_id=user.id).using_db(db).exists()
            ):
                raise HTTPException(403, "Device is not assigned to this teacher")
            existing = await AIJob.filter(request_id=payload.request_id).using_db(db).first()
            if existing:
                if any(
                    getattr(existing, key) != value for key, value in payload.model_dump(exclude={"request_id"}).items()
                ):
                    raise HTTPException(409, "Request ID reused with different job configuration")
                await job_for(user, existing.id, db)
                return await job_view(existing)
            slot = str(device.id)
            active = await AIJob.filter(active_slot=slot).using_db(db).select_for_update().first()
            if active:
                await _reap(active, db, wall(utc_now()))
                if active.active_slot:
                    raise HTTPException(409, "Device already has an active classroom job")
            job = await AIJob.create(
                **payload.model_dump(),
                model_version=PROFILES[payload.profile],
                creator_id=user.id,
                active_slot=slot,
                using_db=db,
            )
        return await job_view(job)
    except IntegrityError as exc:
        raise HTTPException(409, "Concurrent job already occupies this device/request ID") from exc


async def list_jobs(user, session_id=None):
    await require_teacher(user)
    query = AIJob.all()
    if session_id:
        await session_for(user, session_id)
        query = query.filter(session_id=session_id)
    if not await is_admin(user):
        query = query.filter(session__course__teacher_id=user.id)
    return [await job_view(job) for job in await query.order_by("-id").limit(100)]


async def control_job(user, job_id, payload):
    await require_admin(user)
    initial = await job_for(user, job_id)
    async with in_transaction() as db:
        device = await AIDevice.filter(id=initial.device_id).using_db(db).select_for_update().first()
        job = await AIJob.filter(id=job_id).using_db(db).select_for_update().first()
        if job.input_kind == "browser":
            raise HTTPException(409, "Use classroom browser capture configuration")
        session = await session_for(user, job.session_id, db)
        if job.generation != payload.revision:
            raise HTTPException(409, "Stale job revision; refresh status")
        target = {"start": "running", "pause": "paused", "stop": "stopped"}[payload.action]
        if target == job.desired:
            return await job_view(job)
        if job.desired == "stopped" or not job.active_slot:
            raise HTTPException(409, "Stopped jobs cannot restart; create a new job")
        now = wall(utc_now())
        if target == "running":
            if not device.enabled:
                raise HTTPException(403, "Device is disabled")
            if (
                not await is_admin(user)
                and not await AIDeviceGrant.filter(device_id=device.id, teacher_id=user.id).using_db(db).exists()
            ):
                raise HTTPException(403, "Device assignment revoked")
            if not device.last_seen or now - naive(device.last_seen) > timedelta(seconds=60):
                raise HTTPException(409, "Device is offline")
            if job.profile not in device.capabilities:
                raise HTTPException(409, "Device has not prepared the selected profile")
            if not naive(session.start_time) <= now < naive(session.end_time):
                raise HTTPException(422, "Start is outside the classroom time window")
            if job.observed not in ("ready", "paused"):
                raise HTTPException(409, "Wait for device preflight/pause acknowledgement")
            job.started_at = job.started_at or now
        await close_leases(job, db, now)
        job.generation += 1
        job.desired = target
        if target == "stopped":
            job.stopped_at = now
            await _reap(job, db, now)
        await job.save(using_db=db)
    return await job_view(job)


async def heartbeat(identity, payload):
    now = wall(utc_now())
    async with in_transaction() as db:
        device = await AIDevice.filter(id=identity.device_id).using_db(db).select_for_update().first()
        await require_current(identity, db)
        if device.incarnation and device.incarnation != payload.incarnation:
            if device.last_seen and now - naive(device.last_seen) < timedelta(seconds=LEASE_SECONDS):
                raise HTTPException(409, "Another worker owns this device; wait for lease expiry")
            for job in (
                await AIJob.filter(device_id=device.id, active_slot__not_isnull=True).using_db(db).select_for_update()
            ):
                await close_leases(job, db, now)
                job.generation += 1
                job.observed, job.health = "prechecking", "waiting"
                await job.save(using_db=db)
        device.incarnation, device.last_seen = payload.incarnation, now
        device.health, device.capabilities = payload.health, payload.profiles
        await device.save(using_db=db)
        jobs = await AIJob.filter(device_id=device.id, active_slot__not_isnull=True).using_db(db).select_for_update()
        results = []
        for job in jobs:
            session = await ClassSession.filter(id=job.session_id).using_db(db).first()
            if now >= naive(session.end_time) and job.desired != "stopped":
                await close_leases(job, db, now)
                job.generation += 1
                job.desired, job.stopped_at = "stopped", now
                await job.save(using_db=db)
                if job.input_kind == "browser":
                    from app.services.browser_capture import stop_job_captures
                    await stop_job_captures(job.id, db)
            lease = None
            if job.desired == "running":
                lease = (
                    await AILease.filter(job_id=job.id, generation=job.generation)
                    .using_db(db)
                    .select_for_update()
                    .first()
                )
                if lease and (lease.revoked or lease.capture_end or naive(lease.expires_at) <= now):
                    await close_leases(job, db, now)
                    job.generation += 1
                    await job.save(using_db=db)
                    lease = None
                if not lease:
                    lease = await AILease.create(
                        lease_id=uuid4(),
                        job_id=job.id,
                        credential_id=identity.credential_id,
                        incarnation=payload.incarnation,
                        generation=job.generation,
                        acquired_at=now,
                        expires_at=min(now + timedelta(seconds=LEASE_SECONDS), naive(session.end_time)),
                        using_db=db,
                    )
                else:
                    lease.expires_at = min(now + timedelta(seconds=LEASE_SECONDS), naive(session.end_time))
                    await lease.save(using_db=db)
            await _reap(job, db, now)
            view = await job_view(job)
            view.update(
                source_alias=device.source_alias,
                lease_id=str(lease.lease_id) if lease else None,
                lease_expires_at=wire(lease.expires_at) if lease else None,
            )
            results.append(view)
    from app.services.browser_capture import cleanup
    await cleanup()
    return {"server_time": wire(now), "jobs": results, "heartbeat_seconds": 5, "lease_seconds": LEASE_SECONDS}


async def acknowledge(identity, job_id, payload):
    now = wall(utc_now())
    async with in_transaction() as db:
        device = await AIDevice.filter(id=identity.device_id).using_db(db).select_for_update().first()
        await require_current(identity, db)
        job = await AIJob.filter(id=job_id, device_id=device.id).using_db(db).select_for_update().first()
        if not job:
            raise HTTPException(404, "Device job not found")
        if job.input_kind == "browser":
            raise HTTPException(409, "Browser metrics are maintained by frame receipts, not legacy acknowledgements")
        if device.incarnation != payload.incarnation or job.generation != payload.generation:
            raise HTTPException(409, "Worker generation/incarnation is stale")
        if payload.observed != "failed" and payload.observed != job.desired:
            raise HTTPException(409, "Acknowledgement does not match desired state")
        if payload.observed == "running":
            lease = (
                await AILease.filter(
                    job_id=job.id,
                    lease_id=payload.lease_id,
                    generation=payload.generation,
                    credential_id=identity.credential_id,
                    capture_end=None,
                    revoked=False,
                    expires_at__gt=now,
                )
                .using_db(db)
                .first()
            )
            if not lease:
                raise HTTPException(409, "Valid lease required")
        if payload.observed in ("failed", "stopped"):
            await close_leases(job, db, now)
            if payload.observed == "failed":
                job.desired, job.stopped_at = "stopped", now
            job.active_slot = None
        job.observed, job.health = payload.observed, payload.health
        job.metrics, job.last_ack = payload.metrics.model_dump(), now
        await job.save(using_db=db)
    return await job_view(job)


async def guard_session_mutation(session_ids):
    if await AIJob.filter(session_id__in=session_ids, active_slot__not_isnull=True).exists():
        raise HTTPException(
            409, "Stop active AI jobs and wait for device acknowledgement before changing this classroom"
        )
