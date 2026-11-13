import time
from datetime import datetime, timedelta, timezone

import numpy as np

from emoji_ai.capture import Capture
from emoji_ai.mapping import Decision
from emoji_ai.adapters import Observation
from emoji_ai.worker import Worker
from emoji_ai.publisher import Fenced


def test_file_eof_release_and_memory_only():
    class Video:
        released = False
        reads = 0

        def isOpened(self):
            return True

        def read(self):
            self.reads += 1
            return (True, np.zeros((10, 10, 3), dtype=np.uint8)) if self.reads == 1 else (False, None)

        def release(self):
            self.released = True

    video = Video()
    capture = Capture({"kind": "file", "value": "local"}, factory=lambda *args: video).open()
    assert capture.sample().shape == (10, 10, 3)
    assert capture.sample() is None and capture.eof
    capture.close()
    assert video.released


def test_competing_worker_fences_and_releases_input(tmp_path):
    class API:
        def heartbeat(self, data):
            raise Fenced()
    class Camera:
        closed = False
        def close(self):
            self.closed = True
    worker = Worker({"outbox_path": str(tmp_path/"box.sqlite3")}, "unused", api=API())
    camera = worker.capture = Camera()
    worker.job = {"desired": "running"}
    worker.lease_deadline = time.monotonic() + 40
    worker.tick()
    assert camera.closed and worker.job is None and worker.capture is None
    worker.outbox.close()


def test_worker_pauses_and_enqueues_only_under_lease(tmp_path):
    job = {
        "id": 1,
        "profile": "edge",
        "desired": "running",
        "generation": 2,
        "lease_id": "e573b86d-1d5b-44f0-915b-38d58c1cb5a9",
        "lease_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=45)).isoformat(),
        "source_alias": "camera",
        "threshold": 0.7,
        "detection_threshold": 0.85,
        "sample_interval": 0.5,
        "max_faces": 10,
        "model_version": "test",
        "mapping_version": "five-emotions-v1",
        "config_revision": 1,
    }

    class Response:
        status_code = 200

        def json(self):
            return {"data": []}

    class API:
        acks = []

        def heartbeat(self, data):
            return {"server_time": datetime.now(timezone.utc).isoformat(), "jobs": [job]}

        def ack(self, job_id, data):
            self.acks.append(data)
            return Response()

        def call(self, *args):
            return Response()

        def close(self):
            pass

    class Camera:
        eof = failed = False
        closed = False

        def __init__(self, *args):
            pass

        def open(self):
            return self

        def sample(self):
            return np.zeros((10, 10, 3), dtype=np.uint8)

        def close(self):
            self.closed = True

    class Adapter:
        def analyze(self, frame):
            return [Observation(Decision("HAPPY", 0.9, "happy", "accepted"), 0.95, "accepted")]

    config = {
        "outbox_path": str(tmp_path / "outbox.sqlite3"),
        "sources": {"camera": {"kind": "file", "value": "local"}},
    }
    worker = Worker(config, "unused", api=API(), adapter_factory=lambda job: Adapter(), capture_factory=Camera)
    worker.profiles = ["edge"]
    worker.next_publish = time.monotonic() + 60
    worker.tick()
    assert worker.outbox.stats()["queue_size"] == 1
    camera = worker.capture
    job["desired"], job["generation"], job["lease_id"] = "paused", 3, None
    worker.next_heartbeat = 0
    worker.tick()
    assert camera.closed and worker.capture is None
    assert worker.metrics["sampled"] == 1
    acks = len(worker.api.acks)
    for _ in range(20):
        worker.tick()
    assert len(worker.api.acks) == acks  # paused node does not hammer HTTP.
    job["desired"] = "running"
    worker.disconnected = True
    worker.lease_deadline = 0
    worker.tick()
    assert worker.capture is None and worker.metrics["sampled"] == 1
    worker.outbox.close()
