#!/usr/bin/env python3
"""Inventory an old estate of scheduled jobs: last run against schedule, what each script reads and writes, and the
links, copies, clashes and outside consumers a migration has to plan for.

Usage: python3 estate_inventory.py INVENTORY [--scripts FOLDER] [--as-of "YYYY-MM-DD HH:MM"]
                                             [--dead-after DAYS] [--grace MINUTES] [--window MINUTES]

INVENTORY is a job inventory (CSV, TSV, JSON Lines or a JSON array: a job, its script, a cron schedule, and
optionally the owner, the last run, the target and the jobs it depends on; names match case-insensitively with
common aliases), a crontab file, or a folder holding one. Scripts are found relative to the inventory, then under
--scripts. --as-of defaults to the latest last run in the inventory.

Per job: the schedule's cadence, the last time it was due, the runs missed since its last run and a status (on
schedule, missed, stopped, dead: stopped and silent for more than --dead-after days); the tables and file paths its
script reads and writes, outside hosts it sends to or fetches from, the environment variables it reads, and
credentials, shown only as their ${VAR} placeholder or as hidden. For the estate: identical scripts, data links
between jobs (a path or table one writes and another reads) with whether the inventory declares them, jobs that
write the same target with the minutes between their start times, inputs from outside the estate, outputs nobody
inside reads, connected groups and an order that respects every link, for planning waves.

A value that looks like an e-mail address is never printed. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import io
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

DATA_SUFFIXES = {".csv", ".tsv", ".jsonl", ".ndjson", ".json"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__"}
SCRIPT_SUFFIXES = {".sh", ".bash", ".sql", ".py", ".pl", ".ps1", ".ksh", ".hql"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
FIELDS: dict[str, list[str]] = {
    "job": ["job", "job_name", "name", "task", "id"],
    "script": ["script", "script_path", "command", "cmd", "path", "file"],
    "schedule": ["schedule", "cron", "cron_expression", "crontab", "frequency"],
    "owner": ["owner", "owner_on_record", "contact", "maintainer", "responsible", "team"],
    "last_run": [
        "last_run",
        "last_success",
        "last_successful_run",
        "last_run_at",
        "last_run_time",
        "last_execution",
        "last_ok",
    ],
    "target": ["target", "writes", "output", "destination", "target_table", "output_table"],
    "depends_on": ["depends_on", "dependencies", "upstream", "after", "predecessors", "requires"],
    "enabled": ["enabled", "active", "status", "state"],
}
TEMP = ("/tmp/", "/var/tmp/", "/dev/")
SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "sys"}
QNAME = r'[A-Za-z_"`\[][\w"`\[\]$]*(?:\.[\w"`\[\]$*]+)+'
TABLE_WRITES = [
    re.compile(
        rf"(?is)\bcreate\s+(?:or\s+replace\s+)?(?:temp(?:orary)?\s+)?table\s+(?:if\s+not\s+exists\s+)?({QNAME})"
    ),
    re.compile(rf"(?is)\binsert\s+(?:into|overwrite)\s+(?:table\s+)?({QNAME})"),
    re.compile(rf"(?is)\btruncate\s+(?:table\s+)?({QNAME})"),
    re.compile(rf"(?is)\bmerge\s+into\s+({QNAME})"),
    re.compile(rf"(?is)\bupdate\s+({QNAME})\s+set\b"),
    re.compile(rf"(?is)\bdelete\s+from\s+({QNAME})"),
    re.compile(rf"(?is)\bdrop\s+table\s+(?:if\s+exists\s+)?({QNAME})"),
    re.compile(rf"(?is)\\?\bcopy\s+({QNAME})\s*(?:\([^)]*\))?\s+from\b"),
]
TABLE_READS = re.compile(rf"(?is)(?<!delete\s)\b(?:from|join)\s+({QNAME})")
COPY_TO = re.compile(rf"(?is)\\?\bcopy\s+({QNAME})\s*(?:\([^)]*\))?\s+to\b")
PATH = re.compile(r"""(?<![\w$}/.:])(/(?:[\w.*-]+/?)+)""")
URL = re.compile(
    r"\b(sftp|ftps?|https?|s3a?|gs|abfss?|wasbs?|smb|scp)://(?:[^/\s@'\"]+@)?([\w.-]+)(?::\d+)?(/[^\s'\"<>]*)?", re.I
)
SECRETS = [
    re.compile(r"""-u\s+["']?([^"'\s,:]+)[,:]([^"'\s@]+)["']?"""),
    re.compile(r"://([^/\s:@]+):([^@\s/]+)@"),
    re.compile(r"""(?i)\b(?:password|passwd|pwd|secret|token|api_?key|pgpassword)\s*[=:]\s*["']?([^"'\s;&]+)"""),
]
ENV = re.compile(r"\$\{?([A-Z][A-Z0-9_]*)\}?")
UPLOAD = re.compile(r"(?i)\b(put|mput|upload|--upload-file|-T)\b|-X\s*(POST|PUT)\b")


