#!/usr/bin/env python3
"""Trace a failed data pipeline run from its records: where it broke, what changed since the last good run, who waits.

Usage: python3 run_trace.py REPO [--run RUN_ID | --job JOB [--date YYYY-MM-DD]] [--git]
       [--runs FILE] [--checks FILE] [--quarantine FILE] [--deliveries FILE] [--incidents FILE.md] [--jobs DIR]

REPO is the platform's repository. The records are found in it by name (runs, checks, quarantine, deliveries as
JSON Lines, JSON or CSV; an incident log in Markdown; job definitions in YAML with steps or tasks), or given with the
flags. Field names are matched without regard to case, with the usual aliases (status or state, start or started_at,
task or step, error or error_message, ...); the output says which fields of which file were understood.

Without --run it traces the latest failing job: the first failed run since that job's failing task last succeeded.
It prints:
- the run task by task in order, the first failed task, its error split into the value, the file and line, the column;
- the other runs that failed with the same error, and the warnings of the run with how often each came on runs that
  loaded fine;
- the last good run of the same task, and what changed since: rows read, and the delivered input files of both days
  (header, delimiter, how each column writes numbers and dates); with --git, the commits between the two runs;
- the line of code the error names, and the other code files that use the same expression;
- the check results and quarantined rows of the run's day for its tables;
- the jobs that depend on the failed one, their runs since, when their tables were last built against their service
  level, and the documents that name those tables;
- the past incidents in the log that match the error, the job, the task or the file, with what they name in
  backticks and where that is used in the code.

Error texts are printed with e-mail addresses, IBANs and JMBGs removed. It prints no row of a data file. Read-only
(git log only, with --git), standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "target", "dist", "build"}
RECORD_SUFFIXES = {".jsonl", ".ndjson", ".json", ".csv"}
CODE_SUFFIXES = {".sql", ".py", ".hql", ".yaml", ".yml"}
RUN_FIELDS = {
    "run_id": ("run", "id", "execution_id", "dag_run_id", "job_run_id", "run_key"),
    "job": ("job_name", "pipeline", "dag", "dag_id", "workflow", "flow"),
    "task": ("task_id", "task_name", "step", "node", "model", "asset"),
    "layer": ("stage", "zone", "tier"),
    "attempt": ("try", "try_number", "retry", "attempt_number"),
    "start": ("started_at", "start_time", "start_date", "begin", "started"),
    "end": ("ended_at", "finished_at", "end_time", "end_date", "finished", "completed_at"),
    "status": ("state", "result", "outcome"),
    "rows_read": ("rows_in", "input_rows", "records_read"),
    "rows_written": ("rows_out", "output_rows", "rows_affected", "records_written"),
    "rows_changed": ("rows_updated", "changed_rows"),
    "error": ("error_message", "exception", "failure", "err"),
    "message": ("msg", "log", "note", "detail"),
}
CHECK_FIELDS = {
    "date": ("run_date", "day", "checked_at", "timestamp", "executed_at"),
    "check": ("check_name", "test", "test_name", "name", "rule"),
    "table": ("dataset", "model", "asset", "table_name", "object"),
    "status": ("state", "result", "outcome"),
    "failing_rows": ("failures", "failed_rows", "rows_failed", "bad_rows", "failing"),
    "note": ("message", "comment", "detail"),
}
QUARANTINE_FIELDS = {
    "date": ("day", "quarantined_at", "timestamp"),
    "table": ("dataset", "target", "table_name"),
    "rule": ("check", "reason", "rule_name"),
    "run_id": ("run", "execution_id"),
}
DELIVERY_FIELDS = {
    "file": ("path", "file_name", "filename", "object", "key", "name"),
    "arrived_at": ("arrived", "received_at", "landed_at", "created_at", "timestamp"),
    "rows": ("row_count", "records"),
}
STATUS = {
    "success": "success", "succeeded": "success", "ok": "success", "passed": "success", "done": "success",
    "completed": "success", "failed": "failed", "failure": "failed", "error": "failed", "errored": "failed",
    "fail": "failed", "skipped": "skipped", "upstream_failed": "skipped", "cancelled": "skipped",
    "warning": "warning", "warn": "warning", "running": "running",
}  # fmt: skip
EMAIL = re.compile(r"[\w.%+-]+@[\w-]+(\.[\w-]+)+")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
JMBG = re.compile(r"(?<!\d)\d{13}(?!\d)")
CODE_REF = re.compile(r"([\w./-]+\.(?:sql|py|hql|yaml|yml))(?:\s+line\s+|:)(\d+)")
QUOTED = re.compile(r"\"([^\"]{1,80})\"|'([^']{1,80})'")


# ---------------------------------------------------------------------------- reading


def clean(text: Any) -> str:
    """Error and log text with personal values taken out."""
    value = "" if text is None else str(text)
    return JMBG.sub("[jmbg]", IBAN.sub("[iban]", EMAIL.sub("[e-mail]", value)))


def read_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if text.lstrip().startswith("["):
        data = json.loads(text)
        return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
    if path.suffix.lower() in (".jsonl", ".ndjson", ".json"):
        records = []
        for line in text.splitlines():
            try:
                record = json.loads(line) if line.strip() else None
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
        return records
    first = text.split("\n", 1)[0]
    return [dict(r) for r in csv.DictReader(text.splitlines(), delimiter=max(",;\t|", key=first.count))]


def lowered(record: dict[str, Any]) -> dict[str, Any]:
    return {re.sub(r"[\s-]+", "_", str(k).strip().lower()): v for k, v in record.items()}


def normalise(record: dict[str, Any], fields: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    low = lowered(record)
    found: dict[str, Any] = {}
    for name, aliases in fields.items():
        found[name] = next((low[a] for a in (name, *aliases) if a in low), None)
    return found


def understood(path: Path, records: list[dict[str, Any]], fields: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    keys = {re.sub(r"[\s-]+", "_", str(k).strip().lower()): str(k) for r in records[:200] for k in r}
    mapped = {n: keys[a] for n, aliases in fields.items() for a in (n, *aliases) if a in keys}
    mapped = {n: mapped[n] for n in fields if n in mapped}
    return {"file": path.as_posix(), "records": len(records), "fields": mapped,
            "missing": [f for f in fields if f not in mapped]}  # fmt: skip


def as_int(value: Any) -> int | None:
    try:
        return int(float(str(value))) if value not in (None, "") else None
    except ValueError:
        return None


def status_of(value: Any) -> str:
    return STATUS.get(str(value or "").strip().lower(), str(value or "").strip().lower() or "unknown")


def walk(repo: Path) -> list[Path]:
    found = []
    stack = [repo]
    while stack:
        folder = stack.pop()
        for path in sorted(folder.iterdir()):
            if path.is_dir() and path.name not in SKIP_DIRS and not path.name.startswith("."):
                stack.append(path)
            elif path.is_file():
                found.append(path)
    return sorted(found)


def discover(files: list[Path], word: str, suffixes: set[str]) -> Path | None:
    hits = [p for p in files if word in p.stem.lower() and p.suffix.lower() in suffixes]
    return min(hits, key=lambda p: (len(p.parts), p.as_posix())) if hits else None


# ---------------------------------------------------------------------------- YAML, the flat shapes only


def _strip_comment(line: str) -> str:
    quote = ""
    for i, char in enumerate(line):
        if char in "\"'" and not quote:
            quote = char
        elif char == quote:
            quote = ""
        elif char == "#" and not quote and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def scalar(text: str) -> Any:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        return [scalar(p) for p in text[1:-1].split(",") if p.strip()]
    if text in ("", "~", "null"):
        return None
    if text in ("true", "false"):
        return text == "true"
    return text


KEY_LINE = re.compile(r"^[\w.$/-]+\s*:(\s|$)")


def parse_yaml(text: str) -> Any:
    """A YAML reader for the flat shapes of job and check files: mappings, lists, flow lists, scalars."""
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        if line.strip() and line.strip() != "---":
            lines.append((len(line) - len(line.lstrip(" ")), line.strip()))
    return _block(lines, 0, lines[0][0])[0] if lines else None


def _block(lines: list[tuple[int, str]], i: int, indent: int) -> tuple[Any, int]:
    if lines[i][1] == "-" or lines[i][1].startswith("- "):
        items: list[Any] = []
        while i < len(lines) and lines[i][0] == indent and (lines[i][1] == "-" or lines[i][1].startswith("- ")):
            rest = lines[i][1][1:].strip()
            if not rest:
                value, i = _block(lines, i + 1, lines[i + 1][0]) if i + 1 < len(lines) else (None, i + 1)
            elif KEY_LINE.match(rest) and not rest.startswith(("'", '"')):
                inner = indent + len(lines[i][1]) - len(rest)
                lines[i] = (inner, rest)
                value, i = _block(lines, i, inner)
            else:
                value, i = scalar(rest), i + 1
            items.append(value)
        return items, i
    mapping: dict[str, Any] = {}
    while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith("- "):
        key, _, rest = lines[i][1].partition(":")
        key, rest = key.strip().strip("\"'"), rest.strip()
        i += 1
        if rest:
            mapping[key] = scalar(rest)
        elif i < len(lines) and (lines[i][0] > indent or (lines[i][0] == indent and lines[i][1].startswith("- "))):
            mapping[key], i = _block(lines, i, lines[i][0])
        else:
            mapping[key] = None
    return mapping, i


def load_jobs(paths: list[Path], repo: Path) -> dict[str, dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    for path in paths:
        try:
            data = parse_yaml(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, IndexError):
            continue
        if not isinstance(data, dict):
            continue
        steps = data.get("steps") or data.get("tasks")
        if not isinstance(steps, list):
            continue
        name = str(data.get("name") or data.get("job") or path.stem)
        data["_steps"] = [s for s in steps if isinstance(s, dict)]
        data["_file"] = rel(path, repo)
        depends = data.get("depends_on") or data.get("upstream") or data.get("after") or []
        data["_depends"] = [str(d) for d in (depends if isinstance(depends, list) else [depends])]
        jobs[name] = data
    return jobs


def rel(path: Path, repo: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------- runs


def group_runs(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    runs: dict[str, list[dict[str, Any]]] = {}
    for raw in records:
        task = normalise(raw, RUN_FIELDS)
        task["status"] = status_of(task["status"])
        for name in ("rows_read", "rows_written", "rows_changed", "attempt"):
            task[name] = as_int(task[name])
        run_id = str(task["run_id"] or f"{task['job']}@{str(task['start'] or '')[:16]}")
        runs.setdefault(run_id, []).append(task)
    for tasks in runs.values():
        tasks.sort(key=lambda t: str(t["start"] or ""))
    return runs


def run_day(run_id: str, tasks: list[dict[str, Any]]) -> str:
    match = re.search(r"\d{4}-\d{2}-\d{2}", run_id)
    return match.group() if match else str(tasks[0]["start"] or "")[:10]


def first_failed(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((t for t in tasks if t["status"] == "failed"), None)


def signature(error: str) -> str:
    """The error without its values, places and the task's name in front: what two failures share."""
    text = re.sub(r"^[\w.]+:\s+", "", error.strip())
    text = QUOTED.sub("", text)
    text = re.sub(r"\(.*?\)|\d+", "", text)
    return re.sub(r"[\s:,]+$", "", re.sub(r"\s+", " ", text)).strip().lower()


