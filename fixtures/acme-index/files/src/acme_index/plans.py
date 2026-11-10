"""Ingestion plans and the runs that execute them (ADR 0002).

A plan is the ordered list of steps for one source. Its digest is a SHA-256 over the steps, so two runs can be
compared by what they did. A run is a row in the runs table.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from acme_index import IndexingError

RUNS = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    plan TEXT NOT NULL,
    digest TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
"""


@dataclass(frozen=True)
class Step:
    name: str
    params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    source: str
    steps: tuple[Step, ...]

    def digest(self) -> str:
        steps = [[step.name, step.params] for step in self.steps]
        payload = json.dumps({"source": self.source, "steps": steps}, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def without(self, names: set[str]) -> Plan:
        return Plan(self.source, tuple(step for step in self.steps if step.name not in names))


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Runs:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.executescript(RUNS)

    def start(self, plan: Plan) -> dict[str, Any]:
        run = {"id": uuid.uuid4().hex, "plan": plan.source, "digest": plan.digest(), "status": "running"}
        with self._conn:
            self._conn.execute(
                "INSERT INTO runs (id, plan, digest, status, started_at) VALUES (?, ?, ?, ?, ?)",
                (run["id"], run["plan"], run["digest"], run["status"], _now()),
            )
        return run

    def finish(self, run: dict[str, Any], status: str) -> None:
        """Close a run: its status, when it ended and, if the plan changed on the way, the new digest."""
        with self._conn:
            new_digest = run.get("_digest")
            if new_digest is not None:
                self._conn.execute("UPDATE runs SET digest = ? WHERE id = ?", (new_digest, run["id"]))
            self._conn.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE id = ?", (status, _now(), run["id"])
            )

    def load(self, run_id: str) -> dict[str, Any]:
        row = self._conn.execute("SELECT id, plan, digest, status FROM runs WHERE id = ?", (run_id,)).fetchone()
        return {"id": row[0], "plan": row[1], "digest": row[2], "status": row[3]}


def execute(plan: Plan, handlers: dict[str, Callable[[dict[str, str]], None]], runs: Runs) -> dict[str, Any]:
    """Run each step of plan in order. A step with no handler is dropped from the plan."""
    run = runs.start(plan)
    missing = {step.name for step in plan.steps if step.name not in handlers}
    if missing:
        plan = plan.without(missing)
        run["digest"] = plan.digest()
    for step in plan.steps:
        try:
            handlers[step.name](step.params)
        except Exception as exc:
            runs.finish(run, "failed")
            raise IndexingError(f"step {step.name} of the plan for {plan.source} failed") from exc
    runs.finish(run, "done")
    return run
