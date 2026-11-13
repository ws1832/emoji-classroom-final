"""学生网页单帧推理服务；不打开摄像头，不存储原始画面。

模型和元数据 outbox 由唯一工作线程拥有。HTTP线程只持有有界内存帧，
过载立即503；后台控制/重试不受慢客户端上传阻塞。
"""

import argparse
import hashlib
import json
import logging
import os
import queue
import re
import signal
import struct
import threading
import time
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID, uuid4

import cv2
import numpy as np

from .adapters import DeepFaceAdapter, LightweightAdapter
from .outbox import Outbox, OutboxFull
from .publisher import APIClient, BackendUnavailable, CredentialRejected, Fenced, Publisher

log = logging.getLogger("emoji_ai.browser")
MAX_BODY = 256 * 1024
CAP_TOKEN = re.compile(r"Bearer (bcc_[a-f0-9]{32}\.[A-Za-z0-9_-]{43})\Z")


class BoundedHTTPServer(ThreadingHTTPServer):
    """连HTTP解析线程也有界；慢headers不能无限占用线程或内存。"""

    def __init__(self, *args, **kwargs):
        self.connections = threading.BoundedSemaphore(16)
        super().__init__(*args, **kwargs)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(5)
        return request, address

    def process_request(self, request, address):
        if not self.connections.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.connections.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.connections.release()


class FrameRejected(Exception):
    def __init__(self, code, reason):
        self.code, self.reason = code, reason


def jpeg_dimensions(data):
    """解析SOF尺寸后才允许imdecode，拒绝超限/非JPEG/损坏头。"""
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("JPEG required")
    offset = 2
    dimensions = None
    while offset < len(data):
        if data[offset] != 0xFF:
            raise ValueError("Invalid JPEG header")
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker == 0xDA:
            if dimensions is None:
                break
            return dimensions
        if marker in (0xD8, 0xD9, 0x00, 0xDC) or 0xD0 <= marker <= 0xD7:
            break
        if offset + 2 > len(data):
            break
        length = struct.unpack_from(">H", data, offset)[0]
        if length < 2 or offset + length > len(data):
            break
        if marker in (0xC0, 0xC1, 0xC2):
            if dimensions is not None:
                raise ValueError("Multiple JPEG frame headers")
            if length < 8:
                break
            height, width = struct.unpack_from(">HH", data, offset + 3)
            if not (1 <= width <= 1280 and 1 <= height <= 720 and width * height <= 921600):
                raise ValueError("Image dimensions exceed limit")
            dimensions = (width, height)
        elif 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            raise ValueError("Unsupported JPEG frame header")
        offset += length
    raise ValueError("Invalid JPEG dimensions")


def decode_frame(data):
    width, height = jpeg_dimensions(data)
    frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    if frame is None or frame.shape[:2] != (height, width):
        raise ValueError("JPEG decode failed")
    return frame


def observation_reason(observations, threshold, detection_threshold):
    # 判多人在任何质量/表情过滤之前，不能把第二张小脸过滤后当单人。
    if not observations:
        return "no_face"
    if len(observations) != 1:
        return "multi_face"
    row = observations[0]
    if (
        not row.decision
        or not row.decision.emoji_type
        or row.decision.confidence < threshold
        or row.detection_confidence is None
        or row.detection_confidence < detection_threshold
    ):
        return "filtered"
    return "ready"


