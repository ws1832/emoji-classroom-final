"""有界、仅严格 JSON 元数据的 durable outbox；先 enqueue 再 HTTP publish。"""

import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID

from .mapping import EMOJIS, finite_score

_FIELDS = {
    "contract_version",
    "event_id",
    "job_id",
    "generation",
    "lease_id",
    "captured_at",
    "emoji_type",
    "confidence",
    "model_version",
    "config_revision",
    "mapping_version",
    "quality",
}


def safe_event(event):
    if (
        not isinstance(event, dict)
        or set(event) != _FIELDS
        or type(event["contract_version"]) is not int
        or event["contract_version"] != 1
    ):
        raise ValueError("Outbox accepts only v1 event metadata")
    for key in ("event_id", "lease_id"):
        if (
            not isinstance(event[key], str)
            or str(UUID(event[key])) != event[key].lower()
            or UUID(event[key]).version != 4
        ):
            raise ValueError("Canonical event/lease UUID v4 required")
    for key in ("job_id", "generation", "config_revision"):
        if type(event[key]) is not int or event[key] < 1:
            raise ValueError("Positive integer required")
    if not isinstance(event["model_version"], str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", event["model_version"]
    ):
        raise ValueError("Invalid model snapshot")
    if event["mapping_version"] != "five-emotions-v1":
        raise ValueError("Invalid mapping snapshot")
    stamp = event["captured_at"]
    if not isinstance(stamp, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", stamp
    ):
        raise ValueError("RFC3339 capture time required")
    datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if (
        not isinstance(event["emoji_type"], str)
        or event["emoji_type"] not in EMOJIS
        or not 0 <= finite_score(event["confidence"]) <= 1
    ):
        raise ValueError("Invalid emotion observation")
    if not isinstance(event["quality"], dict) or set(event["quality"]) - {"detection_confidence"}:
        raise ValueError("Private quality data prohibited")
    detection = event["quality"].get("detection_confidence")
    if detection is not None and not 0 <= finite_score(detection) <= 1:
        raise ValueError("Invalid detector score")
    return json.dumps(event, separators=(",", ":"), sort_keys=True, allow_nan=False)


class OutboxFull(RuntimeError):
    pass


class Outbox:
    def __init__(self, path: Path, *, max_events=5000, max_bytes=50 * 1024 * 1024, ttl=900, clock=time.time):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.clock, self.max_events, self.max_bytes, self.ttl = clock, max_events, max_bytes, ttl
        self.db = sqlite3.connect(path)
        # 限制主文件页数；WAL 周期 checkpoint，不因持续 enqueue/delete 无限膨胀。
        self.db.execute("PRAGMA auto_vacuum=INCREMENTAL")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA journal_size_limit=131072")
        self.db.execute(f"PRAGMA max_page_count={max(64, (max_bytes + 1024 * 1024) // 4096)}")
        self.mutations = 0
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created REAL NOT NULL,
            retry_at REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0)"""
        )
        self.db.execute("CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, count INTEGER NOT NULL)")
        self.db.commit()

    def _count_drop(self, count):
        self.db.execute(
            "INSERT INTO counters VALUES ('dropped',?) ON CONFLICT(name) DO UPDATE SET count=count+excluded.count",
            (count,),
        )

    def expire(self):
        with self.db:
            deleted = self.db.execute("DELETE FROM events WHERE created < ?", (self.clock() - self.ttl,)).rowcount
            self._count_drop(deleted)
        return deleted

    def _maintain(self):
        self.mutations += 1
        if self.mutations >= 50:
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.db.execute("PRAGMA incremental_vacuum(128)")
            self.mutations = 0

    def enqueue(self, event):
        payload = safe_event(event)
        self.expire()
        with self.db:
            old = self.db.execute("SELECT payload FROM events WHERE event_id=?", (event["event_id"],)).fetchone()
            if old:
                if old[0] != payload:
                    raise ValueError("Outbox event ID conflict")
                return
            count, size = self.db.execute("SELECT count(*),coalesce(sum(length(payload)),0) FROM events").fetchone()
            if count >= self.max_events or size + len(payload) > self.max_bytes:
                raise OutboxFull("Outbox quota exceeded; capture must degrade")
            self.db.execute(
                "INSERT INTO events(event_id,payload,created,retry_at) VALUES (?,?,?,?)",
                (event["event_id"], payload, self.clock(), self.clock()),
            )
        self._maintain()

    def due(self, limit=50):
        self.expire()
        # 优先新鲜结果，补交有界，不让旧 backlog 饿死实时观测。
        return [
            (identifier, json.loads(payload), attempts)
            for identifier, payload, attempts in self.db.execute(
                "SELECT event_id,payload,attempts FROM events WHERE retry_at<=? ORDER BY created DESC LIMIT ?",
                (self.clock(), min(limit, 50)),
            )
        ]

    def ack(self, identifier, *, dropped=False):
        with self.db:
            count = self.db.execute("DELETE FROM events WHERE event_id=?", (identifier,)).rowcount
            if dropped:
                self._count_drop(count)
        self._maintain()

    def retry(self, identifier, delay):
        with self.db:
            self.db.execute(
                "UPDATE events SET attempts=attempts+1,retry_at=? WHERE event_id=?", (self.clock() + delay, identifier)
            )

    def stats(self):
        self.expire()
        count, created = self.db.execute("SELECT count(*),min(created) FROM events").fetchone()
        row = self.db.execute("SELECT count FROM counters WHERE name='dropped'").fetchone()
        return {
            "queue_size": count,
            "oldest_age": self.clock() - created if created else 0,
            "dropped": row[0] if row else 0,
        }

    def close(self):
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.db.close()
