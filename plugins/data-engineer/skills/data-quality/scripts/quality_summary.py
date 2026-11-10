#!/usr/bin/env python3
"""Summarise a data platform's checks over a period: what passed, warned and failed, what was quarantined, how fresh
the tables are, which checks prove nothing, and a verdict per table.

Usage: python3 quality_summary.py REPO [--from YYYY-MM-DD] [--to YYYY-MM-DD]
       [--results FILE] [--quarantine FILE] [--runs FILE] [--definitions DIR] [--cases FILE] [--jobs DIR]

REPO is the platform's repository. The inputs are found in it, or given with the flags:
- check results (JSON Lines, JSON or CSV with a date, a check, a table, a status, failing rows);
- the quarantine (one record per row moved out, with a date, a rule and the value that broke it);
- run records (to know when a table was last built);
- check definitions (YAML with a `checks:` list: name, table, query, warn_if, fail_if, freshness) and quarantine
  rules (a `rules:` list: name, table, column, condition);
- the bad-data cases each check was tried on (YAML with a `cases:` list: check, tried_on, result);
- job definitions (YAML with steps and an `sla`).
Field names are matched without regard to case, with the usual aliases (status or state or result, check or test,
failing_rows or failures); statuses pass, warn and fail are read from their common spellings.

It prints, per check: results, passes, warnings, failures, the range of failing rows, its thresholds, and its test
case. Then the checks that warn on (nearly) every day, the checks that never failed with whether they were ever tried
on bad data, the checks whose query cannot return a row (`amount < amount`, `1 = 0`), single failures followed by a
pass with their note, definitions with no results and results with no definition. Freshness per table with a service
level: the days it was not built by then, from the checks and the runs. The quarantine per rule and day, a step change
in a rule's daily rows, the values behind it and whether each is in the reference table the rule reads. A verdict per
table on the last day: safe, use with care, do not use, with the reasons.

A quarantined value is printed only for a rule on a column that is not personal, and never when it looks like an
e-mail, IBAN or JMBG. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_profile

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "target", "dist", "build"}
RECORD_SUFFIXES = {".jsonl", ".ndjson", ".json", ".csv"}
RESULT_FIELDS = {
    "date": ("run_date", "day", "checked_at", "timestamp", "executed_at", "created_at"),
    "check": ("check_name", "test", "test_name", "name", "rule", "expectation"),
    "table": ("dataset", "model", "asset", "table_name", "object"),
    "layer": ("stage", "zone", "tier"),
    "status": ("state", "result", "outcome"),
    "failing_rows": ("failures", "failed_rows", "rows_failed", "bad_rows", "failing", "unexpected_count"),
    "note": ("message", "comment", "detail"),
}
QUARANTINE_FIELDS = {
    "date": ("day", "quarantined_at", "timestamp", "created_at"),
    "table": ("dataset", "target", "table_name"),
    "rule": ("check", "reason", "rule_name"),
    "row_id": ("id", "key", "record_id", "row_key"),
    "value": ("bad_value", "offending_value"),
    "run_id": ("run", "execution_id"),
}
RUN_FIELDS = {
    "job": ("job_name", "pipeline", "dag", "dag_id", "workflow"),
    "task": ("task_id", "step", "node", "model", "asset"),
    "end": ("ended_at", "finished_at", "end_time", "end_date"),
    "start": ("started_at", "start_time", "start_date"),
    "status": ("state", "result", "outcome"),
}
CHECK_STATUS = {
    "pass": "pass", "passed": "pass", "success": "pass", "ok": "pass", "succeeded": "pass",
    "warn": "warn", "warning": "warn", "fail": "fail", "failed": "fail", "failure": "fail", "error": "fail",
}  # fmt: skip
RUN_STATUS = {"success": "success", "succeeded": "success", "ok": "success", "done": "success", "failed": "failed",
              "error": "failed", "skipped": "skipped", "upstream_failed": "skipped"}  # fmt: skip
NEVER_TRUE = [
    (re.compile(r"(?<![\w.])([\w.]+)\s*(<>|!=|<|>)\s*([\w.]+)(?![\w.(])"), "compares a column with itself"),
    (re.compile(r"\b(1\s*=\s*0|0\s*=\s*1|1\s*<>\s*1)\b"), "a condition that is never true"),
    (re.compile(r"\bwhere\s+false\b|\band\s+false\b", re.I), "and false"),
]
RANK = {"pass": 0, "warn": 1, "fail": 2}
VERDICT = {"pass": "safe", "warn": "use with care", "fail": "do not use"}


# ---------------------------------------------------------------------------- reading


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


def normalise(record: dict[str, Any], fields: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    low = {re.sub(r"[\s-]+", "_", str(k).strip().lower()): v for k, v in record.items()}
    return {name: next((low[a] for a in (name, *aliases) if a in low), None) for name, aliases in fields.items()}


def understood(path: Path, records: list[dict[str, Any]], fields: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    keys = {re.sub(r"[\s-]+", "_", str(k).strip().lower()): str(k) for r in records[:200] for k in r}
    mapped = {
        n: next(keys[a] for a in (n, *al) if a in keys) for n, al in fields.items() if any(a in keys for a in (n, *al))
    }
    return {"file": path.as_posix(), "records": len(records), "fields": mapped,
            "missing": [f for f in fields if f not in mapped]}  # fmt: skip


def as_int(value: Any) -> int | None:
    try:
        return int(float(str(value))) if value not in (None, "") else None
    except ValueError:
        return None


def walk(repo: Path) -> list[Path]:
    found, stack = [], [repo]
    while stack:
        folder = stack.pop()
        for path in sorted(folder.iterdir()):
            if path.is_dir() and path.name not in SKIP_DIRS and not path.name.startswith("."):
                stack.append(path)
            elif path.is_file():
                found.append(path)
    return sorted(found)


def discover(files: list[Path], word: str) -> Path | None:
    hits = [p for p in files if word in p.stem.lower() and p.suffix.lower() in RECORD_SUFFIXES]
    return min(hits, key=lambda p: (len(p.parts), p.as_posix())) if hits else None


def rel(path: Path, repo: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


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
    """A YAML reader for the flat shapes of check, rule, case and job files: mappings, lists, flow lists, scalars."""
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


def yaml_lists(paths: list[Path], repo: Path) -> dict[str, list[dict[str, Any]]]:
    """Every `checks:`, `rules:` and `cases:` list item, and every job with steps, with the file and line it is on."""
    found: dict[str, list[dict[str, Any]]] = {"checks": [], "rules": [], "cases": [], "jobs": []}
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
            data = parse_yaml(text)
        except (UnicodeDecodeError, IndexError):
            continue
        if not isinstance(data, dict):
            continue
        lines = text.splitlines()
        for kind in ("checks", "rules", "cases"):
            for item in data.get(kind) or []:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("check") or "")
                    at = next(
                        (n for n, line in enumerate(lines, 1) if re.search(rf":\s*{re.escape(name)}\s*$", line)), 0
                    )
                    found[kind].append({**item, "_file": rel(path, repo), "_line": at, "_lines": lines})
        steps = data.get("steps") or data.get("tasks")
        if isinstance(steps, list):
            found["jobs"].append(
                {**data, "_file": rel(path, repo), "_steps": [s for s in steps if isinstance(s, dict)]}
            )
    return found


# ---------------------------------------------------------------------------- the checks


def never_true(query: str) -> str | None:
    for pattern, why in NEVER_TRUE:
        for match in pattern.finditer(query):
            if why != "compares a column with itself" or match.group(1) == match.group(3):
                return f"{why}: {match.group(0)}"
    if re.search(r"\b([\w.]+)\s+is\s+null\s+and\s+\1\s+is\s+not\s+null\b", query, re.I):
        return "a column both null and not null"
    return None


def threshold(text: Any) -> int | None:
    match = re.search(r"rows\s*>=?\s*(\d+)", str(text or ""))
    return int(match.group(1)) if match else None


def per_check(results: list[dict[str, Any]], checks: dict[str, dict[str, Any]], cases: dict[str, Any]) -> list[Any]:
    by_check: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        by_check[str(result["check"])].append(result)
    report = []
    for name in sorted(set(by_check) | set(checks)):
        found = sorted(by_check.get(name, []), key=lambda r: str(r["date"]))
        statuses = Counter(r["status"] for r in found)
        rows = [r["failing_rows"] for r in found if r["failing_rows"] is not None]
        definition = checks.get(name, {})
        entry: dict[str, Any] = {
            "check": name,
            "table": (found[0]["table"] if found else None) or definition.get("table"),
            "results": len(found),
            "pass": statuses.get("pass", 0),
            "warn": statuses.get("warn", 0),
            "fail": statuses.get("fail", 0),
        }
        if rows:
            entry["failing_rows"] = [min(rows), max(rows)]
        fails = [str(r["date"]) for r in found if r["status"] == "fail"]
        if fails:
            entry["failed_on"] = fails[:10]
        if definition:
            entry["defined_in"] = f"{definition['_file']}:{definition['_line']}"
            entry["thresholds"] = {k: definition[k] for k in ("warn_if", "fail_if") if definition.get(k)}
            query = str(definition.get("query") or "")
            why = never_true(query) if query else None
            if why:
                at = next(
                    (n for n, line in enumerate(definition["_lines"], 1) if query[:40] in line), definition["_line"]
                )
                entry["cannot_fail"] = {"why": why, "where": f"{definition['_file']}:{at}"}
        entry["test_case"] = cases.get(name)
        report.append(entry)
    return report


def one_offs(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A check that failed on one day and passed on the next."""
    by_check: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        by_check[str(result["check"])].append(result)
    found = []
    for name, rows in by_check.items():
        rows.sort(key=lambda r: str(r["date"]))
        fails = [i for i, r in enumerate(rows) if r["status"] == "fail"]
        if len(fails) == 1 and fails[0] + 1 < len(rows) and rows[fails[0] + 1]["status"] == "pass":
            failed = rows[fails[0]]
            found.append(
                {
                    "check": name,
                    "failed_on": failed["date"],
                    "failing_rows": failed["failing_rows"],
                    "note": failed["note"],
                    "next": {"date": rows[fails[0] + 1]["date"], "status": "pass"},
                }
            )
    return found


