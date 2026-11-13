"""AI worker v1 的元数据契约；用户身份、课堂和来源均由服务端任务推导。

控制与入库路由共享此严格契约；设备认证/租约/事务由服务层执行。
"""

import re
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from app.models.enums import EmojiType

_RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")
_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")


def _uuid(value):
    if isinstance(value, UUID):
        parsed = value
    elif isinstance(value, str) and _UUID.fullmatch(value):
        parsed = UUID(value)
    else:
        raise ValueError("Use a canonical UUID v4")
    if parsed.version != 4:
        raise ValueError("Use a canonical UUID v4")
    return parsed


def _captured_at(value):
    if isinstance(value, str) and _RFC3339.fullmatch(value):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("captured_at must be an RFC3339 datetime with a timezone offset")
    return value.astimezone(timezone.utc)


def _version(value):
    if type(value) is not int:
        raise ValueError("contract_version must be an integer")
    return value


PositiveId = Annotated[int, Field(strict=True, gt=0)]
Score = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]
EventUUID = Annotated[UUID, BeforeValidator(_uuid)]
CapturedAt = Annotated[datetime, BeforeValidator(_captured_at)]


class AIMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AIQuality(AIMetadata):
    """仅允许非身份、非图像质量指标；缺失 detector score 不伪填 1。"""

    detection_confidence: Score | None = None


class AIIngestEvent(AIMetadata):
    contract_version: Annotated[Literal[1], BeforeValidator(_version)] = 1
    event_id: EventUUID
    job_id: PositiveId
    generation: PositiveId
    lease_id: EventUUID
    captured_at: CapturedAt
    emoji_type: EmojiType
    confidence: Score
    model_version: Identifier
    config_revision: PositiveId
    mapping_version: Literal["five-emotions-v1"] = "five-emotions-v1"
    quality: AIQuality = Field(default_factory=AIQuality)

    @field_validator("emoji_type", mode="before")
    @classmethod
    def validate_emoji_type(cls, value):
        if not isinstance(value, (str, EmojiType)):
            raise ValueError("Use a supported EmojiType")
        return value


class AIResultBatch(AIMetadata):
    events: Annotated[list[AIIngestEvent], Field(min_length=1, max_length=50)]


class DeviceCreate(AIMetadata):
    name: Annotated[str, Field(strict=True, min_length=1, max_length=80)]
    source_alias: Identifier
    teacher_ids: Annotated[list[PositiveId], Field(max_length=100)] = Field(default_factory=list)


class DeviceUpdate(AIMetadata):
    enabled: bool = Field(strict=True)
    teacher_ids: Annotated[list[PositiveId], Field(max_length=100)]


class CredentialCreate(AIMetadata):
    valid_days: Annotated[int, Field(strict=True, ge=1, le=365)] = 90


class JobCreate(AIMetadata):
    request_id: EventUUID
    session_id: PositiveId
    device_id: PositiveId
    profile: Literal["standard", "edge"] = "edge"
    threshold: Score = 0.7
    detection_threshold: Annotated[float, Field(strict=True, gt=0, le=1, allow_inf_nan=False)] = 0.85
    sample_interval: Annotated[float, Field(strict=True, ge=0.5, le=60, allow_inf_nan=False)] = 2.0
    max_faces: Annotated[int, Field(strict=True, ge=1, le=30)] = 10


class JobAction(AIMetadata):
    action: Literal["start", "pause", "stop"]
    revision: PositiveId


class WorkerMetrics(AIMetadata):
    sampled: Annotated[int, Field(strict=True, ge=0)] = 0
    no_face: Annotated[int, Field(strict=True, ge=0)] = 0
    multi_face: Annotated[int, Field(strict=True, ge=0)] = 0
    filtered: Annotated[int, Field(strict=True, ge=0)] = 0
    published: Annotated[int, Field(strict=True, ge=0)] = 0
    queue_size: Annotated[int, Field(strict=True, ge=0, le=5000)] = 0
    dropped: Annotated[int, Field(strict=True, ge=0)] = 0
    inference_ms: Annotated[float, Field(strict=True, ge=0, le=3600000, allow_inf_nan=False)] = 0


class WorkerHeartbeat(AIMetadata):
    incarnation: EventUUID
    profiles: Annotated[list[Literal["edge", "standard"]], Field(max_length=2)]
    health: Literal["ready", "waiting", "no_frame", "no_face", "model_failed", "buffering", "degraded"] = "ready"


class WorkerAck(AIMetadata):
    incarnation: EventUUID
    generation: PositiveId
    lease_id: EventUUID | None = None
    observed: Literal["ready", "running", "paused", "stopped", "failed"]
    health: Literal["ready", "no_frame", "no_face", "model_failed", "buffering", "degraded", "eof", "waiting"] = "ready"
    metrics: WorkerMetrics = Field(default_factory=WorkerMetrics)


class BrowserPolicy(AIMetadata):
    enabled: bool = Field(strict=True)
    revision: Annotated[int, Field(strict=True, ge=0)]
    sample_interval: Literal[5, 10, 15, 30] = 10
    threshold: Score = 0.7

    @field_validator("sample_interval", mode="before")
    @classmethod
    def strict_interval(cls, value):
        if type(value) is not int:
            raise ValueError("Use an integer sampling interval")
        return value


class BrowserOpen(AIMetadata):
    consent: Literal[True]

    @field_validator("consent", mode="before")
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError("Explicit camera consent is required")
        return value


class BrowserClaim(AIMetadata):
    capture_token: Annotated[str, Field(strict=True, min_length=70, max_length=100)]
    event_id: EventUUID
    payload_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    incarnation: EventUUID


class BrowserOutcome(AIMetadata):
    event_id: EventUUID
    reason: Literal["ready", "no_face", "multi_face", "filtered", "invalid_image", "model_failed"]
    faces: Annotated[int, Field(strict=True, ge=0, le=5000)]
    inference_ms: Annotated[float, Field(strict=True, ge=0, le=3600000, allow_inf_nan=False)] = 0.0
