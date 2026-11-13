"""真实课堂节点：preflight→lease→capture→outbox→后端，无 raw 落盘。"""

import argparse
import json
import logging
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .adapters import DeepFaceAdapter, LightweightAdapter
from .capture import Capture
from .outbox import Outbox, OutboxFull
from .publisher import APIClient, BackendUnavailable, CredentialRejected, Fenced, Publisher

log = logging.getLogger("emoji_ai")


def event_from_observation(job, observation, captured_at):
    return {
        "contract_version": 1,
        "event_id": str(uuid4()),
        "job_id": job["id"],
        "generation": job["generation"],
        "lease_id": job["lease_id"],
        "captured_at": captured_at,
        "emoji_type": observation.decision.emoji_type,
        "confidence": observation.decision.confidence,
        "model_version": job["model_version"],
        "config_revision": job["config_revision"],
        "mapping_version": job["mapping_version"],
        "quality": {"detection_confidence": observation.detection_confidence},
    }


class Worker:
    def __init__(self, config, token, *, api=None, adapter_factory=None, capture_factory=Capture):
        self.config = config
        self.api = api or APIClient(config["backend_url"], token)
        self.outbox = Outbox(Path(config["outbox_path"]))
        self.publisher = Publisher(self.api, self.outbox)
        self.incarnation = str(uuid4())
        self.capture_factory = capture_factory
        self.adapter_factory = adapter_factory or self._adapter
        self.capture, self.adapter, self.job = None, None, None
        self.prepared = None
        self.profiles = []
        self.health = "waiting"
        self.metrics = {"sampled": 0, "no_face": 0, "filtered": 0, "published": 0, "inference_ms": 0.0}
        self.stop = False
        self.next_sample = self.next_heartbeat = self.next_publish = 0
        self.lease_deadline = 0
        self.disconnected = False
        self.reconnect_attempts = 0
        self.next_status = 0
        self.next_reconnect = 0
        self.ack_key = None
        self.first_frame = None
        self.preflight_deadline = 0
        self.failed_key = None

    def _adapter(self, job):
        factory = DeepFaceAdapter if job["profile"] == "standard" else LightweightAdapter
        return factory(
            manifest=Path(self.config["manifest"]),
            model_dir=Path(self.config["model_dir"]),
            threshold=job["threshold"],
            detection_threshold=job["detection_threshold"],
        )

    def prepare_profiles(self):
        # 一个进程显式选一个 profile，避免 DeepFace 全局缓存跨配置/线程变化。
        profile = self.config.get("profile", "edge")
        try:
            adapter = self._adapter({"profile": profile, "threshold": 0.7, "detection_threshold": 0.85})
            # 实际预热推理，不仅解析权重；空帧不会生成业务观测。
            import numpy as np

            adapter.analyze(np.zeros((480, 640, 3), dtype=np.uint8))
            del adapter
            self.profiles = [profile]
            self.health = "ready"
        except Exception:
            self.profiles = []
            self.health = "model_failed"
            log.error("model_preparation_failed profile=%s", profile)

    def _release(self):
        if self.capture:
            self.capture.close()
        self.capture = None
        self.prepared = None
        self.first_frame = None

    def _ack(self, state, health):
        if not self.job:
            return
        key = (self.job["id"], self.job["generation"], state, health)
        now = time.monotonic()
        if key == self.ack_key and now < self.next_status:
            return
        stats = self.outbox.stats()
        self.api.ack(
            self.job["id"],
            {
                "incarnation": self.incarnation,
                "generation": self.job["generation"],
                "lease_id": self.job.get("lease_id"),
                "observed": state,
                "health": health,
                "metrics": {**self.metrics, "queue_size": stats["queue_size"], "dropped": stats["dropped"]},
            },
        )
        self.ack_key, self.next_status = key, now + 5
        if state == "failed":
            self.failed_key = (self.job["id"], self.job["generation"])

    def tick(self):
        try:
            self._tick()
        except Fenced:
            self._release()
            self.job, self.lease_deadline = None, 0
            self.next_heartbeat = time.monotonic() + 5
            self.health = "waiting"
            log.error("worker_fenced")
        except BackendUnavailable:
            self.disconnected = True
            self.health = "buffering"
            log.error("control_unavailable")

    def _tick(self):
        now = time.monotonic()
        if self.job and self.job["desired"] == "running" and now >= self.lease_deadline:
            self._release()
            self.health = "degraded"
        if now >= self.next_heartbeat:
            self.next_heartbeat = now + 5
            try:
                response = self.api.heartbeat(
                    {"incarnation": self.incarnation, "profiles": self.profiles, "health": self.health}
                )
                now = time.monotonic()  # 网络等待不能延长服务端授予的租约。
                server = datetime.fromisoformat(response["server_time"].replace("Z", "+00:00"))
                if abs((datetime.now(timezone.utc) - server).total_seconds()) > 30:
                    self._release()
                    self.health = "degraded"
                    log.error("clock_skew_exceeded")
                    return
                job = next(iter(response["jobs"]), None)
                self.disconnected = False
                if not job:
                    self._release()
                    self.job = None
                else:
                    old = self.job
                    self.job = job
                    if job["desired"] == "running":
                        expires = datetime.fromisoformat(job["lease_expires_at"].replace("Z", "+00:00"))
                        self.lease_deadline = now + max(0, (expires - datetime.now(timezone.utc)).total_seconds() - 1)
                    if not old or old["id"] != job["id"] or old["generation"] != job["generation"]:
                        self._release()
            except BackendUnavailable:
                self.disconnected = True
                self.health = "buffering"
                log.error("heartbeat_unavailable")
        job = self.job
        if job:
            if job["desired"] in ("paused", "stopped"):
                self._release()
                self.health = "waiting"
                if not self.disconnected:
                    self._ack(job["desired"], "waiting")
            elif job["desired"] in ("ready", "running") and self.failed_key != (job["id"], job["generation"]):
                if (
                    not self.capture
                    and now >= self.next_reconnect
                    and (job["desired"] != "running" or now < self.lease_deadline)
                ):
                    try:
                        if job["profile"] not in self.profiles:
                            raise RuntimeError("Profile not prepared")
                        self.adapter = self.adapter_factory(job)
                        self.capture = self.capture_factory(self.config["sources"][job["source_alias"]]).open()
                        self.preflight_deadline = time.monotonic() + 5
                        self.reconnect_attempts = 0
                        self.health = "ready"
                    except (CredentialRejected, Fenced, BackendUnavailable):
                        raise
                    except Exception:
                        self._release()
                        self.reconnect_attempts += 1
                        self.next_reconnect = now + min(30, 2 ** min(self.reconnect_attempts, 5))
                        self.health = "no_frame"
                        log.error("capture_preflight_failed job_id=%s", job["id"])
                        if self.reconnect_attempts >= 5 and not self.disconnected:
                            self._ack("failed", "no_frame")
                if self.capture and self.prepared is None:
                    self.first_frame = self.capture.sample()
                    if self.first_frame is not None:
                        self.prepared = True
                        if not self.disconnected:
                            self._ack(job["desired"], "ready")
                    elif self.capture.failed or self.capture.eof or time.monotonic() >= self.preflight_deadline:
                        self._release()
                        self.health = "no_frame"
                        if not self.disconnected:
                            self._ack("failed", "no_frame")
                now = time.monotonic()
                if (
                    self.capture
                    and self.prepared
                    and job["desired"] == "running"
                    and now < self.lease_deadline
                    and now >= self.next_sample
                ):
                    self.next_sample = now + job["sample_interval"]
                    frame = self.first_frame
                    self.first_frame = None
                    if frame is None:
                        frame = self.capture.sample()
                    if frame is None:
                        if self.capture.eof:
                            self._release()
                            self.health = "waiting"
                            self._ack("failed", "eof")  # finite file is terminal; release its source slot.
                        elif self.capture.failed:
                            self._release()
                            self.health = "no_frame"
                        frame = None
                    if frame is None:
                        if now >= self.next_publish:
                            self.next_publish = now + 1
                            self.metrics["published"] += self.publisher.flush()
                        return
                    captured_at = getattr(self.capture, "captured_at", None) or datetime.now(
                        timezone.utc
                    ).isoformat().replace("+00:00", "Z")
                    if time.monotonic() >= self.lease_deadline:
                        del frame
                        self._release()
                        return
                    started = time.perf_counter()
                    try:
                        observations = self.adapter.analyze(frame)
                        # 长时推理超过租约时不产生新事件，避免失联节点继续写。
                        if time.monotonic() >= self.lease_deadline:
                            return
                        self.metrics["sampled"] += 1
                        self.metrics["inference_ms"] = round((time.perf_counter() - started) * 1000, 3)
                        if not observations:
                            self.metrics["no_face"] += 1
                            self.health = "no_face"
                        else:
                            self.health = "ready"
                        for observation in observations[: job["max_faces"]]:
                            if observation.decision and observation.decision.emoji_type:
                                self.outbox.enqueue(event_from_observation(job, observation, captured_at))
                            else:
                                self.metrics["filtered"] += 1
                    except OutboxFull:
                        self.health = "degraded"
                        log.error("outbox_quota_exceeded job_id=%s", job["id"])
                    except Exception:
                        self._release()
                        self.health = "model_failed"
                        log.error("inference_failed job_id=%s", job["id"])
                        if not self.disconnected:
                            self._ack("failed", "model_failed")
                    finally:
                        del frame
        if now >= self.next_publish:
            self.next_publish = now + 1
            self.metrics["published"] += self.publisher.flush()
        if self.job and not self.disconnected and now >= self.next_status and self.capture:
            if self.outbox.stats()["queue_size"] and self.publisher.last_unavailable:
                self.health = "buffering"
            self._ack(self.job["desired"], self.health)

    def run(self, duration=None):
        started = time.monotonic()
        self.prepare_profiles()
        try:
            while not self.stop and (duration is None or time.monotonic() - started < duration):
                self.tick()
                time.sleep(0.05)
        except CredentialRejected:
            log.error("credential_rejected; capture_stopped")
        finally:
            self._release()
            self.api.close()
            self.outbox.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=None, help="Bounded smoke run in seconds")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    token = os.environ.get("AI_DEVICE_TOKEN")
    if not token and os.environ.get("AI_DEVICE_TOKEN_FILE"):
        token = Path(os.environ["AI_DEVICE_TOKEN_FILE"]).read_text(encoding="utf-8").strip()
    if not token:
        parser.error("Set AI_DEVICE_TOKEN or AI_DEVICE_TOKEN_FILE; never pass a secret on the command line")
    if config.get("profile", "edge") not in ("edge", "standard") or not isinstance(config.get("sources"), dict):
        parser.error("Select edge/standard and a source alias map")
    if args.duration is not None and args.duration <= 0:
        parser.error("Duration must be positive")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    worker = Worker(config, token)
    signal.signal(signal.SIGINT, lambda *args: setattr(worker, "stop", True))
    signal.signal(signal.SIGTERM, lambda *args: setattr(worker, "stop", True))
    worker.run(args.duration)


if __name__ == "__main__":
    main()