# ---------------------------------------------------------------------------- reading


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def table_key(name: str) -> str:
    return ".".join(re.sub(r'["`\[\]]', "", name.strip()).lower().split(".")[-2:])


def read_rows(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if path.suffix.lower() in (".jsonl", ".ndjson"):
        records = [json.loads(line) for line in text.splitlines() if line.strip().startswith("{")]
    elif path.suffix.lower() == ".json":
        data = json.loads(text)
        records = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])
    else:
        first = text.split("\n", 1)[0]
        delimiter = max(",;\t|", key=first.count)
        return [
            {norm(k): (v or "") for k, v in r.items() if k}
            for r in csv.DictReader(io.StringIO(text), delimiter=delimiter)
        ]
    rows: list[dict[str, str]] = []
    for record in records:
        if isinstance(record, dict):
            rows.append(
                {
                    norm(str(k)): ";".join(map(str, v)) if isinstance(v, list) else ("" if v is None else str(v))
                    for k, v in record.items()
                }
            )
    return rows


def pick(columns: Iterable[str], aliases: Sequence[str]) -> str | None:
    present = set(columns)
    return next((a for a in aliases if a in present), None)


def read_crontab(path: Path) -> list[dict[str, str]]:
    rows = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", line):
            continue
        parts = line.split(None, 1 if line.startswith("@") else 5)
        if len(parts) < (2 if line.startswith("@") else 6):
            continue
        schedule = parts[0] if line.startswith("@") else " ".join(parts[:5])
        command = parts[-1]
        found = re.search(r"(\S+\.(?:sh|bash|sql|py|pl|ps1|ksh|hql))\b", command)
        script = found.group(1) if found else ""
        name = Path(script).stem if script else command.split()[0].rsplit("/", 1)[-1]
        rows.append({"job": name, "script": script, "schedule": schedule})
    return rows


@dataclass
class Inventory:
    path: Path
    kind: str
    fields: dict[str, str]
    rows: list[dict[str, str]]


def find_inventory(target: Path) -> Inventory:
    candidates = (
        [target]
        if target.is_file()
        else sorted(p for p in target.rglob("*") if p.is_file() and not set(p.parts) & SKIP_DIRS)
    )
    for path in candidates:
        if path.suffix.lower() in DATA_SUFFIXES:
            try:
                rows = read_rows(path)
            except (ValueError, UnicodeError):
                continue
            columns = list(rows[0]) if rows else []
            fields = {f: c for f, aliases in FIELDS.items() if (c := pick(columns, aliases))}
            if "schedule" in fields and ("job" in fields or "script" in fields):
                return Inventory(path, "table", fields, rows)
        elif path.name in ("crontab", "cron") or path.suffix.lower() in (".cron", ".crontab"):
            rows = read_crontab(path)
            if rows:
                return Inventory(path, "crontab", {"job": "job", "script": "script", "schedule": "schedule"}, rows)
    raise SystemExit(f"no job inventory found in {target}: need a job or script column and a schedule column")


# ---------------------------------------------------------------------------- cron


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
WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