def error_parts(error: str) -> dict[str, Any]:
    parts: dict[str, Any] = {"signature": signature(error)}
    quoted = QUOTED.search(error)
    if quoted:
        parts["value"] = quoted.group(1) or quoted.group(2)
    code = CODE_REF.search(error)
    if code:
        parts["file"], parts["line"] = code.group(1), int(code.group(2))
    column = re.search(r"\bcolumn\s+[\"`]?(\w+)", error)
    if column:
        parts["column"] = column.group(1)
    return parts


def choose(runs: dict[str, list[dict[str, Any]]], args: argparse.Namespace) -> str | None:
    if args.run:
        return str(args.run) if args.run in runs else None
    failed = [(rid, tasks) for rid, tasks in runs.items() if first_failed(tasks)]
    if args.job:
        failed = [(rid, t) for rid, t in failed if t[0]["job"] == args.job]
    if args.date:
        failed = [(rid, t) for rid, t in failed if run_day(rid, t) == args.date]
    if not failed:
        return None
    latest_id, latest = max(failed, key=lambda pair: str(pair[1][0]["start"] or ""))
    failing = first_failed(latest)
    assert failing is not None
    good = last_good(runs, latest[0]["job"], failing["task"], str(latest[0]["start"] or ""))
    since = str(good[1][0]["start"] or "") if good else ""
    streak = [(rid, t) for rid, t in failed if t[0]["job"] == latest[0]["job"] and str(t[0]["start"] or "") > since]
    return min(streak, key=lambda pair: str(pair[1][0]["start"] or ""))[0] if not args.date else latest_id


