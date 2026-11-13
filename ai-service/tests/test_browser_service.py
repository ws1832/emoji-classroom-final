import threading
import struct
from http.client import HTTPConnection
from types import SimpleNamespace
from uuid import uuid4

import cv2
import numpy as np
import pytest
import requests

from emoji_ai.adapters import Observation
from emoji_ai.browser_service import (
    BoundedHTTPServer,
    BrowserEngine,
    decode_frame,
    handler_factory,
    jpeg_dimensions,
    observation_reason,
)
from emoji_ai.mapping import Decision
from emoji_ai.outbox import Outbox
from emoji_ai.publisher import APIClient, CredentialRejected


def jpeg():
    return cv2.imencode(".jpg", np.zeros((480, 640, 3), np.uint8))[1].tobytes()


def observation(confidence=0.95):
    return Observation(Decision("HAPPY", confidence, "happy", "accepted"), 0.99, "accepted")


def test_size_checked_before_decode(monkeypatch):
    assert jpeg_dimensions(jpeg()) == (640, 480)
    assert decode_frame(jpeg()).shape == (480, 640, 3)
    huge = cv2.imencode(".jpg", np.zeros((721, 1280, 3), np.uint8))[1].tobytes()
    monkeypatch.setattr(cv2, "imdecode", lambda *_: pytest.fail("must not decode oversized image"))
    for data in [huge, b"not jpeg", b"\xff\xd8\xff\xc0\x00\x00"]:
        with pytest.raises(ValueError):
            decode_frame(data)


def test_single_person_gate_before_quality_filter():
    assert observation_reason([], 0.7, 0.85) == "no_face"
    assert observation_reason([observation(), Observation(None, 0.95, "too_small")], 0.7, 0.85) == "multi_face"
    assert observation_reason([observation(0.4)], 0.7, 0.85) == "filtered"
    assert observation_reason([observation()], 0.7, 0.85) == "ready"


def test_multiple_frame_headers_rejected_before_native_decode(monkeypatch):
    data = jpeg()
    offset = data.index(b"\xff\xc0")
    length = struct.unpack_from(">H", data, offset + 2)[0] + 2
    duplicated = data[:offset] + data[offset : offset + length] + data[offset:]
    monkeypatch.setattr(cv2, "imdecode", lambda *_: pytest.fail("must reject before native decode"))
    with pytest.raises(ValueError, match="Multiple"):
        decode_frame(duplicated)


def test_capture_scope_rejection_does_not_revoke_service(monkeypatch):
    api = APIClient("http://localhost:9999/api/v1", "unused")
    monkeypatch.setattr(api.session, "post", lambda *_args, **_kwargs: Response({}, 403))
    try:
        assert api.call("/ai/browser/worker/claim", {}).status_code == 403
        assert api.call("/ai/browser/worker/outcomes", {}).status_code == 403
        with pytest.raises(CredentialRejected):
            api.call("/ai/worker/heartbeat", {})
        monkeypatch.setattr(api.session, "post", lambda *_args, **_kwargs: Response({}, 401))
        with pytest.raises(CredentialRejected):
            api.call("/ai/browser/worker/claim", {})
    finally:
        api.close()


class Response:
    def __init__(self, data, code=200):
        self.status_code, self.data = code, data

    def json(self):
        return {"data": self.data}


class API:
    def __init__(self, ticket):
        self.ticket, self.calls = ticket, []

    def call(self, path, data):
        self.calls.append((path, data))
        if path.endswith("/claim"):
            return Response(self.ticket)
        if path.endswith("/outcomes"):
            return Response({"reason": data["reason"]})
        return Response({"decision": "accepted"})


def ticket():
    return {
        "duplicate": False,
        "event_id": str(uuid4()),
        "job_id": 1,
        "generation": 1,
        "lease_id": str(uuid4()),
        "captured_at": "2026-11-13T03:00:00Z",
        "model_version": "opencv-zoo-mobilefacenet-2022july-fp32",
        "config_revision": 1,
        "mapping_version": "five-emotions-v1",
        "profile": "edge",
        "threshold": 0.7,
        "detection_threshold": 0.85,
    }


@pytest.mark.parametrize(
    "observations,expected",
    [
        ([], "no_face"),
        ([observation()], "accepted"),
        ([observation(), observation()], "multi_face"),
        ([observation(0.3)], "filtered"),
    ],
)
def test_process_only_anonymous_metadata(tmp_path, observations, expected):
    t = ticket()
    api = API(t)
    adapter = SimpleNamespace(model_version=t["model_version"], analyze=lambda _: observations)
    engine = BrowserEngine({"profile": "edge"}, "unused", api=api, adapter=adapter)
    outbox = Outbox(tmp_path / "outbox.sqlite3")
    try:
        result = engine.process(jpeg(), "short-lived", t["event_id"], outbox)
        assert result["status"] == expected
        results = [data for path, data in api.calls if path == "/ai/emoji-results"]
        assert len(results) == (1 if expected == "accepted" else 0)
        assert all("user_id" not in row and "capture_token" not in row for row in results)
        assert "short-lived" not in (tmp_path / "outbox.sqlite3").read_bytes().decode("latin1")
        assert outbox.stats()["queue_size"] == 0
    finally:
        outbox.close()


def test_http_rejects_origins_auth_size_and_format_without_inference():
    engine = BrowserEngine({}, "unused")
    server = BoundedHTTPServer(("127.0.0.1", 0), handler_factory(engine, {"https://classroom.test"}))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    headers = {
        "Origin": "https://classroom.test",
        "Authorization": "Bearer bcc_" + "a" * 32 + "." + "b" * 43,
        "Content-Type": "image/jpeg",
        "X-Frame-ID": str(uuid4()),
    }
    try:
        for change, data, code in [
            ({"Origin": "https://other.test"}, b"x", 403),
            ({"Authorization": "Bearer user-jwt"}, b"x", 401),
            ({"Content-Type": "image/png"}, b"x", 415),
            ({}, b"x", 503),
        ]:
            r = requests.post(base + "/frames", headers={**headers, **change}, data=data, timeout=3)
            assert r.status_code == code
            assert headers["Authorization"] not in r.text
        # 只发送超限声明，不发送正文：验证解析前拒绝，避免 Windows 上
        # 客户端正在上传超大正文而服务提前关闭连接造成 TCP reset 竞态。
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            connection.putrequest("POST", "/frames")
            for key, value in {**headers, "Content-Length": str(256 * 1024 + 1)}.items():
                connection.putheader(key, value)
            connection.endheaders()
            response = connection.getresponse()
            assert response.status == 413
            assert headers["Authorization"].encode() not in response.read()
        finally:
            connection.close()
        r = requests.options(base + "/frames", headers=headers, timeout=3)
        assert r.status_code == 204
        assert r.headers["Access-Control-Allow-Origin"] == "https://classroom.test"
        assert "Access-Control-Allow-Credentials" not in r.headers
        assert engine.frames.empty()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