@dataclass
class Cron:
    minutes: list[int]
    hours: list[int]
    days: set[int]
    months: set[int]
    weekdays: set[int]
    any_day: bool
    any_weekday: bool

    def runs_on(self, day: date) -> bool:
        if day.month not in self.months:
            return False
        weekday = (day.weekday() + 1) % 7
        on_weekday = weekday in self.weekdays or (weekday == 0 and 7 in self.weekdays)
        on_day = day.day in self.days
        if self.any_day and self.any_weekday:
            return True
        if self.any_day:
            return on_weekday
        if self.any_weekday:
            return on_day
        return on_day or on_weekday

    def times_on(self, day: date) -> list[datetime]:
        if not self.runs_on(day):
            return []
        return [datetime(day.year, day.month, day.day, h, m) for h in self.hours for m in self.minutes]


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
    parts = MACROS.get(text.strip().lower(), text.strip()).split()
    if len(parts) != 5:
        return None
    try:
        return Cron(
            cron_field(parts[0], 0, 59),
            cron_field(parts[1], 0, 23),
            set(cron_field(parts[2], 1, 31)),
            set(cron_field(parts[3], 1, 12)),
            set(cron_field(parts[4], 0, 7)),
            parts[2] in ("*", "?"),
            parts[4] in ("*", "?"),
        )
    except ValueError:
        return None


def cadence(text: str, cron: Cron) -> str:
    parts = MACROS.get(text.strip().lower(), text.strip()).split()
    at = f"{cron.hours[0]:02d}:{cron.minutes[0]:02d}" if len(cron.hours) == 1 and len(cron.minutes) == 1 else None
    if parts[0].startswith("*/") and parts[1] == "*" and parts[2:] == ["*", "*", "*"]:
        return f"every {parts[0][2:]} minutes"
    if parts[0].startswith("*/") and parts[2:4] == ["*", "*"]:
        hours = f"{cron.hours[0]:02d}-{cron.hours[-1]:02d}h"
        return f"every {parts[0][2:]} minutes, {hours}" + (f", days {parts[4]}" if parts[4] != "*" else "")
    if at and cron.any_day and cron.any_weekday and len(cron.months) == 12:
        return f"daily {at}"
    if at and cron.any_day and len(cron.weekdays) == 1:
        return f"weekly {WEEKDAYS[next(iter(cron.weekdays)) % 7]} {at}"
    if at and cron.any_weekday and len(cron.days) == 1 and len(cron.months) == 12:
        return f"monthly on day {next(iter(cron.days))} {at}"
    return f"cron {' '.join(parts)}"


def last_due(cron: Cron, as_of: datetime) -> datetime | None:
    for back in range(0, 800):
        day = as_of.date() - timedelta(days=back)
        times = [t for t in cron.times_on(day) if t <= as_of]
        if times:
            return max(times)
    return None


def next_due(cron: Cron, as_of: datetime) -> datetime | None:
    for ahead in range(0, 800):
        times = [t for t in cron.times_on(as_of.date() + timedelta(days=ahead)) if t > as_of]
        if times:
            return min(times)
    return None


def missed_since(cron: Cron, last: datetime, until: datetime) -> int:
    count, day = 0, last.date()
    while day <= until.date():
        count += sum(1 for t in cron.times_on(day) if last < t <= until)
        day += timedelta(days=1)
    return count


def to_datetime(text: str) -> datetime | None:
    value = text.strip().replace("T", " ").replace("Z", "")
    for size, pattern in ((16, "%Y-%m-%d %H:%M"), (19, "%Y-%m-%d %H:%M:%S"), (10, "%Y-%m-%d")):
        try:
            return datetime.strptime(value[:size], pattern)
        except ValueError:
            continue
    match = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\.?(?:\s+(\d{1,2}):(\d{2}))?", value)
    if match:
        hour, minute = int(match[4] or 0), int(match[5] or 0)
        return datetime(int(match[3]), int(match[2]), int(match[1]), hour, minute)
    return None


# ---------------------------------------------------------------------------- scripts


def strip_comments(text: str, suffix: str) -> str:
    """Comments blanked out, line positions kept; for SQL, `--` and /* */, for shell and Python, `#` outside quotes."""

    def blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    if suffix in (".sql", ".hql"):
        return re.sub(r"--[^\n]*|/\*.*?\*/", blank, text, flags=re.S)
    lines = []
    for number, line in enumerate(text.splitlines()):
        quote, cut = "", len(line)
        for i, char in enumerate(line):
            if quote:
                quote = "" if char == quote else quote
            elif char in "\"'":
                quote = char
            elif char == "#" and (i == 0 or line[i - 1] in " \t") and not (number == 0 and line.startswith("#!")):
                cut = i
                break
        lines.append(line[:cut])
    return "\n".join(lines)