class BrowserEngine:
    def __init__(self, config, token, *, api=None, adapter=None):
        self.config, self.token = config, token
        self.api, self.adapter = api, adapter
        self.incarnation = str(uuid4())
        self.frames = queue.Queue(maxsize=1)
        self.admission = threading.BoundedSemaphore(config.get("capacity", 4))
        self.stopping, self.ready = threading.Event(), threading.Event()
        self.health = "waiting"
        self.thread = threading.Thread(target=self.run, name="browser-inference", daemon=True)

    def start(self):
        self.thread.start()

    def submit(self, data, token, event_id):
        if not self.ready.is_set():
            raise FrameRejected(503, "service_unavailable")
        future = Future()
        try:
            self.frames.put_nowait((data, token, event_id, future))
        except queue.Full:
            raise FrameRejected(503, "busy") from None
        return future

    def run(self):
        self.api = self.api or APIClient(self.config["backend_url"], self.token)
        outbox = None
        try:
            profile = self.config.get("profile", "edge")
            if self.adapter is None:
                factory = LightweightAdapter if profile == "edge" else DeepFaceAdapter
                self.adapter = factory(
                    manifest=Path(self.config["manifest"]),
                    model_dir=Path(self.config["model_dir"]),
                    threshold=0.0,
                    detection_threshold=0.85,
                )
            self.adapter.analyze(np.zeros((480, 640, 3), dtype=np.uint8))
            outbox = Outbox(Path(self.config["outbox_path"]), ttl=60)
            publisher = Publisher(self.api, outbox)
            next_beat = next_publish = 0
            self.health = "ready"
            while not self.stopping.is_set():
                now = time.monotonic()
                if now >= next_beat:
                    next_beat = now + 5
                    try:
                        self.api.heartbeat(
                            {"incarnation": self.incarnation, "profiles": [profile], "health": self.health}
                        )
                        self.ready.set()
                        self.health = "ready"
                    except (BackendUnavailable, Fenced):
                        self.ready.clear()
                        self.health = "degraded"
                        log.error("heartbeat_unavailable")
                if now >= next_publish:
                    next_publish = now + 1
                    publisher.flush()
                try:
                    data, token, event_id, future = self.frames.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    if not self.ready.is_set():
                        raise FrameRejected(503, "service_unavailable")
                    result = self.process(data, token, event_id, outbox)
                    future.set_result(result)
                except FrameRejected as exc:
                    future.set_exception(exc)
                except BackendUnavailable:
                    future.set_exception(FrameRejected(503, "backend_unavailable"))
                except CredentialRejected:
                    future.set_exception(FrameRejected(503, "service_unavailable"))
                    raise
                except Exception:
                    log.error("frame_processing_failed")
                    future.set_exception(FrameRejected(503, "processing_failed"))
                finally:
                    del data, token
                    self.frames.task_done()
        except CredentialRejected:
            log.error("service_credential_rejected")
        except Exception:
            self.health = "model_failed"
            log.error("service_initialization_failed")
        finally:
            self.ready.clear()
            self.stopping.set()
            while not self.frames.empty():
                _, _, _, pending = self.frames.get_nowait()
                pending.set_exception(FrameRejected(503, "service_unavailable"))
            if outbox:
                outbox.close()
            self.api.close()

    def process(self, data, token, event_id, outbox):
        response = self.api.call(
            "/ai/browser/worker/claim",
            {
                "capture_token": token,
                "event_id": event_id,
                "payload_hash": hashlib.sha256(data).hexdigest(),
                "incarnation": self.incarnation,
            },
        )
        if response.status_code != 200:
            raise FrameRejected(response.status_code, "capture_rejected")
        ticket = response.json()["data"]
        if ticket["duplicate"]:
            return {"status": ticket["reason"], "duplicate": True, "state": ticket["state"]}
        if (
            ticket["profile"] != self.config.get("profile", "edge")
            or ticket["model_version"] != self.adapter.model_version
        ):
            raise FrameRejected(409, "model_snapshot_mismatch")
        started = time.perf_counter()
        observations = []
        try:
            frame = decode_frame(data)
        except ValueError:
            reason = "invalid_image"
        else:
            try:
                observations = self.adapter.analyze(frame)
                reason = observation_reason(observations, ticket["threshold"], ticket["detection_threshold"])
            except Exception:
                reason = "model_failed"
                log.error("model_inference_failed")
            finally:
                del frame
        inference_ms = (time.perf_counter() - started) * 1000
        response = self.api.call(
            "/ai/browser/worker/outcomes",
            {
                "event_id": event_id,
                "reason": reason,
                "faces": len(observations),
                "inference_ms": inference_ms,
            },
        )
        if response.status_code != 200:
            raise FrameRejected(response.status_code, "capture_rejected")
        if reason != "ready":
            return {"status": reason}
        row = observations[0]
        event = {
            k: ticket[k]
            for k in (
                "event_id",
                "job_id",
                "generation",
                "lease_id",
                "captured_at",
                "model_version",
                "config_revision",
                "mapping_version",
            )
        }
        event.update(
            contract_version=1,
            emoji_type=row.decision.emoji_type,
            confidence=row.decision.confidence,
            quality={"detection_confidence": row.detection_confidence},
        )
        try:
            outbox.enqueue(event)
        except OutboxFull:
            raise FrameRejected(503, "metadata_queue_full") from None
        # enqueue之前不落盘任何票据token。已产生的严格匿名结果允许短期重试。
        try:
            result = self.api.call("/ai/emoji-results", event)
        except BackendUnavailable:
            return {"status": "queued"}
        if result.status_code != 200:
            if result.status_code == 429 or result.status_code >= 500:
                return {"status": "queued"}
            outbox.ack(event_id, dropped=True)
            raise FrameRejected(result.status_code, "result_rejected")
        decision = result.json()["data"]
        outbox.ack(event_id)
        return {"status": decision["decision"]}

    def close(self):
        self.ready.clear()
        self.stopping.set()
        self.thread.join(timeout=30)


