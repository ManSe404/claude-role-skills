#!/usr/bin/env python3
"""Where a data platform's compute and storage money goes, and the spending with no use behind it.

Usage: python3 cost_breakdown.py REPO [--usage FILE] [--storage FILE] [--queries FILE] [--runs FILE]
                                      [--jobs FOLDER] [--changed-below SHARE] [--rate CLUSTER=PRICE ...]

REPO is searched for the inputs that are not given: a usage or billing export (a date, a job or cluster, compute
hours and/or cost), a storage table (a table, its size and its monthly cost), a query log (a date, a consumer, a
table and optionally a count), run records (a job, a task, rows written and rows changed), each as CSV, TSV, JSON
Lines or a JSON array; job definitions as YAML (a name, a cron schedule, a cluster, steps naming the tables they
build); and the SQL files. Field names match case-insensitively, with common aliases. `inputs` says which file and
which column fed each field, and what was not found.

It prints the cost per cluster, job, pipeline (jobs joined by depends_on) and table (a job's compute split over the
tables it builds by their share of run time, evenly when there are no run records), the totals, and four kinds of
candidates: tables nobody reads (no query in the log and no SQL that reads them), full reloads of tables that barely
change (rows changed under the share on every run), jobs that run more often than their tables are read, and compute
billed with no job on it. Money is exact to the cent and the parts add up to the totals.

A consumer that looks like an e-mail address is replaced by a label. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", "dist", "build", ".mypy_cache"}
DATA_SUFFIXES = {".csv", ".tsv", ".jsonl", ".ndjson", ".json"}
MAX_BYTES = 200_000_000
CENT = Decimal("0.01")
SHARE_PLACES = Decimal("0.001")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")

ROLES: dict[str, dict[str, list[str]]] = {
    "usage": {
        "date": ["date", "day", "usage_date", "billing_date", "usage_day", "date_day", "usage_start_date"],
        "resource": ["resource", "resource_name", "job", "job_name", "pipeline", "workload", "name"],
        "type": ["resource_type", "type", "kind", "resource_kind", "category"],
        "cluster": ["cluster", "cluster_name", "warehouse", "warehouse_name", "compute", "pool"],
        "hours": ["compute_hours", "hours", "node_hours", "usage_hours", "runtime_hours", "duration_hours"],
        "cost": [
            "compute_eur",
            "cost_eur",
            "eur",
            "cost",
            "compute_usd",
            "cost_usd",
            "usd",
            "billed_cost",
            "total_cost",
            "net_cost",
            "cost_amount",
            "charge",
        ],
        "currency": ["currency", "billing_currency", "currency_code"],
    },
    "storage": {
        "table": ["table", "table_name", "full_name", "table_full_name", "object", "object_name"],
        "layer": ["layer", "schema", "zone", "tier"],
        "gb": ["gb", "size_gb", "storage_gb", "total_gb", "gib"],
        "bytes": ["bytes", "size_bytes", "total_bytes", "active_bytes", "storage_bytes"],
        "cost": [
            "eur_per_month",
            "monthly_eur",
            "storage_eur",
            "cost_per_month",
            "monthly_cost",
            "cost_eur",
            "usd_per_month",
            "monthly_usd",
            "cost",
            "eur",
            "usd",
        ],
    },
    "queries": {
        "date": ["date", "day", "query_date", "start_time", "started_at", "timestamp", "ts", "executed_at"],
        "consumer": [
            "consumer",
            "user",
            "user_name",
            "username",
            "client",
            "application",
            "app",
            "principal",
            "reader",
            "service",
        ],
        "table": ["table", "table_name", "object", "object_name", "relation", "accessed_table", "base_object"],
        "count": ["queries", "query_count", "count", "reads", "num_queries", "executions", "n"],
    },
    "runs": {
        "job": ["job", "job_name", "pipeline", "dag_id", "flow"],
        "task": ["task", "task_id", "step", "table", "model", "node"],
        "run": ["run_id", "run", "execution_id", "dag_run_id"],
        "start": ["start", "started_at", "start_time", "start_ts"],
        "end": ["end", "ended_at", "end_time", "finished_at", "end_ts"],
        "status": ["status", "state", "result", "outcome"],
        "written": ["rows_written", "written_rows", "rows_out", "rows_loaded", "rows_affected"],
        "changed": ["rows_changed", "changed_rows", "rows_modified", "changes"],
    },
}
REQUIRED: dict[str, list[list[str]]] = {
    "usage": [["date"], ["hours", "cost"], ["resource", "cluster"]],
    "storage": [["table"], ["gb", "bytes", "cost"]],
    "queries": [["date"], ["consumer"], ["table"]],
    "runs": [["job"], ["status", "written"], ["start", "run"]],
}
NAME_HINTS = {
    "usage": ("usage", "billing", "cost", "spend"),
    "storage": ("storage", "size", "tables"),
    "queries": ("query", "access", "read"),
    "runs": ("run", "task", "execution"),
}
QNAME = r'[A-Za-z_"`\[][\w"`\[\]$]*(?:\.[\w"`\[\]$]+)+'
WRITES = [
    ("replace", re.compile(rf"(?is)\bcreate\s+or\s+replace\s+(?:transient\s+)?table\s+({QNAME})")),
    ("create", re.compile(rf"(?is)\bcreate\s+(?:temp\w*\s+|transient\s+)?table\s+(?:if\s+not\s+exists\s+)?({QNAME})")),
    ("overwrite", re.compile(rf"(?is)\binsert\s+overwrite\s+(?:table\s+)?({QNAME})")),
    ("insert", re.compile(rf"(?is)\binsert\s+into\s+({QNAME})")),
    ("truncate", re.compile(rf"(?is)\btruncate\s+(?:table\s+)?({QNAME})")),
    ("merge", re.compile(rf"(?is)\bmerge\s+into\s+({QNAME})")),
    ("update", re.compile(rf"(?is)\bupdate\s+({QNAME})\s+set\b")),
    ("delete", re.compile(rf"(?is)\bdelete\s+from\s+({QNAME})")),
]
FULL_KINDS = {"replace", "overwrite", "truncate"}
READS = re.compile(rf"(?is)\b(from|join)\s+({QNAME})")
SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "sys"}
FULL_KEYS = re.compile(
    r"(?im)^\s*(load|load_type|mode|strategy|materialized|refresh)\s*:\s*[\"']?(full\w*|truncate\w*|overwrite|table)"
    r"[\"']?\s*(#.*)?$|^\s*full_refresh\s*:\s*true\b"
)


# ---------------------------------------------------------------------------- reading files


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def table_key(name: str) -> str:
    """A table name without quotes, in lower case, as its last two parts, so db.gold.t matches gold.t."""
    clean = re.sub(r'["`\[\]]', "", name.strip()).lower()
    return ".".join(clean.split(".")[-2:])


def delimiter_of(line: str) -> str:
    return max(",;\t|", key=line.count)


def flat(record: dict[str, Any]) -> dict[str, str]:
    row: dict[str, str] = {}
    for key, value in record.items():
        if isinstance(value, dict):
            for sub, inner in value.items():
                row[norm(f"{key}_{sub}")] = "" if inner is None else str(inner)
        else:
            row[norm(str(key))] = "" if value is None else str(value)
    return row


def read_rows(path: Path) -> list[dict[str, str]]:
    """The rows of a CSV, TSV, JSON Lines or JSON array file, with normalised column names and text values."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if path.suffix.lower() in (".jsonl", ".ndjson"):
        return [flat(json.loads(line)) for line in text.splitlines() if line.strip().startswith("{")]
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        items = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])
        return [flat(item) for item in items if isinstance(item, dict)]
    first = text.split("\n", 1)[0]
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter_of(first))
    return [{norm(k): (v or "") for k, v in row.items() if k is not None} for row in reader]


