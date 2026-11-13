"""有界 HTTP 重试；永久拒绝不无限重传，认证失败立即停止采集。"""

import random
from urllib.parse import urlparse

import requests


class CredentialRejected(RuntimeError):
    pass


class BackendUnavailable(RuntimeError):
    pass


class Fenced(RuntimeError):
    """控制面不再承认本地任务/代际，立即释放采集并重新领取。"""


class APIClient:
    def __init__(self, base_url, token):
        parsed = urlparse(base_url)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1")):
            raise ValueError("Remote backend requires HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Backend URL must not contain credentials/query")
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": "Bearer " + token})

    def call(self, path, data):
        try:
            response = self.session.post(self.base + path, json=data, timeout=(3, 10), allow_redirects=False)
        except requests.RequestException:
            raise BackendUnavailable("Backend connection failed") from None
        # 采集授权跨服务/课堂403只拒绝该帧，不关闭共享推理线程。
        capture_scoped = path in ("/ai/browser/worker/claim", "/ai/browser/worker/outcomes")
        if response.status_code == 401 or (response.status_code == 403 and not capture_scoped):
            raise CredentialRejected("Device authorization rejected")
        if response.status_code == 429 or response.status_code >= 500:
            raise BackendUnavailable("Backend temporarily unavailable")
        return response

    def heartbeat(self, data):
        response = self.call("/ai/worker/heartbeat", data)
        if response.status_code != 200:
            raise Fenced("Heartbeat rejected or competing worker")
        try:
            data = response.json()["data"]
            if not isinstance(data, dict) or not isinstance(data["jobs"], list):
                raise ValueError()
            return data
        except (KeyError, ValueError, TypeError):
            raise BackendUnavailable("Invalid heartbeat response") from None

    def ack(self, job_id, data):
        response = self.call(f"/ai/worker/jobs/{job_id}/ack", data)
        if response.status_code != 200:
            raise Fenced("Acknowledgement fenced")
        return response

    def close(self):
        self.session.close()


class Publisher:
    def __init__(self, api, outbox, random_source=random.random):
        self.api, self.outbox, self.random = api, outbox, random_source
        self.last_unavailable = False

    def flush(self):
        rows = self.outbox.due()
        if not rows:
            return 0
        try:
            response = self.api.call("/ai/emoji-results/batch", {"events": [row[1] for row in rows]})
        except CredentialRejected:
            raise
        except BackendUnavailable:
            self.last_unavailable = True
            for identifier, _, attempts in rows:
                self.outbox.retry(identifier, min(60, 2 ** min(attempts, 6)) + self.random())
            return 0
        if response.status_code != 200:
            for identifier, _, _ in rows:
                self.outbox.ack(identifier, dropped=True)
            return 0
        try:
            results = {row["event_id"]: row for row in response.json()["data"]}
        except (ValueError, KeyError, TypeError):
            for identifier, _, attempts in rows:
                self.outbox.retry(identifier, min(60, 2 ** min(attempts, 6)) + self.random())
            return 0
        self.last_unavailable = False
        published = 0
        for identifier, _, attempts in rows:
            result = results.get(identifier)
            if result and result.get("status") in ("accepted", "duplicate", "filtered"):
                self.outbox.ack(identifier)
                published += result.get("decision") == "accepted"
            elif (
                result and result.get("status") == "rejected" and result.get("code", 0) not in (429, 500, 502, 503, 504)
            ):
                self.outbox.ack(identifier, dropped=True)
            else:
                self.outbox.retry(identifier, min(60, 2 ** min(attempts, 6)) + self.random())
        return published