def hide_secrets(line: str) -> str:
    for pattern in SECRETS:
        for match in pattern.finditer(line):
            value = match.group(match.lastindex or 1)
            if not ENV.fullmatch(value):
                line = line.replace(value, "[hidden]")
    return EMAIL.sub("[e-mail]", line)


@dataclass
class Script:
    path: str
    lines: int
    sha: str
    normal: str
    reads_tables: set[str] = field(default_factory=set)
    writes_tables: set[str] = field(default_factory=set)
    reads_paths: set[str] = field(default_factory=set)
    writes_paths: set[str] = field(default_factory=set)
    outside: list[dict[str, Any]] = field(default_factory=list)
    env: set[str] = field(default_factory=set)
    credentials: list[dict[str, Any]] = field(default_factory=list)
    dynamic_sql: bool = False


def read_script(path: Path, shown: str) -> Script:
    raw = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    text = strip_comments(raw, suffix)
    normal = re.sub(r"\s+", " ", text).strip().lower()
    script = Script(shown, len(raw.splitlines()), hashlib.sha256(raw.encode()).hexdigest()[:12], normal)
    sql_text = re.sub(r"'(?:[^']|'')*'", lambda m: " " * len(m.group(0)), text) if suffix in (".sql", ".hql") else text
    for pattern in TABLE_WRITES:
        for match in pattern.finditer(sql_text):
            script.writes_tables.add(table_key(match.group(1)))
    for match in COPY_TO.finditer(sql_text):
        script.reads_tables.add(table_key(match.group(1)))
    for match in TABLE_READS.finditer(sql_text):
        table = table_key(match.group(1))
        if table.split(".")[0] not in SYSTEM_SCHEMAS and not re.search(r"\.(csv|txt|json|gz|zip|xml)$", table):
            script.reads_tables.add(table)
    script.dynamic_sql = bool(re.search(r"(?i)\bexecute\s+(format|immediate)\b|%I", text))
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in PATH.finditer(line):
            value = match.group(1)
            before = line[: match.start()]
            if re.search(r"(?:^|\s)cd\s+$", before) or value in ("/", "/bin/sh", "/bin/bash", "/usr/bin/env"):
                continue
            words = re.split(r"&&|\|\||[;|(]", before)[-1].split()
            command = next((w for w in words if not re.match(r"^[A-Z_][A-Z0-9_]*=", w)), "")
            if re.search(r"(>>?|\bto\s+'|-o\s+|--output[= ])\s*['\"]?$", before) or (
                command in ("cp", "mv", "rsync", "install") and line.rstrip().endswith(value)
            ):
                script.writes_paths.add(value)
            elif command != "rm":
                script.reads_paths.add(value)
        for match in URL.finditer(line):
            direction = "out" if UPLOAD.search(text) else "in" if re.search(r"(?i)\b(get|mget|wget)\b", text) else "?"
            script.outside.append(
                {
                    "scheme": match.group(1).lower(),
                    "host": match.group(2),
                    "line": line_no,
                    "direction": direction,
                    "evidence": hide_secrets(line.strip())[:200],
                }
            )
        if re.search(r"(?i)\b(mailx?|sendmail|mutt)\b", line):
            script.outside.append(
                {
                    "scheme": "e-mail",
                    "host": None,
                    "line": line_no,
                    "direction": "out",
                    "evidence": hide_secrets(line.strip())[:200],
                }
            )
        for pattern in SECRETS:
            for match in pattern.finditer(line):
                value = match.group(match.lastindex or 1)
                placeholder = value if ENV.fullmatch(value) else None
                script.credentials.append({"line": line_no, "placeholder": placeholder, "literal": placeholder is None})
    assigned = set(re.findall(r"(?m)^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)=", text))
    script.env = {name for name in ENV.findall(text) if name not in assigned}
    return script


def resolve_script(value: str, bases: list[Path]) -> Path | None:
    candidate = re.search(r"(\S+\.(?:sh|bash|sql|py|pl|ps1|ksh|hql))\b", value)
    name = candidate.group(1) if candidate else value.strip()
    if not name:
        return None
    for base in bases:
        path = (base / name) if not Path(name).is_absolute() else Path(name)
        if path.is_file():
            return path
    for base in bases:
        hits = sorted(p for p in base.rglob(Path(name).name) if p.is_file()) if base.is_dir() else []
        if hits:
            return hits[0]
    return None


