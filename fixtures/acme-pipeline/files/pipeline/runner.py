"""Run a job of jobs/*.yaml step by step and write what happened to the ops folder.

Usage: python3 -m pipeline.runner run JOB [--date YYYY-MM-DD]
       python3 -m pipeline.runner status JOB
       python3 -m pipeline.runner checks --layer LAYER

Each task of a run is one line of runs.jsonl; check results go to checks.jsonl and quarantined rows to
quarantine.jsonl (see ops/README.md for the fields).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pipeline import warehouse
from pipeline.config import settings

JOBS = Path("jobs")
CHECKS = Path("checks")


def parse_yaml(text: str) -> dict[str, Any]:
    """The small YAML the job and check files use: scalars, lists of scalars and lists of flat mappings."""
    result: dict[str, Any] = {}
    key = ""
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = raw.split("  #", 1)[0].rstrip()
        if not line.startswith(" "):
            key, _, value = line.partition(":")
            result[key] = value.strip().strip('"') if value.strip() else []
        elif line.lstrip().startswith("- "):
            item = line.lstrip()[2:]
            name, colon, value = item.partition(":")
            result[key].append({name.strip(): value.strip().strip('"')} if colon else item.strip().strip('"'))
        else:
            name, _, value = line.strip().partition(":")
            result[key][-1][name.strip()] = value.strip().strip('"')
    return result


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def append(name: str, record: dict[str, Any]) -> None:
    path = Path(settings.OPS_DIR) / name
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def wait_for_file(step: dict[str, str], day: str) -> tuple[dict[str, int], str, str | None]:
    path = Path(step["path"].replace("{date}", day))
    started = time.monotonic()
    timeout = int(step.get("timeout_minutes", "60")) * 60
    while not path.exists():
        if time.monotonic() - started > timeout:
            raise TimeoutError(f"{path} did not arrive within {timeout // 60} minutes")
        time.sleep(60)
    waited = int(time.monotonic() - started) // 60
    if waited:
        message = f"{path.name} arrived {datetime.now():%H:%M}, {waited} minutes after the job started"
        return {"rows_read": 0, "rows_written": 0, "rows_changed": 0}, "warning", message
    return {"rows_read": 0, "rows_written": 0, "rows_changed": 0}, "success", None


def quarantine(table: str, day: str, run_id: str) -> int:
    rules = parse_yaml((CHECKS / "quarantine.yaml").read_text(encoding="utf-8"))["rules"]
    moved = 0
    for rule in [r for r in rules if r["table"] == table]:
        source = rule.get("source", table)
        sql = f"select row_id, {rule.get('column', 'store_id')} from {source} where load_date = :day and {rule['condition']}"
        for row_id, value in warehouse.query(sql, {"day": day}):
            append("quarantine.jsonl", {"date": day, "table": table, "rule": rule["name"], "row_id": row_id,
                                        "value": value, "run_id": run_id})
            moved += 1
    return moved


def run_step(step: dict[str, str], day: str, run_id: str) -> tuple[dict[str, int], str, str | None]:
    if step["task"] == "wait_for_file":
        return wait_for_file(step, day)
    if "run" in step:
        done = subprocess.run([*step["run"].split(), "--date", day], capture_output=True, text=True, check=True)
        return json.loads(done.stdout), "success", None
    moved = quarantine(step["task"], day, run_id) if "quarantine" in step else 0
    written = warehouse.run_sql(step["sql"], {"load_date": day})
    return {"rows_read": written + moved, "rows_written": written, "rows_changed": written}, "success", None


def run_job(name: str, day: str, attempt: int = 1) -> bool:
    job = parse_yaml((JOBS / f"{name}.yaml").read_text(encoding="utf-8"))
    if job.get("enabled") == "false":
        print(f"{name} is disabled", file=sys.stderr)
        return False
    run_id = f"{name}-{day}-{attempt}"
    record_all = job.get("record_runs", "all") == "all"
    for step in job["steps"]:
        record: dict[str, Any] = {"run_id": run_id, "job": name, "task": step["task"], "layer": step["layer"],
                                  "attempt": attempt, "start": now()}
        try:
            counts, status, message = run_step(step, day, run_id)
        except Exception as error:  # the run record is the only place the error is kept
            record.update(end=now(), status="failed", rows_read=0, rows_written=0, rows_changed=0,
                          error=f"{step['task']}: {error}", message=None)
            append("runs.jsonl", record)
            return False
        record.update(end=now(), status=status, **counts, error=None, message=message)
        if record_all:
            append("runs.jsonl", record)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["run", "status", "checks"])
    parser.add_argument("job", nargs="?")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--layer", default="silver")
    args = parser.parse_args(argv)
    if args.command == "run":
        return 0 if run_job(args.job, args.date) else 1
    if args.command == "status":
        lines = (Path(settings.OPS_DIR) / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        for line in [entry for entry in lines if f'"job": "{args.job}"' in entry][-10:]:
            print(line)
        return 0
    print(f"checks of the {args.layer} layer are run by the scheduler; see checks/{args.layer}.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