# ---------------------------------------------------------------------------- freshness, quarantine, verdicts


def built(runs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        if run["task"]:
            tables[str(run["task"])].append(run)
    return tables


def freshness(
    jobs: list[dict[str, Any]],
    checks: dict[str, dict[str, Any]],
    results: list[dict[str, Any]],
    runs: Any,
    days: list[str],
) -> list[dict[str, Any]]:
    report = []
    fresh_checks = {n: c for n, c in checks.items() if c.get("freshness") or re.search(r"fresh", n)}
    tables = {str(s.get("task") or s.get("table")): job for job in jobs for s in job["_steps"]}
    for table in sorted(
        {str(c.get("table")) for c in fresh_checks.values()} | {t for t, j in tables.items() if j.get("sla")}
    ):
        job = tables.get(table)
        names = [n for n, c in fresh_checks.items() if c.get("table") == table]
        failed = sorted({str(r["date"]) for r in results if r["check"] in names and r["status"] == "fail"})
        entry: dict[str, Any] = {"table": table, "freshness_checks": names, "failed_on": failed}
        if job:
            entry["job"] = job.get("name") or job["_file"]
            entry["sla"] = job.get("sla")
        own = runs.get(table, [])
        if own:
            good = [r for r in own if r["status"] == "success" and r["end"]]
            entry["last_built"] = max((str(r["end"]) for r in good), default=None)
            if job and job.get("sla"):
                sla = str(job["sla"])[:5]
                on_time = {str(r["end"])[:10] for r in good if str(r["end"])[11:16] <= sla}
                entry["days_not_built_by_the_sla"] = [d for d in days if d not in on_time]
        elif job and job.get("record_runs"):
            entry["runs"] = f"the job writes only some runs ({job['record_runs']})"
        report.append(entry)
    return report


def step_change(per_day: dict[str, int]) -> dict[str, Any] | None:
    days = sorted(per_day)
    for k in range(3, len(days) - 1):
        before, after = [per_day[d] for d in days[:k]], [per_day[d] for d in days[k:]]
        if min(after) > 3 * max(before) and min(after) >= 10:
            return {
                "from": days[k],
                "days_before": len(before),
                "rows_before": sum(before),
                "max_a_day_before": max(before),
                "days_from": len(after),
                "rows_from": sum(after),
                "min_a_day_from": min(after),
            }
    return None


def reference(rule: dict[str, Any], files: list[Path], repo: Path) -> tuple[set[str], dict[str, Any]] | None:
    match = re.search(r"\bfrom\s+(\w+)\.(\w+)", str(rule.get("condition") or ""), re.I)
    column = str(rule.get("column") or "")
    if not match or not column:
        return None
    schema, name = match.groups()
    path = next((p for p in files if p.stem == name and p.parent.name == schema and p.suffix == ".csv"), None)
    if path is None:
        return None
    rows = read_records(path)
    values = sorted({str(r.get(column) or "") for r in rows} - {""})
    return set(values), {"file": rel(path, repo), "column": column, "rows": len(rows), "last_in_order": values[-1:]}


def quarantine(
    rows: list[dict[str, Any]], rules: dict[str, dict[str, Any]], files: list[Path], repo: Path
) -> dict[str, Any]:
    by_rule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_rule[str(row["rule"])].append(row)
    report: dict[str, Any] = {}
    for name, found in sorted(by_rule.items()):
        per_day = Counter(str(r["date"])[:10] for r in found)
        rule = rules.get(name, {})
        entry: dict[str, Any] = {
            "rows": len(found),
            "days": len(per_day),
            "table": found[0]["table"],
            "column": rule.get("column"),
            "defined_in": f"{rule['_file']}:{rule['_line']}" if rule else None,
            "per_day": dict(sorted(per_day.items())),
        }
        change = step_change(dict(per_day))
        if change:
            entry["step_change"] = change
        column = str(rule.get("column") or "")
        values = [str(r["value"] or "") for r in found]
        is_personal = data_profile.personal_of(column, [v for v in values if v][:2000]) if column else None
        if not is_personal and any(values):
            ref = reference(rule, files, repo)
            entry["values"] = []
            for value, count in Counter(values).most_common(8):
                if not value or any(check(value) for _, check in data_profile.VALUE_CHECKS):
                    continue
                dates = sorted(str(r["date"])[:10] for r in found if r["value"] == value)
                item: dict[str, Any] = {"value": value, "rows": count, "first": dates[0], "last": dates[-1]}
                if ref:
                    item["in_reference"] = value in ref[0]
                entry["values"].append(item)
            if ref:
                entry["reference"] = ref[1]
        report[name] = entry
    return report


def verdicts(
    results: list[dict[str, Any]],
    last: str,
    fresh: list[dict[str, Any]],
    runs: Any,
    checks: list[dict[str, Any]],
    q: Any,
) -> dict[str, Any]:
    tables = sorted({str(r["table"]) for r in results if r["table"]})
    report = {}
    for table in tables:
        today = [r for r in results if r["table"] == table and str(r["date"]) == last]
        why = [f"{r['check']} {r['status']}" + (f" ({r['failing_rows']} rows)" if r["failing_rows"] else "")
               for r in today if r["status"] != "pass"]  # fmt: skip
        worst = max((r["status"] for r in today), key=lambda s: RANK.get(s, 0), default=None)
        verdict = VERDICT.get(str(worst), "not checked")
        if not today:
            why.append(f"no check result on {last}")
        own = sorted(runs.get(table, []), key=lambda r: str(r["start"] or ""))
        if own and own[-1]["status"] in ("failed", "skipped"):
            verdict = "do not use"
            why.append(f"its last build {own[-1]['status']} ({str(own[-1]['start'])[:10]})")
        if any(f["table"] == table and last in f["failed_on"] for f in fresh):
            verdict = "do not use"
        for check in checks:
            if check["table"] == table and check.get("cannot_fail"):
                why.append(f"{check['check']} cannot fail")
                verdict = "use with care" if verdict == "safe" else verdict
        for rule, entry in q.items():
            if entry["table"] == table and entry.get("step_change"):
                why.append(f"quarantine {rule} jumped from {entry['step_change']['from']}")
                verdict = "use with care" if verdict == "safe" else verdict
        report[table] = {"verdict": verdict, "why": why, "results_on_the_last_day": len(today)}
    return report


# ---------------------------------------------------------------------------- the whole summary


def summarise(args: argparse.Namespace) -> dict[str, Any]:
    repo: Path = args.repo
    files = walk(repo)
    paths = {
        "results": args.results or discover(files, "check"),
        "quarantine": args.quarantine or discover(files, "quarant"),
        "runs": args.runs or discover(files, "run"),
    }
    if paths["results"] is None:
        raise SystemExit("no check results found: give them with --results")
    yaml_files = [f for f in files if f.suffix in (".yaml", ".yml")]
    if args.definitions:
        yaml_files = sorted(args.definitions.rglob("*.y*ml")) + [
            f for f in yaml_files if args.definitions not in f.parents
        ]
    if args.cases:
        yaml_files = [f for f in yaml_files if f.resolve() != args.cases.resolve()] + [args.cases]
    lists = yaml_lists(yaml_files, repo)
    if args.jobs:
        lists["jobs"] = yaml_lists(sorted(args.jobs.glob("*.y*ml")), repo)["jobs"]
    fields = {"results": RESULT_FIELDS, "quarantine": QUARANTINE_FIELDS, "runs": RUN_FIELDS}
    raw = {k: read_records(p) if p else [] for k, p in paths.items()}
    seen: dict[str, Any] = {k: understood(p, raw[k], fields[k]) if p else None for k, p in paths.items()}
    seen["definitions"] = sorted({c["_file"] for c in lists["checks"] + lists["rules"]})
    seen["cases"] = sorted({c["_file"] for c in lists["cases"]})
    seen["jobs"] = sorted(j["_file"] for j in lists["jobs"])
    results = []
    for record in raw["results"]:
        one = normalise(record, RESULT_FIELDS)
        one["date"] = str(one["date"] or "")[:10]
        one["status"] = CHECK_STATUS.get(str(one["status"] or "").strip().lower(), str(one["status"]))
        one["failing_rows"] = as_int(one["failing_rows"])
        results.append(one)
    days_all = sorted({r["date"] for r in results if r["date"]})
    start, end = args.date_from or (days_all[0] if days_all else ""), args.date_to or (days_all[-1] if days_all else "")
    results = [r for r in results if start <= r["date"] <= end]
    days = sorted({r["date"] for r in results})
    checks = {str(c.get("name")): c for c in lists["checks"] if c.get("name")}
    rules = {str(c.get("name")): c for c in lists["rules"] if c.get("name")}
    cases: dict[str, Any] = {}
    for case in sorted(lists["cases"], key=lambda c: str(c.get("tried_on") or "")):
        cases[str(case.get("check"))] = {k: case.get(k) for k in ("tried_on", "bad_rows", "result")} | {
            "where": f"{case['_file']}:{case['_line']}"
        }
    runs_raw = [normalise(r, RUN_FIELDS) for r in raw["runs"]]
    for run in runs_raw:
        run["status"] = RUN_STATUS.get(str(run["status"] or "").lower(), str(run["status"]))
    runs = built([r for r in runs_raw if start <= str(r["start"] or "")[:10] <= end] or runs_raw)
    checked = per_check(results, checks, cases)
    rows_q = [normalise(r, QUARANTINE_FIELDS) for r in raw["quarantine"]]
    rows_q = [r for r in rows_q if start <= str(r["date"] or "")[:10] <= end]
    fresh = freshness(lists["jobs"], checks, results, runs, days)
    q = quarantine(rows_q, rules, files, repo)
    with_results = [c for c in checked if c["results"]]
    result: dict[str, Any] = {
        "understood": seen,
        "period": {"from": start, "to": end, "days": len(days), "results": len(results)},
        "checks": checked,
        "warn_every_day": [
            {k: c.get(k) for k in ("check", "table", "warn", "results", "failing_rows", "thresholds")}
            for c in with_results
            if c["warn"] >= 0.9 * c["results"] and c["warn"] >= 5
        ],
        "never_failed": [
            {"check": c["check"], "table": c["table"], "results": c["results"], "test_case": c["test_case"]}
            for c in with_results
            if c["fail"] == 0 and c["warn"] == 0
        ],
        "without_a_test_case": sorted(c["check"] for c in checked if not c["test_case"]),
        "cannot_fail": [{"check": c["check"], **c["cannot_fail"]} for c in checked if c.get("cannot_fail")],
        "single_failures": one_offs(results),
        "defined_without_results": sorted(c["check"] for c in checked if not c["results"]),
        "results_without_a_definition": sorted(c["check"] for c in with_results if c["check"] not in checks)
        if checks
        else [],
        "freshness": fresh,
        "quarantine": q,
        "quarantine_watched_by_a_check": any(re.search(r"quarant", str(c["check"])) for c in checked),
        "verdicts": verdicts(results, end, fresh, runs, checked, q),
    }
    result["hits"] = hits_of(result)
    return result


def hits_of(result: dict[str, Any]) -> list[str]:
    hits = []
    for check in result["warn_every_day"]:
        hits.append(
            f"{check['check']} warned on {check['warn']} of {check['results']} days, rows {check['failing_rows']}"
        )
    for check in result["cannot_fail"]:
        hits.append(f"{check['check']} cannot fail: {check['why']} ({check['where']})")
    if result["without_a_test_case"]:
        hits.append(f"never tried on bad data: {result['without_a_test_case']}")
    for fresh in result["freshness"]:
        if fresh["failed_on"]:
            hits.append(f"{fresh['table']}: freshness failed on {fresh['failed_on']}, sla {fresh.get('sla')}")
    for rule, entry in result["quarantine"].items():
        if entry.get("step_change"):
            new = [v["value"] for v in entry.get("values", []) if v.get("in_reference") is False]
            hits.append(
                f"quarantine {rule}: step change from {entry['step_change']['from']}, values not in the reference {new}"
            )
    if result["quarantine"] and not result["quarantine_watched_by_a_check"]:
        hits.append("no check watches the quarantine")
    for one in result["single_failures"]:
        hits.append(f"{one['check']} failed once on {one['failed_on']} and passed the next day: {one['note']}")
    hits += [f"defined but no results: {c}" for c in result["defined_without_results"]]
    for table, verdict in result["verdicts"].items():
        hits.append(f"{table}: {verdict['verdict']} ({'; '.join(verdict['why']) or 'every check passed'})")
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("repo", type=Path, help="the platform's repository")
    parser.add_argument("--from", dest="date_from", help="first day of the period (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", help="last day of the period; the verdicts are for this day")
    parser.add_argument("--results", type=Path, help="check results, if not found by name")
    parser.add_argument("--quarantine", type=Path, help="quarantined rows, if not found by name")
    parser.add_argument("--runs", type=Path, help="run records, if not found by name")
    parser.add_argument("--definitions", type=Path, help="folder of check and rule definitions")
    parser.add_argument("--cases", type=Path, help="the bad-data cases of the checks")
    parser.add_argument("--jobs", type=Path, help="folder of job definitions")
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        print(f"not a folder: {args.repo}", file=sys.stderr)
        return 2
    json.dump(summarise(args), sys.stdout, indent=1, ensure_ascii=False, default=str)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