def header_of(path: Path) -> list[str]:
    try:
        if path.stat().st_size > MAX_BYTES:
            return []
        with path.open(encoding="utf-8-sig", errors="replace") as handle:
            first = handle.readline()
            if path.suffix.lower() in (".jsonl", ".ndjson"):
                return list(flat(json.loads(first))) if first.strip().startswith("{") else []
            if path.suffix.lower() == ".json":
                handle.seek(0)
                rows = read_rows(path)
                return list(rows[0]) if rows else []
            return [norm(c) for c in next(csv.reader([first], delimiter=delimiter_of(first)), [])]
    except (OSError, ValueError, UnicodeError):
        return []


def pick(columns: Iterable[str], aliases: Sequence[str]) -> str | None:
    present = set(columns)
    return next((a for a in aliases if a in present), None)


def fields_for(role: str, columns: list[str]) -> dict[str, str] | None:
    """The column for each field of a role, or None when a required field is missing."""
    found = {f: c for f, aliases in ROLES[role].items() if (c := pick(columns, aliases))}
    if all(any(f in found for f in options) for options in REQUIRED[role]):
        return found
    return None


def walk(root: Path, suffixes: set[str]) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in suffixes and not set(p.relative_to(root).parts) & SKIP_DIRS
    )


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


@dataclass
class Source:
    role: str
    path: Path
    fields: dict[str, str]
    rows: list[dict[str, str]] = field(default_factory=list)

    def get(self, row: dict[str, str], name: str) -> str:
        column = self.fields.get(name)
        return row.get(column, "").strip() if column else ""


def find_sources(root: Path, given: dict[str, Path | None]) -> dict[str, Source]:
    found: dict[str, Source] = {}
    candidates: dict[str, list[tuple[int, int, Path, dict[str, str]]]] = defaultdict(list)
    files = walk(root, DATA_SUFFIXES) if root.is_dir() else []
    for role, path in given.items():
        if path is not None:
            columns = header_of(path)
            fields = fields_for(role, columns)
            if fields is None:
                raise SystemExit(f"{path}: no {role} columns found among {columns}")
            found[role] = Source(role, path, fields)
    for path in files:
        columns = header_of(path)
        for role in ROLES:
            if role in found:
                continue
            fields = fields_for(role, columns)
            if fields is not None:
                hint = int(any(h in path.name.lower() for h in NAME_HINTS[role]))
                candidates[role].append((hint, len(fields), path, fields))
    taken = {s.path for s in found.values()}
    for role in ROLES:
        if role in found:
            continue
        options = sorted((c for c in candidates[role] if c[2] not in taken), key=lambda c: (-c[0], -c[1], str(c[2])))
        if options:
            _, _, path, fields = options[0]
            found[role] = Source(role, path, fields)
            taken.add(path)
    for source in found.values():
        source.rows = read_rows(source.path)
    return found


