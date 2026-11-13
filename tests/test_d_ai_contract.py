"""D v1：拒绝原始素材/类型强转，采样时间适配及重试 canonical hash。"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.ai import AIIngestEvent, AIResultBatch
from app.services.ai_ingest import business_timestamp, event_payload_hash, validate_capture_time


def event_payload(**changes):
    return {
        "contract_version": 1,
        "event_id": "7dd9ab8d-6f1c-467a-922f-f19f7a87514a",
        "job_id": 23,
        "generation": 4,
        "lease_id": "e573b86d-1d5b-44f0-915b-38d58c1cb5a9",
        "captured_at": "2026-11-11T16:00:00.123Z",
        "emoji_type": "HAPPY",
        "confidence": 0.91,
        "model_version": "deepface-emotion-0.0.104-onnx",
        "config_revision": 3,
        "mapping_version": "five-emotions-v1",
        "quality": {"detection_confidence": 0.96},
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"confidence": True},
        {"confidence": "0.9"},
        {"confidence": float("nan")},
        {"confidence": float("inf")},
        {"confidence": -0.1},
        {"confidence": 1.01},
        {"job_id": True},
        {"job_id": 1.0},
        {"job_id": "1"},
        {"generation": 0},
        {"config_revision": False},
        {"contract_version": True},
        {"contract_version": 1.0},
        {"contract_version": 2},
        {"event_id": "not-a-uuid"},
        {"event_id": "00000000-0000-0000-0000-000000000000"},
        {"captured_at": "2026-11-11T16:00:00"},
        {"captured_at": 1794412800},
        {"captured_at": "2026-11-11 16:00:00Z"},
        {"emoji_type": "FEAR"},
        {"source": "AI"},
        {"session_id": 99},
        {"user_id": 1},
        {"device_source": "any"},
        {"image": "base64"},
        {"embedding": [1, 2]},
        {"quality": {"landmarks": []}},
        {"quality": {"detection_confidence": True}},
        {"model_version": "https://secret"},
        {"mapping_version": "unknown"},
        {"model_version": "x" * 65},
    ],
)
def test_reject_invalid_or_private_fields(changes):
    with pytest.raises(ValidationError):
        AIIngestEvent.model_validate(event_payload(**changes))


def test_utc_beijing_cross_day_and_explicit_timestamp():
    event = AIIngestEvent.model_validate(event_payload())
    assert event.captured_at == datetime(2026, 11, 11, 16, 0, 0, 123000, tzinfo=timezone.utc)
    assert business_timestamp(event) == datetime(2026, 11, 12, 0, 0, 0, 123000)
    assert business_timestamp(event).tzinfo is None


def test_hash_is_stable_for_timezone_key_order_uuid_case_and_null_optional():
    original = event_payload()
    retry = {
        **original,
        "captured_at": "2026-11-12T00:00:00.123+08:00",
        "event_id": original["event_id"].upper(),
    }
    first = AIIngestEvent.model_validate(original)
    second = AIIngestEvent.model_validate(dict(reversed(list(retry.items()))))
    assert event_payload_hash(first) == event_payload_hash(second)
    assert event_payload_hash(first) != event_payload_hash(first.model_copy(update={"confidence": 0.92}))
    missing = AIIngestEvent.model_validate(event_payload(quality={}))
    null = AIIngestEvent.model_validate(event_payload(quality={"detection_confidence": None}))
    assert event_payload_hash(missing) == event_payload_hash(null)


def test_capture_window_inclusive_start_exclusive_end_and_late_boundary():
    start = datetime(2026, 11, 12, 0)
    end = start + timedelta(hours=1)
    now = datetime(2026, 11, 11, 16, 15, tzinfo=timezone.utc)
    at_start = AIIngestEvent.model_validate(event_payload(captured_at="2026-11-11T16:00:00Z"))
    assert validate_capture_time(at_start, session_start=start, session_end=end, now=now) == start
    for captured in ["2026-11-11T15:59:59Z", "2026-11-11T17:00:00Z", "2026-11-11T16:15:31Z"]:
        event = AIIngestEvent.model_validate(event_payload(captured_at=captured))
        with pytest.raises(ValueError):
            validate_capture_time(event, session_start=start, session_end=end, now=now)
    with pytest.raises(ValueError, match="retry window"):
        validate_capture_time(at_start, session_start=start, session_end=end, now=now + timedelta(microseconds=1))
    with pytest.raises(ValueError, match="timezone-aware"):
        validate_capture_time(at_start, session_start=start, session_end=end, now=now.replace(tzinfo=None))


def test_batch_is_bounded_and_has_no_raw_fields():
    for count in (1, 50):
        batch = AIResultBatch.model_validate({"events": [event_payload(event_id=str(uuid4())) for _ in range(count)]})
        assert len(batch.events) == count
    for payload in ({"events": []}, {"events": [event_payload()] * 51}, {"events": [event_payload()], "video": "raw"}):
        with pytest.raises(ValidationError):
            AIResultBatch.model_validate(payload)
