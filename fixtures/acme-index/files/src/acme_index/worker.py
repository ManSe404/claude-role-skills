"""The worker: takes jobs from the queue table and runs them.

Jobs are rows in the jobs table of the tenant's SQLite file. A job that keeps failing goes to the dead_letter
table with its last error, where an operator can look at it and queue it again.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acme_index import EmbedderError
from acme_index.embedder import Embedder
from acme_index.parse import parse_document
from acme_index.store import Store

log = logging.getLogger(__name__)

MAX_RETRIES = 3
DEFAULT_TENANT = "default"

QUEUE = """
CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dead_letter (id INTEGER PRIMARY KEY, kind TEXT, payload TEXT, error TEXT);
"""


@dataclass(frozen=True)
class Config:
    database: str
    embedder_url: str
    tenant: str
    backoff_seconds: float


def load_config(path: Path) -> Config:
    """Read the worker config (JSON). `tenant` and `backoff_seconds` are optional, see README.md."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Config(
        database=raw["database"],
        embedder_url=raw["embedder_url"],
        tenant=raw.get("tenant", DEFAULT_TENANT),
        backoff_seconds=float(raw.get("backoff_seconds", 2.0)),
    )


@dataclass(frozen=True)
class Job:
    id: int
    kind: str
    payload: dict[str, Any]


class Queue:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.executescript(QUEUE)

    def put(self, kind: str, payload: dict[str, Any]) -> None:
        with self._conn:
            self._conn.execute("INSERT INTO jobs (kind, payload) VALUES (?, ?)", (kind, json.dumps(payload)))

    def next(self) -> Job | None:
        row = self._conn.execute("SELECT id, kind, payload FROM jobs ORDER BY id LIMIT 1").fetchone()
        return Job(row[0], row[1], json.loads(row[2])) if row else None

    def done(self, job: Job) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM jobs WHERE id = ?", (job.id,))

    def dead_letter(self, job: Job, error: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO dead_letter (id, kind, payload, error) VALUES (?, ?, ?, ?)",
                (job.id, job.kind, json.dumps(job.payload), error),
            )
            self._conn.execute("DELETE FROM jobs WHERE id = ?", (job.id,))


class Worker:
    def __init__(self, queue: Queue, store: Store, backoff_seconds: float = 2.0) -> None:
        self._queue = queue
        self._store = store
        self._backoff = backoff_seconds
        self._handlers: dict[str, Callable[[dict[str, Any]], None]] = {
            "index": self._index,
            "reindex": self._reindex,
        }

    def run_job(self, job: Job) -> None:
        """Run one job until it succeeds or has used up its retries."""
        retries = 0
        while True:
            try:
                self._handlers[job.kind](job.payload)
            except EmbedderError as exc:
                if retries >= MAX_RETRIES:
                    log.error("job %s failed after %d retries: %s", job.id, retries, exc)
                    self._queue.dead_letter(job, str(exc))
                    return
                retries += 1
                time.sleep(self._backoff * retries)
            except Exception as exc:
                log.warning("job %s failed, retrying: %s", job.id, exc)
                time.sleep(self._backoff)
            else:
                self._queue.done(job)
                return

    def drain(self) -> int:
        """Run jobs until the queue is empty; return how many ran."""
        ran = 0
        while (job := self._queue.next()) is not None:
            self.run_job(job)
            ran += 1
        return ran

    def _index(self, payload: dict[str, Any]) -> None:
        text = "\n\n".join(parse_document(Path(payload["path"])))
        self._store.add_document(payload["doc_id"], text)

    def _reindex(self, payload: dict[str, Any]) -> None:
        text = "\n\n".join(parse_document(Path(payload["path"])))
        self._store.reindex(payload["doc_id"], text)


def main(argv: list[str] | None = None) -> int:
    """Drain the queue of one tenant: python -m acme_index.worker CONFIG."""
    args = sys.argv[1:] if argv is None else argv
    config = load_config(Path(args[0] if args else "acme-index.json"))
    logging.basicConfig(level=logging.INFO)
    database = Path(config.database) / f"{config.tenant}.sqlite"
    store = Store(database, Embedder(config.embedder_url))
    worker = Worker(Queue(sqlite3.connect(database)), store, config.backoff_seconds)
    log.info("ran %d jobs", worker.drain())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