def to_decimal(text: str) -> Decimal | None:
    value = text.strip().replace(" ", "").replace("\N{NO-BREAK SPACE}", "")
    if not value:
        return None
    if "," in value and "." in value:
        value = (
            value.replace(".", "").replace(",", ".") if value.rfind(",") > value.rfind(".") else value.replace(",", "")
        )
    elif "," in value:
        value = value.replace(",", "") if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+", value) else value.replace(",", ".")
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def to_date(text: str) -> date | None:
    value = text.strip()
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if match:
        return date(int(match[1]), int(match[2]), int(match[3]))
    match = re.match(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", value)
    if match:
        return date(int(match[3]), int(match[2]), int(match[1]))
    return None


def to_datetime(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def share(part: int, whole: int) -> str | None:
    return str((Decimal(part) * 100 / Decimal(whole)).quantize(SHARE_PLACES, rounding=ROUND_HALF_UP)) if whole else None


def allocate(total: Decimal, weights: dict[str, Decimal]) -> dict[str, Decimal]:
    """Split total over the keys by weight, in cents, so the parts add up to the total exactly."""
    cents = int((total / CENT).to_integral_value(rounding=ROUND_HALF_UP))
    whole = sum(weights.values())
    if not weights:
        return {}
    if whole == 0:
        weights = dict.fromkeys(weights, Decimal(1))
        whole = Decimal(len(weights))
    raw = {k: Decimal(cents) * w / whole for k, w in weights.items()}
    floors = {k: int(v) for k, v in raw.items()}
    left = cents - sum(floors.values())
    for key in sorted(raw, key=lambda k: (-(raw[k] - floors[k]), k))[:left]:
        floors[key] += 1
    return {k: Decimal(v) * CENT for k, v in floors.items()}


# ---------------------------------------------------------------------------- YAML, flat shapes


def strip_comment(line: str) -> str:
    quote = ""
    for i, char in enumerate(line):
        if quote:
            quote = "" if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def scalar(text: str) -> Any:
    value = text.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        return [scalar(part) for part in value[1:-1].split(",") if part.strip()]
    if value in ("null", "~", ""):
        return None
    return value


KEY = re.compile(r"""^("[^"]*"|'[^']*'|[^\s"'#:-][^:]*?|-[^\s:][^:]*?)\s*:(\s+|$)""")


def parse_yaml(text: str) -> Any:
    """Mappings, lists, lists of mappings and flow lists, nested by indentation: the flat shapes job files use."""
    lines: list[list[Any]] = []
    for raw in text.splitlines():
        line = strip_comment(raw).rstrip()
        if line.strip() and line.strip() not in ("---", "..."):
            lines.append([len(line) - len(line.lstrip(" ")), line.strip()])
    if not lines:
        return None
    value, _ = _block(lines, 0, lines[0][0])
    return value


def _is_item(line: list[Any]) -> bool:
    return bool(line[1] == "-" or str(line[1]).startswith("- "))


def _block(lines: list[list[Any]], i: int, indent: int) -> tuple[Any, int]:
    if _is_item(lines[i]):
        return _list(lines, i, indent)
    if not KEY.match(lines[i][1]):
        return scalar(lines[i][1]), i + 1
    return _map(lines, i, indent)


def _map(lines: list[list[Any]], i: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while i < len(lines) and lines[i][0] == indent and not _is_item(lines[i]):
        match = KEY.match(lines[i][1])
        if not match:
            i += 1
            continue
        key = str(scalar(match.group(1)))
        rest = lines[i][1][match.end() :].strip()
        i += 1
        if rest and rest not in ("|", ">", "|-", ">-"):
            result[key] = scalar(rest)
        elif i < len(lines) and (lines[i][0] > indent or (lines[i][0] == indent and _is_item(lines[i]))):
            result[key], i = _block(lines, i, lines[i][0])
        else:
            result[key] = None
    return result, i


def _list(lines: list[list[Any]], i: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while i < len(lines) and lines[i][0] == indent and _is_item(lines[i]):
        content = lines[i][1][1:].strip()
        if not content:
            i += 1
            if i < len(lines) and lines[i][0] > indent:
                value, i = _block(lines, i, lines[i][0])
                items.append(value)
            else:
                items.append(None)
        elif KEY.match(content):
            lines[i] = [indent + 2, content]
            value, i = _map(lines, i, indent + 2)
            items.append(value)
        else:
            items.append(scalar(content))
            i += 1
    return items, i


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [part for part in re.split(r"[;,\s]+", str(value)) if part]


# ---------------------------------------------------------------------------- cron


@dataclass
class Cron:
    minutes: list[int]
    hours: list[int]
    days: set[int]
    months: set[int]
    weekdays: set[int]
    any_day: bool
    any_weekday: bool

    def runs_on(self, day: date) -> int:
        if day.month not in self.months:
            return 0
        weekday = (day.weekday() + 1) % 7
        on_weekday = weekday in self.weekdays or (weekday == 0 and 7 in self.weekdays)
        on_day = day.day in self.days
        if self.any_day and self.any_weekday:
            hit = True
        elif self.any_day:
            hit = on_weekday
        elif self.any_weekday:
            hit = on_day
        else:
            hit = on_day or on_weekday
        return len(self.minutes) * len(self.hours) if hit else 0


MACROS = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
}
NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
    "sun": 0,
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
}


def cron_field(text: str, low: int, high: int) -> list[int]:
    values: set[int] = set()
    for part in text.lower().split(","):
        base, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if base in ("*", "?"):
            start, end = low, high
        elif "-" in base:
            first, last = base.split("-", 1)
            start, end = int(NAMES.get(first, first)), int(NAMES.get(last, last))
        else:
            start = int(NAMES.get(base, base))
            end = high if step_text else start
        if not low <= start <= end <= high or step < 1:
            raise ValueError(part)
        values.update(range(start, end + 1, step))
    return sorted(values)


def parse_cron(text: str) -> Cron | None:
    expr = MACROS.get(text.strip().lower(), text.strip())
    parts = expr.split()
    if len(parts) != 5:
        return None
    try:
        minutes = cron_field(parts[0], 0, 59)
        hours = cron_field(parts[1], 0, 23)
        days = set(cron_field(parts[2], 1, 31))
        months = set(cron_field(parts[3], 1, 12))
        weekdays = set(cron_field(parts[4], 0, 7))
    except ValueError:
        return None
    return Cron(minutes, hours, days, months, weekdays, parts[2] in ("*", "?"), parts[4] in ("*", "?"))


def runs_between(cron: Cron, first: date, last: date) -> int:
    total, day = 0, first
    while day <= last:
        total += cron.runs_on(day)
        day += timedelta(days=1)
    return total


# ---------------------------------------------------------------------------- the platform


@dataclass
class Job:
    name: str
    file: str
    schedule: str | None = None
    schedule_line: int | None = None
    cluster: str | None = None
    depends_on: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    sql_files: list[str] = field(default_factory=list)
    enabled: bool = True
    record_runs: str | None = None
    full_evidence: list[str] = field(default_factory=list)


def line_of(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text, re.M)
    return text.count("\n", 0, match.start()) + 1 if match else None


def load_jobs(root: Path, folder: Path | None) -> list[Job]:
    jobs: list[Job] = []
    for path in walk(folder or root, {".yaml", ".yml"}):
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            data = parse_yaml(text)
        except (ValueError, IndexError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("schedule", data.get("cron")), str):
            continue
        job = Job(name=str(data.get("name") or path.stem), file=rel(path, root))
        job.schedule = str(data.get("schedule", data.get("cron")))
        job.schedule_line = line_of(text, r"^\s*(schedule|cron)\s*:")
        cluster = next(
            (data[k] for k in ("cluster", "warehouse", "compute", "pool", "cluster_name") if k in data), None
        )
        job.cluster = str(cluster) if cluster else None
        job.depends_on = [str(d) for d in as_list(data.get("depends_on", data.get("upstream")))]
        job.enabled = str(data.get("enabled", "true")).lower() not in ("false", "no", "0")
        job.record_runs = str(data["record_runs"]) if data.get("record_runs") else None
        for step in as_list(data.get("steps", data.get("tasks"))):
            if not isinstance(step, dict):
                continue
            for key in ("task", "table", "target", "model", "output"):
                value = step.get(key)
                if isinstance(value, str) and "." in value and "/" not in value:
                    job.tables.append(table_key(value))
                    break
            for key in ("sql", "query_file", "file"):
                if isinstance(step.get(key), str) and str(step[key]).endswith(".sql"):
                    job.sql_files.append(str(step[key]))
        for key in ("table", "target"):
            if isinstance(data.get(key), str) and "." in data[key]:
                job.tables.append(table_key(data[key]))
        for match in FULL_KEYS.finditer(text):
            job.full_evidence.append(f"{job.file}:{text.count(chr(10), 0, match.start()) + 1}")
        jobs.append(job)
    return jobs


def clean_sql(text: str) -> str:
    """Comments and string literals blanked out, keeping every line where it was."""

    def blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    return re.sub(r"--[^\n]*|/\*.*?\*/|'(?:[^']|'')*'", blank, text, flags=re.S)


@dataclass
class SqlFacts:
    writes: dict[str, list[tuple[str, int, str]]] = field(default_factory=lambda: defaultdict(list))
    reads: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    comments: dict[str, list[str]] = field(default_factory=dict)


def scan_sql(root: Path) -> tuple[SqlFacts, int]:
    facts = SqlFacts()
    files = walk(root, {".sql"}) if root.is_dir() else []
    for path in files:
        name = rel(path, root)
        raw = path.read_text(encoding="utf-8", errors="replace")
        clean = clean_sql(raw)
        facts.comments[name] = [line[2:].strip() for line in raw.splitlines()[:12] if line.startswith("--")][:6]
        deletes = set()
        for kind, pattern in WRITES:
            for match in pattern.finditer(clean):
                table = table_key(match.group(1))
                facts.writes[table].append((name, clean.count("\n", 0, match.start()) + 1, kind))
                if kind == "delete":
                    deletes.add(match.start(1))
        for match in READS.finditer(clean):
            table = table_key(match.group(2))
            if match.start(2) not in deletes and table.split(".")[0] not in SYSTEM_SCHEMAS:
                facts.reads[table].add(name)
    return facts, len(files)


def mask(name: str, labels: dict[str, str]) -> str:
    if EMAIL.search(name):
        labels.setdefault(name, f"user-{len(labels) + 1} (e-mail hidden)")
        return labels[name]
    return name


# ---------------------------------------------------------------------------- the breakdown


def breakdown(
    root: Path, sources: dict[str, Source], jobs: list[Job], changed_below: Decimal, rates: dict[str, Decimal]
) -> dict[str, Any]:
    sql, sql_count = scan_sql(root)
    usage = sources.get("usage")
    storage = sources.get("storage")
    queries = sources.get("queries")
    runs = sources.get("runs")
    by_name = {j.name.lower(): j for j in jobs}
    labels: dict[str, str] = {}

    # Usage: compute per resource and day.
    eur: dict[str, Decimal] = defaultdict(Decimal)
    hours: dict[str, Decimal] = defaultdict(Decimal)
    days_billed: dict[str, set[date]] = defaultdict(set)
    full_days: dict[str, int] = defaultdict(int)
    weekend: dict[str, list[Decimal]] = defaultdict(list)
    kind: dict[str, str] = {}
    cluster_of: dict[str, str] = {}
    dates: set[date] = set()
    currency = None
    if usage:
        cost_column = usage.fields.get("cost", "")
        currency = next((c.upper() for c in ("eur", "usd", "gbp", "chf") if c in cost_column), None)
        for row in usage.rows:
            day = to_date(usage.get(row, "date"))
            resource = usage.get(row, "resource") or usage.get(row, "cluster")
            if day is None or not resource:
                continue
            cluster = usage.get(row, "cluster")
            hour = to_decimal(usage.get(row, "hours")) or Decimal(0)
            cost = to_decimal(usage.get(row, "cost"))
            if cost is None:
                cost = hour * rates.get(cluster, rates.get(resource, Decimal(0)))
            currency = currency or (usage.get(row, "currency").upper() or None)
            dates.add(day)
            eur[resource] += cost
            hours[resource] += hour
            days_billed[resource].add(day)
            if hour >= Decimal("23.99"):
                full_days[resource] += 1
            if day.weekday() >= 5:
                weekend[resource].append(cost)
            typed = usage.get(row, "type").lower()
            if typed:
                kind[resource] = typed
            elif resource.lower() in by_name:
                kind[resource] = "job"
            elif resource == cluster:
                kind[resource] = "cluster"
            else:
                kind.setdefault(resource, "other")
            if cluster:
                cluster_of[resource] = cluster
    compute_total = sum(eur.values(), Decimal(0))

    # Query log: reads per table.
    reads: dict[str, int] = defaultdict(int)
    reads_a_day: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    consumers: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    query_dates: set[date] = set()
    if queries:
        for row in queries.rows:
            table = table_key(queries.get(row, "table"))
            day = to_date(queries.get(row, "date"))
            if not table or day is None:
                continue
            count = int(to_decimal(queries.get(row, "count")) or 1) if "count" in queries.fields else 1
            reads[table] += count
            reads_a_day[table][day] += count
            consumers[table][mask(queries.get(row, "consumer"), labels)] += count
            query_dates.add(day)

    # Run records: per job and task.
    task_seconds: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    reload_runs: dict[str, list[tuple[int, int]]] = defaultdict(list)
    run_counts: dict[str, int] = defaultdict(int)
    if runs:
        seen_runs: set[tuple[str, str]] = set()
        for row in runs.rows:
            job_name = runs.get(row, "job")
            status = runs.get(row, "status").lower()
            run_id = runs.get(row, "run") or f"{job_name}-{runs.get(row, 'start')}"
            if (job_name, run_id) not in seen_runs:
                seen_runs.add((job_name, run_id))
                run_counts[job_name] += 1
            if status not in ("", "success", "succeeded", "ok", "warning", "done", "completed"):
                continue
            task = runs.get(row, "task")
            start, end = to_datetime(runs.get(row, "start")), to_datetime(runs.get(row, "end"))
            if task and "." in task and start and end:
                task_seconds[job_name][table_key(task)] += Decimal((end - start).total_seconds())
            rows_out = to_decimal(runs.get(row, "written"))
            rows_new = to_decimal(runs.get(row, "changed"))
            if rows_out and rows_out > 0 and rows_new is not None:
                reload_runs[f"{job_name}\t{table_key(task) if task else ''}"].append((int(rows_out), int(rows_new)))

    # The period: the usage dates, else the query log's.
    period = sorted(dates or query_dates)
    first, last = (period[0], period[-1]) if period else (None, None)
    span = (last - first).days + 1 if first and last else 0

    # Jobs: tables, runs a day, pipelines.
    sql_users: dict[str, set[str]] = defaultdict(set)
    for job in jobs:
        for name in job.sql_files:
            sql_users[name].add(job.name)
        for table, places in sql.writes.items():
            if any(p[0] in job.sql_files for p in places) and table not in job.tables:
                job.tables.append(table)
        for table in job.tables:
            for name, line, how in sql.writes.get(table, []):
                if how in FULL_KINDS and (name in job.sql_files or not job.sql_files):
                    job.full_evidence.append(f"{name}:{line}")
        job.full_evidence = sorted(set(job.full_evidence))
    runs_a_day: dict[str, Decimal] = {}
    runs_in_period: dict[str, int] = {}
    for job in jobs:
        cron = parse_cron(job.schedule or "")
        if cron and first and last and job.enabled:
            runs_in_period[job.name] = runs_between(cron, first, last)
            runs_a_day[job.name] = Decimal(runs_in_period[job.name]) / Decimal(span)
    parent = {j.name: j.name for j in jobs}

    def root_of(name: str) -> str:
        while parent[name] != name:
            name = parent[name]
        return name

    for job in jobs:
        for dep in job.depends_on:
            if dep in parent:
                parent[root_of(job.name)] = root_of(dep)
    pipelines: dict[str, list[str]] = defaultdict(list)
    for job in jobs:
        pipelines[root_of(job.name)].append(job.name)

    # Compute per job and its split over tables.
    table_compute: dict[str, Decimal] = defaultdict(Decimal)
    by_job: list[dict[str, Any]] = []
    no_table = Decimal(0)
    for resource in sorted(eur, key=lambda r: (-eur[r], r)):
        job_def = by_name.get(resource.lower())
        if kind.get(resource) == "cluster" or (job_def is None and kind.get(resource) != "job"):
            continue
        tables = list(dict.fromkeys(job_def.tables)) if job_def else []
        seconds = task_seconds.get(resource, {})
        weights = {t: seconds.get(t, Decimal(0)) for t in tables}
        method = "run time" if any(weights.values()) else "even split"
        parts = allocate(eur[resource], weights) if tables else {}
        for table, part in parts.items():
            table_compute[table] += part
        if not tables:
            no_table += eur[resource]
        by_job.append(
            {
                "job": resource,
                "cluster": cluster_of.get(resource) or (job_def.cluster if job_def else None),
                "hours": str(hours[resource]),
                "eur": money(eur[resource]),
                "days_billed": len(days_billed[resource]),
                "defined_in": job_def.file if job_def else None,
                "enabled": job_def.enabled if job_def else None,
                "schedule": job_def.schedule if job_def else None,
                "runs_in_period": runs_in_period.get(resource),
                "run_records": run_counts.get(resource, 0),
                "record_runs": job_def.record_runs if job_def else None,
                "tables": {t: money(v) for t, v in parts.items()},
                "split": method if tables else "no table known",
            }
        )
    for job in jobs:
        if job.name not in eur and job.name.lower() not in {r.lower() for r in eur}:
            by_job.append(
                {
                    "job": job.name,
                    "eur": "0.00",
                    "defined_in": job.file,
                    "enabled": job.enabled,
                    "schedule": job.schedule,
                    "note": "defined but not in the usage export",
                }
            )

    # Clusters.
    jobs_on: dict[str, set[str]] = defaultdict(set)
    for job in jobs:
        if job.cluster:
            jobs_on[job.cluster].add(job.name)
    billed_jobs_on: dict[str, set[str]] = defaultdict(set)
    for resource, cluster in cluster_of.items():
        if kind.get(resource) != "cluster":
            billed_jobs_on[cluster].add(resource)
    clusters: dict[str, Decimal] = defaultdict(Decimal)
    for resource, value in eur.items():
        clusters[cluster_of.get(resource) or resource] += value
    by_cluster: list[dict[str, Any]] = []
    without_jobs: list[dict[str, Any]] = []
    for name in sorted(clusters, key=lambda c: (-clusters[c], c)):
        cluster_rows = [r for r in eur if kind.get(r) == "cluster" and (cluster_of.get(r) or r) == name]
        cluster_hours = sum((hours[r] for r in cluster_rows), Decimal(0))
        job_hours = sum((hours[r] for r in billed_jobs_on[name]), Decimal(0))
        rate = None
        all_hours = sum((hours[r] for r in eur if (cluster_of.get(r) or r) == name), Decimal(0))
        if all_hours:
            rate = money(clusters[name] / all_hours)
        entry = {
            "cluster": name,
            "eur": money(clusters[name]),
            "eur_per_hour": rate,
            "jobs_defined": sorted(jobs_on.get(name, set())),
            "jobs_billed": sorted(billed_jobs_on.get(name, set())),
            "cluster_hours": str(cluster_hours) if cluster_rows else None,
            "job_hours": str(job_hours),
        }
        by_cluster.append(entry)
        if cluster_rows and not jobs_on.get(name) and not billed_jobs_on.get(name):
            cost = sum((eur[r] for r in cluster_rows), Decimal(0))
            weekend_costs = [c for r in cluster_rows for c in weekend[r]]
            without_jobs.append(
                {
                    "cluster": name,
                    "hours": str(cluster_hours),
                    "eur": money(cost),
                    "eur_per_hour": rate,
                    "days_billed": len({d for r in cluster_rows for d in days_billed[r]}),
                    "days_up_24_hours": sum(full_days[r] for r in cluster_rows),
                    "weekend_days_billed": len(weekend_costs),
                    "weekend_eur": money(sum(weekend_costs, Decimal(0))),
                    "jobs_defined": 0,
                    "jobs_billed": 0,
                    "period_days": span,
                }
            )

    # Storage per table.
    gb: dict[str, Decimal] = {}
    storage_eur: dict[str, Decimal] = {}
    layer: dict[str, str] = {}
    if storage:
        for row in storage.rows:
            table = table_key(storage.get(row, "table"))
            if not table:
                continue
            size = to_decimal(storage.get(row, "gb"))
            if size is None and (raw := to_decimal(storage.get(row, "bytes"))) is not None:
                size = raw / Decimal(10**9)
            gb[table] = gb.get(table, Decimal(0)) + (size or Decimal(0))
            storage_eur[table] = storage_eur.get(table, Decimal(0)) + (
                to_decimal(storage.get(row, "cost")) or Decimal(0)
            )
            layer[table] = storage.get(row, "layer") or table.split(".")[0]
    storage_total = sum(storage_eur.values(), Decimal(0))
    month_like = 28 <= span <= 31
    storage_in_period = storage_total if month_like or not span else storage_total * Decimal(span) / Decimal(30)

    # Readers of each table.
    def readers(table: str) -> dict[str, Any]:
        sql_readers = sorted(f for f in sql.reads.get(table, set()) if not any(w[0] == f for w in sql.writes[table]))
        reader_jobs = sorted({j for f in sql_readers for j in sql_users.get(f, set())})
        per_day = reads_a_day.get(table, {})
        return {
            "consumer_queries": reads.get(table, 0),
            "consumers": len(consumers.get(table, {})),
            "consumer_days": len(per_day),
            "consumer_max_a_day": max(per_day.values(), default=0),
            "read_by_sql": sql_readers,
            "read_by_jobs": reader_jobs,
            "reader_runs_a_day": max((runs_a_day.get(j, Decimal(0)) for j in reader_jobs), default=Decimal(0)),
        }

    all_tables = sorted(set(gb) | set(table_compute) | {t for j in jobs for t in j.tables})
    by_table: list[dict[str, Any]] = []
    for table in all_tables:
        info = readers(table)
        total = table_compute.get(table, Decimal(0)) + storage_eur.get(table, Decimal(0))
        by_table.append(
            {
                "table": table,
                "layer": layer.get(table, table.split(".")[0]),
                "gb": str(gb[table]) if table in gb else None,
                "storage_eur_per_month": money(storage_eur[table]) if table in storage_eur else None,
                "compute_eur": money(table_compute.get(table, Decimal(0))),
                "total_eur": money(total),
                "consumer_queries": info["consumer_queries"],
                "consumers": sorted(consumers.get(table, {})),
                "read_by_sql": len(info["read_by_sql"]),
                "eur_per_consumer_query": money(total / info["consumer_queries"]) if info["consumer_queries"] else None,
            }
        )
    by_table.sort(key=lambda t: (-Decimal(t["total_eur"]), t["table"]))

    # Candidates.
    unread: list[dict[str, Any]] = []
    for table in sorted(gb, key=lambda t: (-storage_eur.get(t, Decimal(0)), -gb[t], t)):
        info = readers(table)
        if info["consumer_queries"] or info["read_by_sql"]:
            continue
        places = sorted(sql.writes.get(table, []), key=lambda w: (w[0], w[1]))
        unread.append(
            {
                "table": table,
                "gb": str(gb[table]),
                "eur_per_month": money(storage_eur.get(table, Decimal(0))),
                "compute_eur": money(table_compute.get(table, Decimal(0))),
                "queries": 0,
                "written_by_jobs": sorted(j.name for j in jobs if table in j.tables),
                "defined_in": [f"{f}:{n}" for f, n, _ in places[:3]],
                "notes": sql.comments.get(places[0][0], []) if places else [],
            }
        )
    reloads: list[dict[str, Any]] = []
    for job in jobs:
        if not job.full_evidence:
            continue
        for table in job.tables or [""]:
            records = reload_runs.get(f"{job.name}\t{table}", [])
            written_rows = sum(w for w, _ in records)
            changed_rows = sum(c for _, c in records)
            max_share = max((Decimal(c) / Decimal(w) for w, c in records), default=None)
            reloads.append(
                {
                    "job": job.name,
                    "table": table or None,
                    "evidence": job.full_evidence,
                    "eur": money(eur.get(job.name, Decimal(0))),
                    "runs": len(records),
                    "rows_written": written_rows,
                    "rows_changed": changed_rows,
                    "changed_percent": share(changed_rows, written_rows),
                    "max_changed_a_run": max((c for _, c in records), default=None),
                    "max_changed_percent_a_run": str((max_share * 100).quantize(SHARE_PLACES)) if max_share else None,
                    "barely_changes": bool(records) and max_share is not None and max_share < changed_below,
                    "note": None if records else "no run records with rows written and rows changed",
                }
            )
    frequent: list[dict[str, Any]] = []
    for job in jobs:
        if job.name not in runs_a_day or not job.tables:
            continue
        table_rows: list[dict[str, Any]] = []
        for table in job.tables:
            info = readers(table)
            table_rows.append(
                {
                    "table": table,
                    "consumer_queries": info["consumer_queries"],
                    "consumer_days": info["consumer_days"],
                    "consumer_max_a_day": info["consumer_max_a_day"],
                    "read_by_jobs": info["read_by_jobs"],
                    "reader_runs_a_day": str(info["reader_runs_a_day"].quantize(SHARE_PLACES)),
                }
            )
        most = max(
            (Decimal(t["consumer_max_a_day"]) + Decimal(t["reader_runs_a_day"]) for t in table_rows), default=Decimal(0)
        )
        cost = eur.get(job.name, Decimal(0))
        count = runs_in_period[job.name]
        frequent.append(
            {
                "job": job.name,
                "schedule": job.schedule,
                "where": f"{job.file}:{job.schedule_line}",
                "runs_a_day": str(runs_a_day[job.name].quantize(SHARE_PLACES)),
                "runs_in_period": count,
                "eur": money(cost),
                "eur_per_run": str((cost / count).quantize(Decimal("0.0001"))) if count else None,
                "most_reads_a_day": str(most.quantize(SHARE_PLACES)),
                "tables": table_rows,
                "faster_than_reads": most > 0 and runs_a_day[job.name] > most,
            }
        )

    attributed = sum(table_compute.values(), Decimal(0))
    cluster_only = sum((eur[r] for r in eur if kind.get(r) == "cluster"), Decimal(0))
    other = compute_total - attributed - cluster_only
    pipeline_rows: list[dict[str, Any]] = []
    for members in pipelines.values():
        cost = sum((eur.get(m, Decimal(0)) for m in members), Decimal(0))
        pipeline_rows.append({"pipeline": " + ".join(members), "jobs": members, "eur": money(cost)})
    pipeline_rows.sort(key=lambda p: (-Decimal(p["eur"]), p["pipeline"]))
    return {
        "period": {
            "from": first.isoformat() if first else None,
            "to": last.isoformat() if last else None,
            "days": span,
            "days_in_usage": len(dates),
            "storage_counted_as": "one month" if month_like else f"{span} of 30 days",
        },
        "currency": currency,
        "totals": {
            "compute_eur": money(compute_total),
            "storage_eur_per_month": money(storage_total),
            "storage_gb": str(sum(gb.values(), Decimal(0))),
            "storage_eur_in_period": money(storage_in_period),
            "total_eur": money(compute_total + storage_in_period),
        },
        "adds_up": {
            "compute_on_tables": money(attributed),
            "compute_clusters_without_job_rows": money(cluster_only),
            "compute_jobs_without_tables": money(other),
            "equals_compute_total": attributed + cluster_only + other == compute_total and other == no_table,
        },
        "by_cluster": by_cluster,
        "by_job": by_job,
        "by_pipeline": pipeline_rows,
        "by_table": by_table,
        "candidates": {
            "unread_tables": unread,
            "full_reloads": reloads,
            "schedules": frequent,
            "compute_without_jobs": without_jobs,
        },
        "sql_files": sql_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", type=Path, help="the platform's repository or a folder with its exports")
    parser.add_argument("--usage", type=Path, help="usage or billing export")
    parser.add_argument("--storage", type=Path, help="table sizes and storage cost")
    parser.add_argument("--queries", type=Path, help="query log")
    parser.add_argument("--runs", type=Path, help="run records")
    parser.add_argument("--jobs", type=Path, help="folder of job definitions (YAML)")
    parser.add_argument(
        "--changed-below",
        type=Decimal,
        default=Decimal("0.001"),
        help="a full reload barely changes its table when every run changes fewer rows than this share",
    )
    parser.add_argument(
        "--rate",
        action="append",
        default=[],
        metavar="CLUSTER=PRICE",
        help="price per compute hour, used when the export has hours but no cost",
    )
    args = parser.parse_args(argv)
    root = args.repo.resolve()
    if not root.exists():
        raise SystemExit(f"not found: {root}")
    rates: dict[str, Decimal] = {}
    for item in args.rate:
        name, _, price = item.partition("=")
        value = to_decimal(price)
        if not name or value is None:
            raise SystemExit(f"--rate wants CLUSTER=PRICE, got {item!r}")
        rates[name] = value
    given = {"usage": args.usage, "storage": args.storage, "queries": args.queries, "runs": args.runs}
    sources = find_sources(root, given)
    jobs = load_jobs(root, args.jobs)
    result: dict[str, Any] = {
        "inputs": {
            **{
                role: {"file": rel(s.path, root), "rows": len(s.rows), "fields": s.fields}
                for role, s in sorted(sources.items())
            },
            "jobs": {"files": len(jobs), "names": sorted(j.name for j in jobs)},
            "not_found": sorted(set(ROLES) - set(sources)) + ([] if jobs else ["jobs"]),
        }
    }
    result.update(breakdown(root, sources, jobs, args.changed_below, rates))
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