def last_good(
    runs: dict[str, list[dict[str, Any]]], job: Any, task: Any, before: str
) -> tuple[str, list[dict[str, Any]]] | None:
    good = [
        (rid, tasks)
        for rid, tasks in runs.items()
        if tasks[0]["job"] == job
        and str(tasks[0]["start"] or "") < before
        and any(t["task"] == task and t["status"] in ("success", "warning") for t in tasks)
    ]
    return max(good, key=lambda pair: str(pair[1][0]["start"] or "")) if good else None


def task_view(task: dict[str, Any]) -> dict[str, Any]:
    view = {k: task[k] for k in ("task", "layer", "status", "start", "end", "rows_read", "rows_written") if task[k]}
    if task["error"]:
        view["error"] = clean(task["error"])
    if task["message"]:
        view["message"] = clean(task["message"])
    return view


# ---------------------------------------------------------------------------- what changed: input files and code


def column_styles(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1250", errors="replace")
    first = text.split("\n", 1)[0]
    delimiter = max(",;\t|", key=first.count)
    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    header = next(reader, [])
    styles: dict[str, Counter[str]] = {h: Counter() for h in header}
    rows = 0
    for row in reader:
        if not row:
            continue
        rows += 1
        for name, value in zip(header, row, strict=False):
            styles[name][style(value)] += 1
    return {
        "rows": rows,
        "delimiter": delimiter,
        "header": header,
        "columns": {k: dict(v.most_common(3)) for k, v in styles.items()},
    }


def style(value: str) -> str:
    text = value.strip()
    shapes = [
        ("empty", r""),
        ("integer", r"[+-]?\d+"),
        ("decimal point", r"[+-]?\d+\.\d+|[+-]?\d{1,3}(,\d{3})+\.\d+"),
        ("decimal comma", r"[+-]?\d+,\d+|[+-]?\d{1,3}(\.\d{3})+,\d+"),
        ("date YYYY-MM-DD", r"\d{4}-\d{2}-\d{2}"),
        ("date DD.MM.YYYY", r"\d{1,2}\.\d{1,2}\.\d{4}\.?"),
        ("timestamp", r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}.*"),
    ]
    return next((name for name, rx in shapes if re.fullmatch(rx, text)), "text")


def input_files(job: dict[str, Any] | None, deliveries: list[dict[str, Any]], repo: Path, day: str) -> list[Path]:
    templates = []
    for step in (job or {}).get("_steps", []):
        templates += [str(v) for v in step.values() if isinstance(v, str) and "{date}" in v]
    found = [repo / t.replace("{date}", day) for t in templates]
    if not found:
        found = [repo / str(d["file"]) for d in deliveries if day in str(d["file"] or "")]
    return [p for p in found if p.is_file()]


def compare_inputs(before: list[Path], after: list[Path], repo: Path, column: str | None) -> list[dict[str, Any]]:
    result = []
    for old, new in zip(before, after, strict=False):
        a, b = column_styles(old), column_styles(new)
        entry: dict[str, Any] = {
            "last_good": rel(old, repo),
            "failed": rel(new, repo),
            "rows": [a["rows"], b["rows"]],
            "columns_added": [c for c in b["header"] if c not in a["header"]],
            "columns_removed": [c for c in a["header"] if c not in b["header"]],
        }
        if a["delimiter"] != b["delimiter"]:
            entry["delimiter"] = [a["delimiter"], b["delimiter"]]
        changed = {
            c: {"last_good": a["columns"][c], "failed": b["columns"][c]}
            for c in b["header"]
            if c in a["columns"]
            and max(a["columns"][c], key=a["columns"][c].get, default="")
            != max(b["columns"][c], key=b["columns"][c].get, default="")
        }
        entry["columns_written_differently"] = changed
        if column and column in b["columns"]:
            entry["the_failing_column"] = {
                "column": column,
                "last_good": a["columns"].get(column),
                "failed": b["columns"][column],
            }
        result.append(entry)
    return result


def code_line(repo: Path, file: str, line: int) -> str | None:
    path = repo / file
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[line - 1].strip() if 0 < line <= len(lines) else None


def expression_of(line: str) -> re.Pattern[str]:
    """The cast on the line, made loose about spaces and the column, or the line itself."""
    cast = re.search(r"cast\s*\(\s*[\w.\"]+\s+as\s+([\w ]+(\([\d,\s]*\))?)\s*\)", line, re.I)
    if cast:
        kind = r"\s*".join(re.escape(part) for part in re.split(r"\s+", cast.group(1).strip()))
        kind = kind.replace(",", r",\s*")
        return re.compile(rf"cast\s*\(\s*[\w.\"]+\s+as\s+{kind}\s*\)", re.I)
    shorthand = re.search(r"[\w.\"]+\s*::\s*([\w]+(\([\d,\s]*\))?)", line)
    if shorthand:
        return re.compile(rf"[\w.\"]+\s*::\s*{re.escape(shorthand.group(1))}", re.I)
    return re.compile(re.escape(re.sub(r"\s+", " ", line)))


def same_pattern(repo: Path, files: list[Path], origin: str, line: int, text: str) -> list[dict[str, Any]]:
    pattern = expression_of(text)
    found = []
    for path in files:
        if path.suffix.lower() not in {".sql", ".hql", ".py"}:
            continue
        name = rel(path, repo)
        for number, content in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if (name, number) != (origin, line) and pattern.search(re.sub(r"\s+", " ", content)):
                found.append({"file": name, "line": number, "text": content.strip()})
    return found


def commits_between(repo: Path, since: str, until: str) -> list[str] | str:
    command = [
        "git",
        "-C",
        str(repo),
        "log",
        f"--since={since}",
        f"--until={until}",
        "--format=%h %ad %s",
        "--date=iso",
    ]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"git log failed: {error}"
    return done.stdout.splitlines() if done.returncode == 0 else f"git log failed: {done.stderr.strip()[:200]}"


# ---------------------------------------------------------------------------- the incident log


def incidents(path: Path) -> list[dict[str, Any]]:
    entries = []
    current: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("## "):
            current = {"title": re.sub(r"^\d{4}-\d{2}-\d{2}:?\s*", "", line[3:].strip()), "lines": []}
            date = re.search(r"\d{4}-\d{2}-\d{2}", line)
            current["date"] = date.group() if date else None
            entries.append(current)
        elif current is not None:
            current["lines"].append(line)
    return entries


def match_incidents(
    entries: list[dict[str, Any]], failing: dict[str, Any], parts: dict[str, Any], code: list[Path], repo: Path
) -> list[dict[str, Any]]:
    matched = []
    texts = {rel(p, repo): p.read_text(encoding="utf-8", errors="replace") for p in code}
    for entry in entries:
        body = "\n".join(entry["lines"])
        whole = (entry["title"] + "\n" + body).lower()
        reasons = []
        if parts.get("signature") and len(parts["signature"]) > 12 and parts["signature"] in whole:
            reasons.append(f"the same error: {parts['signature']}")
        for label in ("job", "task"):
            if failing.get(label) and str(failing[label]).lower() in whole:
                reasons.append(f"the same {label}: {failing[label]}")
        if parts.get("file") and parts["file"].lower() in whole:
            reasons.append(f"the same file: {parts['file']}")
        if not reasons:
            continue
        mentions = sorted(set(re.findall(r"`([^`\s]{3,80})`", body)))
        used = {}
        for mention in mentions:  # a function the past fix brought in: where it is called, and if the failing file does
            if not re.fullmatch(r"[\w]+(\.[\w]+)?", mention):
                continue
            call = re.compile(rf"(?i)(?<!into )(?<!table )(?<![\w.]){re.escape(mention)}\s*\(")
            callers = sorted(
                f for f, t in texts.items() if call.search(t) and not re.search(r"(?i)create\b.*\bfunction", t)
            )
            if callers:
                used[mention] = {"called_in": callers, "called_in_the_failing_file": parts.get("file") in callers}
        open_items = [clean(line.split(":", 1)[1].strip()) for line in entry["lines"] if re.match(r"^- Open\b", line)]
        matched.append(
            {
                "date": entry["date"],
                "title": clean(entry["title"]),
                "matched_on": reasons,
                "names": mentions,
                "where_those_are_used": used,
                "open": open_items,
            }
        )
    return matched


# ---------------------------------------------------------------------------- the whole trace


def tables_of(job: dict[str, Any] | None) -> list[str]:
    tables = []
    for step in (job or {}).get("_steps", []):
        name = str(step.get("task") or step.get("name") or step.get("table") or "")
        if re.fullmatch(r"\w+\.\w+", name):
            tables.append(name)
    return tables


def downstream(
    jobs: dict[str, dict[str, Any]],
    runs: dict[str, list[dict[str, Any]]],
    failed_job: str,
    since: str,
    docs: list[Path],
    repo: Path,
) -> list[dict[str, Any]]:
    found = []
    for name, job in sorted(jobs.items()):
        if failed_job not in job["_depends"]:
            continue
        own = sorted(((rid, t) for rid, t in runs.items() if t[0]["job"] == name), key=lambda p: str(p[1][0]["start"]))
        after = [{"run_id": rid, "status": worst(t)} for rid, t in own if str(t[0]["start"] or "") >= since[:10]]
        built = [t for _, ts in own for t in ts if t["status"] == "success"]
        tables = tables_of(job)
        found.append(
            {
                "job": name,
                "defined_in": job["_file"],
                "tables": tables,
                "sla": job.get("sla"),
                "runs_since_the_failure": after,
                "last_built": max((str(t["end"]) for t in built if t["end"]), default=None),
                "documents_naming_its_tables": sorted(
                    rel(p, repo)
                    for p in docs
                    if any(t in p.read_text(encoding="utf-8", errors="replace") for t in tables)
                ),
            }
        )
    return found


def worst(tasks: list[dict[str, Any]]) -> str:
    order = ["failed", "skipped", "warning", "running", "success"]
    return str(min((t["status"] for t in tasks), key=lambda s: order.index(s) if s in order else len(order)))


def trace(args: argparse.Namespace) -> dict[str, Any]:
    repo: Path = args.repo
    files = walk(repo)
    paths = {
        "runs": args.runs or discover(files, "run", RECORD_SUFFIXES),
        "checks": args.checks or discover([f for f in files if f.suffix.lower() != ".yaml"], "check", RECORD_SUFFIXES),
        "quarantine": args.quarantine or discover(files, "quarant", RECORD_SUFFIXES),
        "deliveries": args.deliveries or discover(files, "deliver", RECORD_SUFFIXES),
        "incidents": args.incidents or discover(files, "incident", {".md"}),
    }
    if paths["runs"] is None:
        raise SystemExit("no run records found: give them with --runs")
    job_files = sorted(args.jobs.glob("*.y*ml")) if args.jobs else [f for f in files if f.suffix in (".yaml", ".yml")]
    jobs = load_jobs(job_files, repo)
    code = [f for f in files if f.suffix.lower() in CODE_SUFFIXES]
    docs = [f for f in files if f.suffix.lower() == ".md" and f != paths["incidents"]]
    records = {k: read_records(p) if p else [] for k, p in paths.items() if k != "incidents"}
    fields = {
        "runs": RUN_FIELDS,
        "checks": CHECK_FIELDS,
        "quarantine": QUARANTINE_FIELDS,
        "deliveries": DELIVERY_FIELDS,
    }
    seen: dict[str, Any] = {
        k: understood(p, records[k], fields[k]) if p else None for k, p in paths.items() if k in fields
    }
    seen["incidents"] = rel(paths["incidents"], repo) if paths["incidents"] else None
    seen["jobs"] = sorted(j["_file"] for j in jobs.values())
    runs = group_runs(records["runs"])
    failed_runs = [
        {"run_id": rid, "job": t[0]["job"], "start": t[0]["start"], "task": f["task"], "error": clean(f["error"])}
        for rid, t in sorted(runs.items(), key=lambda p: str(p[1][0]["start"] or ""))
        if (f := first_failed(t))
    ]
    result: dict[str, Any] = {"understood": seen, "failed_runs": failed_runs[-20:]}
    chosen = choose(runs, args)
    if chosen is None:
        result["run"] = None
        result["hits"] = ["no failed run matches" if (args.run or args.job) else "no failed run in the records"]
        return result
    tasks = runs[chosen]
    failing = first_failed(tasks) or tasks[-1]
    job_name = str(tasks[0]["job"])
    job = jobs.get(job_name)
    day = run_day(chosen, tasks)
    parts = error_parts(str(failing["error"] or ""))
    result["run"] = {
        "run_id": chosen,
        "job": job_name,
        "day": day,
        "attempt": tasks[0]["attempt"],
        "job_definition": job["_file"] if job else None,
        "tasks": [task_view(t) for t in tasks],
        "first_failed": task_view(failing),
        "error_parts": {k: clean(v) if isinstance(v, str) else v for k, v in parts.items()},
    }
    start = str(tasks[0]["start"] or "")
    result["same_error_since"] = [
        {"run_id": f["run_id"], "start": f["start"], "task": f["task"]}
        for f in failed_runs
        if f["run_id"] != chosen and str(f["start"] or "") >= start and signature(f["error"]) == parts["signature"]
    ]
    result["warnings_in_the_run"] = warnings(runs, tasks, failing)
    good = last_good(runs, job_name, failing["task"], start)
    if good:
        good_id, good_tasks = good
        good_task = next(t for t in good_tasks if t["task"] == failing["task"])
        changes: dict[str, Any] = {
            "rows_read": {"last_good": good_task["rows_read"], "failed": failing["rows_read"]},
        }
        deliveries = [normalise(r, DELIVERY_FIELDS) for r in records["deliveries"]]
        before = input_files(job, deliveries, repo, run_day(good_id, good_tasks))
        after = input_files(job, deliveries, repo, day)
        changes["input_files"] = compare_inputs(before, after, repo, parts.get("column"))
        if args.git:
            changes["commits_between"] = commits_between(repo, str(good_tasks[0]["start"]), start)
        result["last_good"] = {"run_id": good_id, "start": good_tasks[0]["start"], "task": task_view(good_task)}
        result["changed_since_the_last_good_run"] = changes
    if parts.get("file") and parts.get("line"):
        text = code_line(repo, parts["file"], parts["line"])
        result["code"] = {"file": parts["file"], "line": parts["line"], "text": text}
        if text:
            result["same_expression_elsewhere"] = same_pattern(repo, code, parts["file"], parts["line"], text)
    tables = tables_of(job)
    checks = [normalise(r, CHECK_FIELDS) for r in records["checks"]]
    result["checks_that_day"] = [
        {"check": c["check"], "table": c["table"], "status": c["status"], "failing_rows": c["failing_rows"]}
        for c in checks
        if str(c["date"] or "")[:10] == day and (not tables or c["table"] in tables)
    ]
    not_checked = [t for t in tables if t not in {c["table"] for c in result["checks_that_day"]}]
    if not_checked:
        result["tables_without_a_check_result_that_day"] = not_checked
    quarantined = [normalise(r, QUARANTINE_FIELDS) for r in records["quarantine"]]
    result["quarantine_of_the_run"] = dict(Counter(str(q["rule"]) for q in quarantined if q["run_id"] == chosen))
    result["downstream"] = downstream(jobs, runs, job_name, start, docs, repo)
    if paths["incidents"]:
        entries = incidents(paths["incidents"])
        result["past_incidents"] = match_incidents(
            entries, {"job": job_name, "task": failing["task"]}, parts, code, repo
        )
    result["hits"] = hits_of(result)
    return result


def warnings(runs: dict[str, list[dict[str, Any]]], tasks: list[dict[str, Any]], failing: dict[str, Any]) -> list[Any]:
    found = []
    for task in tasks:
        if task["status"] != "warning":
            continue
        same = [
            rid for rid, ts in runs.items() if any(t["task"] == task["task"] and t["status"] == "warning" for t in ts)
        ]
        fine = [
            rid for rid in same if any(t["task"] == failing["task"] and t["status"] == "success" for t in runs[rid])
        ]
        found.append(
            {
                "task": task["task"],
                "message": clean(task["message"] or task["error"]),
                "runs_with_this_warning": len(same),
                "of_which_the_failed_task_succeeded": len(fine),
            }
        )
    return found


def hits_of(result: dict[str, Any]) -> list[str]:
    run = result["run"]
    first = run["first_failed"]
    hits = [f"{run['run_id']}: first failed task {first.get('task')} ({first.get('layer')}): {first.get('error')}"]
    if result["same_error_since"]:
        hits.append(f"the same error in {len(result['same_error_since'])} later runs")
    for warning in result["warnings_in_the_run"]:
        hits.append(
            f"warning {warning['task']} came on {warning['runs_with_this_warning']} runs, "
            f"{warning['of_which_the_failed_task_succeeded']} of them loaded fine"
        )
    for entry in result.get("changed_since_the_last_good_run", {}).get("input_files", []):
        if entry.get("the_failing_column"):
            hits.append(f"input {entry['failed']}: {entry['the_failing_column']}")
        elif entry["columns_written_differently"]:
            hits.append(f"input {entry['failed']}: written differently {list(entry['columns_written_differently'])}")
        if entry["columns_added"] or entry["columns_removed"]:
            hits.append(f"input {entry['failed']}: added {entry['columns_added']}, removed {entry['columns_removed']}")
    if result.get("code"):
        hits.append(f"{result['code']['file']}:{result['code']['line']}: {result['code']['text']}")
    hits += [f"same expression at {s['file']}:{s['line']}" for s in result.get("same_expression_elsewhere", [])]
    for job in result["downstream"]:
        statuses = Counter(r["status"] for r in job["runs_since_the_failure"])
        hits.append(
            f"downstream {job['job']}: runs since {dict(statuses)}, last built {job['last_built']}, sla {job['sla']}"
        )
    for entry in result.get("past_incidents", []):
        hits.append(f"past incident {entry['date']}: {entry['title']} ({'; '.join(entry['matched_on'])})")
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("repo", type=Path, help="the platform's repository")
    parser.add_argument("--run", help="the run id to trace")
    parser.add_argument("--job", help="trace the latest failed run of this job")
    parser.add_argument("--date", help="with --job: the run of this day (YYYY-MM-DD)")
    parser.add_argument("--git", action="store_true", help="list the commits between the last good and the failed run")
    for name in ("runs", "checks", "quarantine", "deliveries", "incidents", "jobs"):
        parser.add_argument(f"--{name}", type=Path, help=f"the {name} file (or folder, for jobs), if not found by name")
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        print(f"not a folder: {args.repo}", file=sys.stderr)
        return 2
    json.dump(trace(args), sys.stdout, indent=1, ensure_ascii=False, default=str)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
