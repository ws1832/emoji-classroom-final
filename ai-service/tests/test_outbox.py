from datetime import datetime, timezone
from uuid import uuid4

import pytest

from emoji_ai.outbox import Outbox, OutboxFull
from emoji_ai.publisher import BackendUnavailable, Publisher


def event():
    return {
        "contract_version": 1,
        "event_id": str(uuid4()),
        "job_id": 1,
        "generation": 2,
        "lease_id": str(uuid4()),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "emoji_type": "HAPPY",
        "confidence": 0.9,
        "model_version": "test",
        "config_revision": 1,
        "mapping_version": "five-emotions-v1",
        "quality": {"detection_confidence": 0.95},
    }


def test_durable_restart_retry_id_and_ack(tmp_path):
    path = tmp_path / "outbox.sqlite3"
    box = Outbox(path)
    payload = event()
    box.enqueue(payload)
    box.close()
    box = Outbox(path)
    assert box.due()[0][1] == payload
    box.enqueue(payload)
    assert box.stats()["queue_size"] == 1
    with pytest.raises(ValueError):
        box.enqueue({**payload, "confidence": 0.8})
    box.retry(payload["event_id"], 60)
    assert box.due() == []
    box.ack(payload["event_id"])
    assert box.stats()["queue_size"] == 0
    box.close()


def test_quota_ttl_and_no_raw_metadata(tmp_path):
    clock = [1000.0]
    box = Outbox(tmp_path / "outbox.sqlite3", max_events=1, ttl=10, clock=lambda: clock[0])
    box.enqueue(event())
    with pytest.raises(OutboxFull):
        box.enqueue(event())
    with pytest.raises(ValueError):
        box.enqueue({**event(), "image": "raw"})
    with pytest.raises(ValueError):
        box.enqueue({**event(), "quality": {"landmarks": []}})
    clock[0] += 11
    assert box.expire() == 1 and box.stats()["dropped"] == 1
    box.close()


def test_publish_uncertain_ack_reuses_same_event(tmp_path):
    clock = [1000.0]
    box = Outbox(tmp_path / "outbox.sqlite3", clock=lambda: clock[0])
    payload = event()
    box.enqueue(payload)

    class Response:
        status_code = 200

        def json(self):
            return {"data": [{"event_id": payload["event_id"], "status": "duplicate", "decision": "accepted"}]}

    class API:
        calls = []

        def call(self, path, data):
            self.calls.append(data)
            if len(self.calls) == 1:
                raise BackendUnavailable()
            return Response()

    api = API()
    publisher = Publisher(api, box, random_source=lambda: 0)
    assert publisher.flush() == 0 and box.stats()["queue_size"] == 1
    clock[0] += 2
    assert publisher.flush() == 1 and box.stats()["queue_size"] == 0
    assert api.calls[0] == api.calls[1]
    box.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"generation": True},
        {"job_id": 0},
        {"contract_version": True},
        {"model_version": "x" * 65},
        {"captured_at": "2026-11-11 12:00:00"},
        {"quality": {"detection_confidence": True}},
        {"confidence": float("nan")},
        {"mapping_version": "anything"},
        {"event_id": uuid4().hex},
    ],
)
def test_outbox_rejects_unbounded_or_invalid_metadata(tmp_path, changes):
    box = Outbox(tmp_path / "box.sqlite3")
    with pytest.raises(ValueError):
        box.enqueue({**event(), **changes})
    assert box.stats()["queue_size"] == 0
    box.close()


def test_churn_checkpoints_and_reuses_storage(tmp_path):
    box = Outbox(tmp_path / "box.sqlite3", max_events=100, max_bytes=100000)
    for _ in range(300):
        payload = event()
        box.enqueue(payload)
        box.ack(payload["event_id"])
    assert box.stats()["queue_size"] == 0
    box.close()
    assert (tmp_path / "box.sqlite3").stat().st_size < 1024 * 1024


def test_malformed_response_retries_instead_of_dropping(tmp_path):
    box = Outbox(tmp_path / "box.sqlite3")
    box.enqueue(event())

    class Response:
        status_code = 200

        def json(self):
            return {"unexpected": True}

    class API:
        def call(self, *args):
            return Response()

    assert Publisher(API(), box).flush() == 0
    assert box.stats()["queue_size"] == 1 and box.due() == []
    box.close()
