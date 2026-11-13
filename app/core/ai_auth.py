"""独立设备 opaque credential；不接受用户 JWT，不返回可重用 secret。"""

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models.ai import AICredential, AIDevice
from app.utils.time import BEIJING

bearer = HTTPBearer(auto_error=False, scheme_name="AIDeviceCredential")
_TOKEN = re.compile(r"aic_([a-f0-9]{32})\.[A-Za-z0-9_-]{43}\Z")


def utc_now():
    return datetime.now(timezone.utc)


def wall(value):
    return value.astimezone(BEIJING).replace(tzinfo=None)


def naive(value):
    # Tortoise may attach the configured business timezone even with use_tz=False.
    return value.replace(tzinfo=None)


def wire(value):
    return BEIJING.localize(naive(value)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class DeviceIdentity:
    credential_id: int
    device_id: int


async def require_current(identity: DeviceIdentity, db=None):
    credential = await AICredential.filter(id=identity.credential_id).using_db(db).first()
    device = await AIDevice.filter(id=identity.device_id).using_db(db).first()
    if not credential or credential.revoked or naive(credential.expires_at) <= wall(utc_now()):
        raise HTTPException(401, "Device credential expired or revoked")
    if not device or not device.enabled or credential.device_id != device.id:
        raise HTTPException(403, "Device is disabled")
    return credential, device


async def authenticate_device(auth: HTTPAuthorizationCredentials = Security(bearer)):
    if not auth or auth.scheme.lower() != "bearer":
        raise HTTPException(401, "Independent device credential required")
    match = _TOKEN.fullmatch(auth.credentials)
    if not match:
        raise HTTPException(401, "Invalid device credential")
    credential = await AICredential.get_or_none(key_id=match.group(1))
    digest = hashlib.sha256(auth.credentials.encode()).hexdigest()
    if not credential or not hmac.compare_digest(credential.secret_hash, digest):
        raise HTTPException(401, "Invalid device credential")
    identity = DeviceIdentity(credential.id, credential.device_id)
    await require_current(identity)
    return identity
