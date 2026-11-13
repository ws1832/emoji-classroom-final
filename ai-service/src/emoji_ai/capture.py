"""节点本地 source alias；实时 latest-frame 覆盖，raw 仅内存。"""

import threading
import time
from datetime import datetime, timezone

import cv2


class Capture:
    def __init__(self, source, *, factory=cv2.VideoCapture):
        self.source, self.factory = source, factory
        self.capture = None
        self.thread = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.sequence = 0
        self.consumed = 0
        self.eof = False
        self.failed = False
        self.captured_at = None
        self.latest_at = None

    def open(self):
        kind, value = self.source["kind"], self.source["value"]
        if kind not in ("usb", "file", "rtsp"):
            raise ValueError("Source kind must be usb, file or rtsp")
        if kind == "usb":
            capture = self.factory(int(value))
        else:
            capture = self.factory(
                value,
                cv2.CAP_FFMPEG,
                [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                    3000,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                    3000,
                ],
            )
        if not capture.isOpened():
            capture.release()
            raise RuntimeError("Capture input is unavailable")
        self.capture = capture
        if kind != "file":
            self.thread = threading.Thread(target=self._read_latest, daemon=True)
            self.thread.start()
        return self

    def _read_latest(self):
        while not self.stop_event.is_set():
            ok, frame = self.capture.read()
            if not ok:
                self.failed = True
                break
            with self.lock:
                self.latest = frame
                self.latest_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                self.sequence += 1
            time.sleep(0.001)

    def sample(self):
        if self.source["kind"] == "file":
            ok, frame = self.capture.read()
            if not ok:
                self.eof = True
                return None
            self.captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            return frame
        with self.lock:
            if self.sequence == self.consumed:
                return None
            self.consumed = self.sequence
            self.captured_at = self.latest_at
            return self.latest

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=4)
            if self.thread.is_alive():
                # 不在另一个线程 release 正在 read 的 OpenCV 对象；退出进程而非再开相机。
                raise RuntimeError("Capture read did not stop within timeout")
        if self.capture:
            self.capture.release()
        with self.lock:
            self.latest = None