# ---------------------------------------------------------------------------- the estate


def matches(written: str, read: str) -> bool:
    if written == read:
        return True
    if "*" in written and fnmatch.fnmatch(read, written):
        return True
    if "*" in read and fnmatch.fnmatch(written, read):
        return True
    return written.endswith("/") and read.startswith(written)


def shown(value: str) -> str:
    return "[e-mail]" if EMAIL.search(value) else value


def inventory(
    target: Path, scripts_dir: Path | None, as_of_text: str | None, dead_after: int, grace: int, window: int
) -> dict[str, Any]:
    inv = find_inventory(target)
    base = inv.path.parent
    bases = [base, *([scripts_dir] if scripts_dir else []), base.parent]

    def get(row: dict[str, str], name: str) -> str:
        return row.get(inv.fields.get(name, ""), "").strip()

    rows = [r for r in inv.rows if get(r, "job") or get(r, "script")]
    last_runs = {(get(r, "job") or Path(get(r, "script")).stem): to_datetime(get(r, "last_run")) for r in rows}
    if as_of_text:
        as_of = to_datetime(as_of_text)
        if as_of is None:
            raise SystemExit(f"--as-of: cannot read {as_of_text!r}")
        as_of_source = "--as-of"
    else:
        known = [t for t in last_runs.values() if t]
        if not known:
            raise SystemExit("the inventory has no last runs; give --as-of")
        as_of = max(known)
        as_of_source = "the latest last run in the inventory"

    jobs: dict[str, dict[str, Any]] = {}
    scripts: dict[str, Script] = {}
    used_scripts: set[Path] = set()
    for row in rows:
        name = get(row, "job") or Path(get(row, "script")).stem
        schedule = get(row, "schedule")
        cron = parse_cron(schedule)
        last = last_runs.get(name)
        entry: dict[str, Any] = {
            "job": name,
            "script": get(row, "script") or None,
            "schedule": schedule,
            "cadence": cadence(schedule, cron) if cron else "schedule not understood",
            "owner": shown(get(row, "owner")) or None,
            "last_run": last.isoformat(sep=" ", timespec="minutes") if last else None,
            "declared_target": get(row, "target") or None,
            "depends_on": [d for d in re.split(r"[;,|\s]+", get(row, "depends_on")) if d],
            "enabled": get(row, "enabled") or None,
        }
        if cron:
            due, upcoming = last_due(cron, as_of), next_due(cron, as_of)
            entry["last_due"] = due.isoformat(sep=" ", timespec="minutes") if due else None
            entry["next_due"] = upcoming.isoformat(sep=" ", timespec="minutes") if upcoming else None
            if last:
                until = as_of - timedelta(minutes=grace)
                missed = missed_since(cron, last, until) if last < until else 0
                days = (as_of.date() - last.date()).days
                entry["missed_runs"] = missed
                entry["days_since_last_run"] = days
                entry["status"] = (
                    "on schedule"
                    if missed == 0
                    else "missed"
                    if missed < 3
                    else "dead"
                    if days > dead_after
                    else "stopped"
                )
            else:
                entry["status"] = "no last run on record"
        else:
            entry["status"] = "schedule not understood"
        path = resolve_script(entry["script"] or name, bases)
        if path:
            used_scripts.add(path.resolve())
            try:
                label = path.relative_to(base.parent).as_posix()
            except ValueError:
                label = path.name
            script = read_script(path, label)
            scripts[name] = script
            entry["script_found"] = label
            entry["script_lines"] = script.lines
            entry["sha256"] = script.sha
            entry["reads"] = sorted(script.reads_tables | script.reads_paths)
            entry["writes"] = sorted(script.writes_tables | script.writes_paths)
            entry["outside"] = script.outside
            entry["env"] = sorted(script.env)
            entry["credentials"] = script.credentials
            entry["dynamic_sql"] = script.dynamic_sql
        else:
            entry["script_found"] = None
        jobs[name] = entry

    # What each job writes: its script, plus the inventory's target.
    writes: dict[str, set[str]] = defaultdict(set)
    reads: dict[str, set[str]] = defaultdict(set)
    for name, entry in jobs.items():
        facts = scripts.get(name)
        if facts:
            writes[name] |= facts.writes_tables | {p for p in facts.writes_paths if not p.startswith(TEMP)}
            reads[name] |= facts.reads_tables | {p for p in facts.reads_paths if not p.startswith(TEMP)}
        target_value = entry["declared_target"]
        if target_value and "://" not in target_value:
            writes[name].add(target_value if target_value.startswith("/") else table_key(target_value))

    def declared(reader: str, writer: str) -> str:
        direct = jobs[reader]["depends_on"]
        if writer in direct:
            return "direct"
        seen, todo = set(), list(direct)
        while todo:
            current = todo.pop()
            if current == writer:
                return "transitive"
            if current in jobs and current not in seen:
                seen.add(current)
                todo.extend(jobs[current]["depends_on"])
        return "no"

    links: list[dict[str, Any]] = []
    for reader, wanted in reads.items():
        for item in sorted(wanted):
            for writer, made in writes.items():
                if writer == reader:
                    continue
                for out in sorted(made):
                    if matches(out, item):
                        links.append(
                            {
                                "writer": writer,
                                "reader": reader,
                                "what": item,
                                "kind": "file" if item.startswith("/") else "table",
                                "declared": declared(reader, writer),
                            }
                        )
    undeclared = [link for link in links if link["declared"] == "no"]
    missing_deps = [
        {"job": name, "depends_on": dep}
        for name, entry in jobs.items()
        for dep in entry["depends_on"]
        if dep not in jobs
    ]

    # Two jobs writing the same target, and how close their start times are.
    same: list[dict[str, Any]] = []
    owners_of: dict[str, list[str]] = defaultdict(list)
    for name, made in writes.items():
        for item in made:
            owners_of[item].append(name)
    for item, names in sorted(owners_of.items()):
        if len(names) < 2:
            continue
        crons = {n: parse_cron(jobs[n]["schedule"]) for n in names}
        gap: int | None = None
        for offset in range(0, 14):
            day = as_of.date() + timedelta(days=offset)
            fires = {n: c.times_on(day) for n, c in crons.items() if c}
            ordered = sorted(names)
            for i, first in enumerate(ordered):
                for second in ordered[i + 1 :]:
                    for a in fires.get(first, []):
                        for b in fires.get(second, []):
                            minutes = abs(int((a - b).total_seconds() // 60))
                            gap = minutes if gap is None else min(gap, minutes)
        same.append(
            {
                "target": item,
                "jobs": sorted(names),
                "schedules": {n: jobs[n]["schedule"] for n in sorted(names)},
                "min_minutes_apart": gap,
                "at_once": gap is not None and gap < window,
            }
        )

    # Copies.
    by_sha: dict[str, list[str]] = defaultdict(list)
    by_normal: dict[str, list[str]] = defaultdict(list)
    for name, script in scripts.items():
        by_sha[script.sha].append(name)
        by_normal[hashlib.sha256(script.normal.encode()).hexdigest()].append(name)
    identical = [
        {"jobs": sorted(n), "targets": {j: sorted(writes[j]) for j in sorted(n)}} for n in by_sha.values() if len(n) > 1
    ]
    exact_sets = {frozenset(g["jobs"]) for g in identical}
    near = [
        {"jobs": sorted(n), "note": "the same once comments and spacing are removed"}
        for n in by_normal.values()
        if len(n) > 1 and frozenset(n) not in exact_sets
    ]

    # The estate's edges, for outside inputs, unread outputs, groups and an order.
    written_anywhere = {w for made in writes.values() for w in made}
    read_anywhere = {r for wanted in reads.values() for r in wanted}
    outside_inputs: dict[str, list[str]] = defaultdict(list)
    for name, wanted in reads.items():
        for item in wanted:
            if not any(matches(w, item) for w in written_anywhere):
                outside_inputs[item].append(name)
    unread_outputs: dict[str, list[str]] = defaultdict(list)
    for name, made in writes.items():
        for item in made:
            if not any(matches(item, r) for r in read_anywhere):
                unread_outputs[item].append(name)
    sends = [
        {"job": name, **{k: v for k, v in o.items() if k != "evidence"}, "evidence": o["evidence"]}
        for name, entry in jobs.items()
        for o in entry.get("outside", [])
    ]
    for name, entry in jobs.items():
        target_value = entry["declared_target"] or ""
        url = URL.search(target_value)
        if url and not any(s["job"] == name and s["host"] == url.group(2) for s in sends):
            sends.append(
                {
                    "job": name,
                    "scheme": url.group(1).lower(),
                    "host": url.group(2),
                    "line": None,
                    "direction": "out",
                    "evidence": "declared target in the inventory",
                }
            )

    edges = {(link["writer"], link["reader"]) for link in links}
    edges |= {(dep, name) for name, entry in jobs.items() for dep in entry["depends_on"] if dep in jobs}
    parent = {name: name for name in jobs}

    def root_of(name: str) -> str:
        while parent[name] != name:
            name = parent[name]
        return name

    for src, dst in edges:
        parent[root_of(src)] = root_of(dst)
    for group in same:
        for other in group["jobs"][1:]:
            parent[root_of(other)] = root_of(group["jobs"][0])
    groups: dict[str, list[str]] = defaultdict(list)
    for name in jobs:
        groups[root_of(name)].append(name)
    incoming: dict[str, set[str]] = {name: set() for name in jobs}
    for src, dst in edges:
        incoming[dst].add(src)
    order: list[str] = []
    ready = sorted(n for n, deps in incoming.items() if not deps)
    while ready:
        current = ready.pop(0)
        order.append(current)
        for name in sorted(jobs):
            if current in incoming[name]:
                incoming[name].discard(current)
                if not incoming[name] and name not in order and name not in ready:
                    ready.append(name)
        ready.sort()
    owners: dict[str, int] = defaultdict(int)
    for entry in jobs.values():
        owners[entry["owner"] or "(none)"] += 1
    script_root = scripts_dir or base
    orphans = sorted(
        p.relative_to(script_root).as_posix()
        for p in (script_root.rglob("*") if script_root.is_dir() else [])
        if p.is_file() and p.suffix.lower() in SCRIPT_SUFFIXES and p.resolve() not in used_scripts
    )
    statuses: dict[str, list[str]] = defaultdict(list)
    for name, entry in jobs.items():
        statuses[entry["status"]].append(name)
    return {
        "inputs": {
            "inventory": inv.path.name if target.is_file() else inv.path.relative_to(target).as_posix(),
            "kind": inv.kind,
            "fields": inv.fields,
            "jobs": len(jobs),
            "scripts_found": len(scripts),
            "scripts_missing": sorted(n for n, e in jobs.items() if not e["script_found"]),
            "scripts_not_in_inventory": orphans,
        },
        "as_of": {
            "time": as_of.isoformat(sep=" ", timespec="minutes"),
            "from": as_of_source,
            "dead_after_days": dead_after,
            "grace_minutes": grace,
        },
        "status": {k: sorted(v) for k, v in sorted(statuses.items())},
        "jobs": list(jobs.values()),
        "identical_scripts": identical,
        "near_identical_scripts": near,
        "links": links,
        "undeclared_links": undeclared,
        "unknown_dependencies": missing_deps,
        "same_target": same,
        "outside_consumers": sends,
        "outside_inputs": [{"what": k, "read_by": sorted(v)} for k, v in sorted(outside_inputs.items())],
        "outputs_no_job_reads": [{"what": k, "written_by": sorted(v)} for k, v in sorted(unread_outputs.items())],
        "groups": sorted((sorted(g) for g in groups.values()), key=lambda g: (-len(g), g)),
        "order": order,
        "cycle": sorted(set(jobs) - set(order)),
        "owners": dict(sorted(owners.items())),
        "env": sorted({v for e in jobs.values() for v in e.get("env", [])}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inventory", type=Path, help="job inventory file, crontab, or a folder holding one")
    parser.add_argument("--scripts", type=Path, help="folder of the job scripts, when not beside the inventory")
    parser.add_argument("--as-of", help="the time the inventory was taken, YYYY-MM-DD HH:MM")
    parser.add_argument("--dead-after", type=int, default=180, help="days silent before a stopped job counts as dead")
    parser.add_argument("--grace", type=int, default=60, help="minutes before --as-of a run may still be going")
    parser.add_argument("--window", type=int, default=15, help="start times closer than this are at the same time")
    args = parser.parse_args(argv)
    target = args.inventory.resolve()
    if not target.exists():
        raise SystemExit(f"not found: {target}")
    result = inventory(
        target, args.scripts.resolve() if args.scripts else None, args.as_of, args.dead_after, args.grace, args.window
    )
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