def handler_factory(engine, allowed_origins):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass  # 禁止记录路径、headers、token、raw body。

        def reply(self, code, data):
            body = json.dumps(data, ensure_ascii=True).encode()
            self.send_response(code)
            origin = self.headers.get("Origin")
            if origin in allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            if code in (429, 503):
                self.send_header("Retry-After", "5")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def origin_ok(self):
            return self.headers.get("Origin") in allowed_origins

        def do_OPTIONS(self):
            if self.path != "/frames" or not self.origin_ok():
                return self.reply(403, {"status": "origin_rejected"})
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "POST")
            self.send_header("Access-Control-Allow-Headers", "Authorization,Content-Type,X-Frame-ID")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if self.path != "/healthz":
                return self.reply(404, {"status": "not_found"})
            self.reply(200 if engine.ready.is_set() else 503, {"ready": engine.ready.is_set(), "health": engine.health})

        def do_POST(self):
            try:
                if self.path != "/frames":
                    raise FrameRejected(404, "not_found")
                if not self.origin_ok():
                    raise FrameRejected(403, "origin_rejected")
                match = CAP_TOKEN.fullmatch(self.headers.get("Authorization", ""))
                if not match:
                    raise FrameRejected(401, "capture_authorization_required")
                identifier = self.headers.get("X-Frame-ID", "")
                try:
                    parsed = UUID(identifier)
                    if parsed.version != 4 or str(parsed) != identifier:
                        raise ValueError()
                except ValueError:
                    raise FrameRejected(422, "frame_id_required") from None
                if self.headers.get("Content-Type", "").lower() != "image/jpeg":
                    raise FrameRejected(415, "jpeg_required")
                lengths = self.headers.get_all("Content-Length", [])
                if self.headers.get("Transfer-Encoding") or len(lengths) != 1 or not lengths[0].isdigit():
                    raise FrameRejected(411, "content_length_required")
                length = int(lengths[0])
                if not 1 <= length <= MAX_BODY:
                    raise FrameRejected(413, "frame_too_large")
                if not engine.admission.acquire(blocking=False):
                    raise FrameRejected(503, "busy")
                try:
                    self.connection.settimeout(5)
                    data = self.rfile.read(length)
                    if len(data) != length:
                        raise FrameRejected(400, "incomplete_frame")
                    result = engine.submit(data, match.group(1), identifier).result(timeout=25)
                    del data
                finally:
                    engine.admission.release()
                self.reply(200, result)
            except FrameRejected as exc:
                self.reply(exc.code, {"status": exc.reason})
            except (TimeoutError, OSError):
                self.close_connection = True
            except Exception:
                self.reply(503, {"status": "service_unavailable"})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    if type(config.get("capacity", 4)) is not int or not 1 <= config.get("capacity", 4) <= 16:
        parser.error("capacity must be an integer in [1,16]")
    token = os.environ.get("AI_DEVICE_TOKEN")
    if not token and config.get("token_file"):
        token = Path(config["token_file"]).read_text(encoding="utf-8-sig").strip()
    if not token or not config.get("allowed_origins") or "*" in config["allowed_origins"]:
        parser.error("Provide private token_file/AI_DEVICE_TOKEN and explicit allowed_origins")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = BrowserEngine(config, token)
    server = BoundedHTTPServer(
        (config.get("host", "127.0.0.1"), config.get("port", 9998)),
        handler_factory(engine, set(config["allowed_origins"])),
    )

    # 监听线程仅用于shutdown；工作模型/outbox从不跨线程访问。
    def shutdown(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    engine.start()
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        engine.close()


if __name__ == "__main__":
    main()
