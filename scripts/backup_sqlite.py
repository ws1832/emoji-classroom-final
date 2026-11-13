"""SQLite online backup；不直接复制活跃 WAL 数据库。目标必须不存在。"""

import argparse
import os
import sqlite3
from pathlib import Path
from contextlib import closing


def backup(source: Path, destination: Path):
    source, destination = source.resolve(), destination.resolve()
    if not source.is_file() or destination.exists() or source == destination:
        raise ValueError("Existing source and a new destination are required")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    if temporary.exists():
        raise ValueError("Partial backup already exists")
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as incoming:
            with closing(sqlite3.connect(temporary)) as outgoing:
                incoming.backup(outgoing, pages=128)
                if outgoing.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup failed integrity verification")
        os.rename(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    backup(args.source, args.destination)
    print("Backup complete; keep the snapshot outside Git and verify a separate restore.")
