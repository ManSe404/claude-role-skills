#!/usr/bin/env python3
"""One timeline from log files, the git history and deploy markers, with the counts an incident needs.

Usage: python3 incident_timeline.py LOG [LOG ...] [--repo REPO] [--window HOURS] [--since ISO] [--until ISO]
                                    [--detected ISO] [--mitigated ISO] [--resolved ISO] [--max-signatures N]

A log line starts with a timestamp (ISO 8601, `2026-10-02 06:00:01,123`, syslog `Oct  2 06:00:01` or `[...]`); a line
without one (a traceback, a wrapped message) belongs to the entry before it. The level is the first TRACE, DEBUG, INFO,
WARN, WARNING, ERROR, CRITICAL, FATAL or PANIC after the timestamp; an entry whose continuation ends in a Python
exception line counts as an error too. The component is the first word after the level when it looks like a name.

What comes out, all read-only, standard library only, JSON on stdout:
- `first_error`: the first entry at ERROR or above in the window, with its signature and the tail of its traceback
- `last_normal_before`: the last entry below ERROR before it
- `errors`: the total, the distinct signatures (digits, hex ids, quoted text, paths and e-mail addresses replaced)
  with their counts and first and last time, the components named, the rate per minute before and after the first
  error, and the count per day
- `deploys`: lines that name a deploy, release or rollback with a version or a commit
- `runs`: for a job that logs a start line, each run with its outcome
- `changes_before_first_error`: the deploys in the window before it and, with --repo, the commits of that window
  (hash, date and message; no author, because a postmortem names roles, not people)
- `ids`: how many distinct e-mail addresses, order-like ids and IP addresses the errors mention, as counts only;
  no value is ever printed
- `phases`: with --detected, --mitigated and --resolved, the minutes from the first error to each and the errors in
  each phase
- `timeline`: deploys, the first error, each change between failing and working, and the phase marks, in order

--since and --until cut the window; --window (default 72) is the hours before the first error that count as "before".
The git call has a timeout. A personal value that no pattern recognises is kept out only by the caller never printing
raw lines; the entries this script prints are signatures, not lines.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

MAX_BYTES = 50_000_000
TRACE_TAIL = 6
LEVELS = ("TRACE", "DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL", "PANIC")
ERROR_LEVELS = {"ERROR", "CRITICAL", "FATAL", "PANIC"}
ISO = re.compile(
    r"^\[?(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?(?:\s?(?:Z|[+-]\d{2}:?\d{2}))?)\]?\s*"
)
SYSLOG = re.compile(r"^(?P<ts>[A-Z][a-z]{2}\s+\d{1,2} \d{2}:\d{2}:\d{2})\s+")
LEVEL = re.compile(r"\b(" + "|".join(LEVELS) + r")\b[:\]]?\s*")
COMPONENT = re.compile(r"^\[?([A-Za-z_][\w.-]{1,40})\]?[:\s]")
EXCEPTION_LINE = re.compile(r"^(?:[A-Za-z_][\w.]*\.)?[A-Z]\w*(?:Error|Exception|Warning|Fault|Timeout|Interrupt)\b")
FRAME = re.compile(r'^\s+File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>\S+)')
DEPLOY = re.compile(
    r"\b(?P<kind>deploy(?:ed|ing|ment)?|release[ds]?|rollback|rolled back|restart(?:ed|ing)?)\b"
    r"(?:\s+(?:to|of|version|v))?\s*(?P<ref>v?\d+\.\d+[\w.-]*|[0-9a-f]{7,40})?",
    re.IGNORECASE,
)
RUN_START = re.compile(r"\b(?:start(?:ed|ing)?|begin(?:ning)?|launch(?:ed|ing)?)\b", re.IGNORECASE)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}\b")
IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
ORDER_ID = re.compile(r"\b[A-Z]{1,4}-\d{2,}\b")
HEX_ID = re.compile(r"\b[0-9a-f]{7,40}\b")
UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
QUOTED = re.compile(r"(['\"]).*?\1")
PATH = re.compile(r"(?:/[\w.-]+){2,}")
NUMBER = re.compile(r"\d+")


def parse_time(text: str, year: int | None = None) -> datetime | None:
    text = text.strip().replace(",", ".")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for candidate in (text, text.replace(" ", "T", 1)):
        try:
            value = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        value = datetime.strptime(text, "%b %d %H:%M:%S")
    except ValueError:
        return None
    return value.replace(year=year or datetime.now(UTC).year, tzinfo=UTC)


def signature(message: str) -> str:
    text = EMAIL.sub("<email>", message)
    text = UUID.sub("<uuid>", text)
    text = PATH.sub("<path>", text)
    text = QUOTED.sub("<text>", text)
    text = IP.sub("<ip>", text)
    text = ORDER_ID.sub("<id>", text)
    text = HEX_ID.sub("<hex>", text)
    text = NUMBER.sub("N", text)
    return re.sub(r"\s+", " ", text).strip()[:160]


def component_of(message: str) -> str | None:
    match = COMPONENT.match(message)
    if not match:
        return None
    name = match.group(1)
    return name if not name.isdigit() and name.lower() not in {"the", "a", "an"} else None


def read_entries(path: Path, year: int | None) -> list[dict[str, Any]]:
    """Entries of one file: timestamp, level, component, message, continuation lines, line number."""
    entries: list[dict[str, Any]] = []
    if path.stat().st_size > MAX_BYTES:
        raise SystemExit(f"{path} is over {MAX_BYTES} bytes; cut the window first")
    with path.open(encoding="utf-8", errors="replace") as handle:
        for number, raw in enumerate(handle, start=1):
            line = raw.rstrip("\n")
            match = ISO.match(line) or SYSLOG.match(line)
            when = parse_time(match.group("ts"), year) if match else None
            if match and when is not None:
                rest = line[match.end() :]
                level_match = LEVEL.search(rest[:80])
                level = level_match.group(1).upper() if level_match else None
                level = "WARNING" if level == "WARN" else level
                message = rest[level_match.end() :] if level_match else rest
                entries.append(
                    {
                        "time": when,
                        "level": level,
                        "component": component_of(message),
                        "message": message.strip(),
                        "continuation": [],
                        "file": path.name,
                        "line": number,
                    }
                )
            elif entries:
                entries[-1]["continuation"].append(line)
    for entry in entries:
        tail = [c for c in entry["continuation"] if c.strip()]
        if tail and EXCEPTION_LINE.match(tail[-1].strip()):
            entry["exception"] = tail[-1].strip()
            if entry["level"] not in ERROR_LEVELS:
                entry["level"] = "ERROR"
        entry["error"] = entry["level"] in ERROR_LEVELS
    return entries


def traceback_tail(entry: dict[str, Any]) -> list[dict[str, Any]]:
    frames = [m.groupdict() for m in (FRAME.match(c) for c in entry["continuation"]) if m]
    return [{"file": f["file"], "line": int(f["line"]), "function": f["func"]} for f in frames[-TRACE_TAIL:]]


def deploy_in(entry: dict[str, Any]) -> dict[str, Any] | None:
    """A deploy, release, rollback or restart event with its ref; `(deployed X)` in an aside is a version marker."""
    match = DEPLOY.search(entry["message"])
    if not match or not match.group("ref"):
        return None
    if entry["message"][: match.start()].rstrip().endswith("("):
        return None
    return {
        "time": entry["time"].isoformat(),
        "kind": match.group("kind").lower(),
        "ref": match.group("ref"),
        "line": f"{entry['file']}:{entry['line']}",
    }


def version_in(entry: dict[str, Any]) -> str | None:
    """The running version a line names in an aside such as `(deployed c376ea1)` or `version 1.4.2`."""
    match = DEPLOY.search(entry["message"])
    if not match or not match.group("ref"):
        return None
    aside = entry["message"][: match.start()].rstrip().endswith("(")
    return match.group("ref") if aside else None


def version_changes(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    changes = []
    current = None
    for entry in entries:
        version = version_in(entry)
        if version and version != current:
            if current is not None:
                changes.append(
                    {
                        "time": entry["time"].isoformat(),
                        "from": current,
                        "to": version,
                        "line": f"{entry['file']}:{entry['line']}",
                    }
                )
            current = version
    return changes


def runs_in(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for entry in entries:
        if RUN_START.search(entry["message"]) and not entry["error"]:
            if current:
                runs.append(current)
            current = {
                "start": entry["time"].isoformat(),
                "outcome": "ok",
                "errors": 0,
                "line": f"{entry['file']}:{entry['line']}",
            }
        elif current is not None and entry["error"]:
            current["outcome"] = "error"
            current["errors"] += 1
    if current:
        runs.append(current)
    return runs


def rate_per_minute(entries: list[dict[str, Any]], start: datetime, end: datetime) -> float | None:
    minutes = (end - start).total_seconds() / 60
    if minutes <= 0:
        return None
    count = sum(1 for e in entries if e["error"] and start <= e["time"] < end)
    return round(count / minutes, 3)


def git_commits(repo: Path, since: datetime, until: datetime) -> list[dict[str, str]] | str:
    try:
        done = subprocess.run(
            [
                "git",
                "log",
                f"--since={since.isoformat()}",
                f"--until={until.isoformat()}",
                "--format=%h%x1f%aI%x1f%s",
                "--no-merges",
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"git log failed: {type(exc).__name__}"
    if done.returncode != 0:
        return "git log failed: " + done.stderr.strip()[:120]
    commits = []
    for line in done.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            commits.append({"hash": parts[0], "date": parts[1], "message": parts[2]})
    return commits


def minutes(a: datetime | None, b: datetime | None) -> float | None:
    return round((b - a).total_seconds() / 60, 1) if a and b else None


def build(
    paths: list[Path],
    repo: Path | None,
    window_hours: float,
    since: datetime | None,
    until: datetime | None,
    detected: datetime | None,
    mitigated: datetime | None,
    resolved: datetime | None,
    max_signatures: int,
) -> dict[str, Any]:
    year = None
    entries: list[dict[str, Any]] = []
    files = []
    for path in paths:
        own = read_entries(path, year)
        files.append(
            {
                "path": path.name,
                "entries": len(own),
                "first": own[0]["time"].isoformat() if own else None,
                "last": own[-1]["time"].isoformat() if own else None,
            }
        )
        entries.extend(own)
    entries.sort(key=lambda e: e["time"])
    if since:
        entries = [e for e in entries if e["time"] >= since]
    if until:
        entries = [e for e in entries if e["time"] <= until]
    errors = [e for e in entries if e["error"]]
    first = errors[0] if errors else None
    deploys = [d for d in (deploy_in(e) for e in entries) if d]
    result: dict[str, Any] = {
        "files": files,
        "entries": len(entries),
        "span": {"first": entries[0]["time"].isoformat(), "last": entries[-1]["time"].isoformat()} if entries else None,
        "levels": dict(Counter((e["level"] or "none") for e in entries)),
        "deploys": deploys,
        "version_changes": version_changes(entries),
        "runs": runs_in(entries),
    }
    if first is None:
        result["first_error"] = None
        result["errors"] = {"total": 0}
        result["timeline"] = [{"time": d["time"], "kind": "deploy", "text": f"{d['kind']} {d['ref']}"} for d in deploys]
        result["note"] = "No entry at ERROR or above in the window."
        return result
    before = [e for e in entries if e["time"] < first["time"] and not e["error"]]
    window_start = first["time"] - timedelta(hours=window_hours)
    by_signature: dict[str, dict[str, Any]] = {}
    for e in errors:
        key = signature(e.get("exception") or e["message"])
        slot = by_signature.setdefault(
            key, {"signature": key, "count": 0, "first": e["time"], "last": e["time"], "components": Counter()}
        )
        slot["count"] += 1
        slot["last"] = e["time"]
        if e["component"]:
            slot["components"][e["component"]] += 1
    signatures = sorted(by_signature.values(), key=lambda s: -s["count"])[:max_signatures]
    text_of_errors = "\n".join(e["message"] + "\n" + "\n".join(e["continuation"]) for e in errors)
    per_day: Counter[str] = Counter(e["time"].date().isoformat() for e in errors)
    total_per_day: Counter[str] = Counter(e["time"].date().isoformat() for e in entries)
    last_time = entries[-1]["time"]
    result["first_error"] = {
        "time": first["time"].isoformat(),
        "where": f"{first['file']}:{first['line']}",
        "level": first["level"],
        "component": first["component"],
        "signature": signature(first.get("exception") or first["message"]),
        "exception": first.get("exception"),
        "traceback_tail": traceback_tail(first),
    }
    result["last_normal_before"] = (
        {"time": before[-1]["time"].isoformat(), "signature": signature(before[-1]["message"])} if before else None
    )
    result["errors"] = {
        "total": len(errors),
        "by_signature": [
            {
                "signature": s["signature"],
                "count": s["count"],
                "first": s["first"].isoformat(),
                "last": s["last"].isoformat(),
                "components": dict(s["components"]),
            }
            for s in signatures
        ],
        "by_component": dict(Counter(e["component"] for e in errors if e["component"])),
        "per_minute_before": rate_per_minute(entries, max(window_start, entries[0]["time"]), first["time"]),
        "per_minute_after": rate_per_minute(entries, first["time"], last_time + timedelta(seconds=1)),
        "per_day": [
            {"day": day, "errors": per_day.get(day, 0), "entries": total_per_day[day]} for day in sorted(total_per_day)
        ],
    }
    changes: dict[str, Any] = {
        "window_hours": window_hours,
        "from": window_start.isoformat(),
        "to": first["time"].isoformat(),
        "deploys": [d for d in deploys if window_start.isoformat() <= d["time"] <= first["time"].isoformat()],
        "version_changes": [
            v for v in result["version_changes"] if window_start.isoformat() <= v["time"] <= first["time"].isoformat()
        ],
    }
    if repo is not None:
        changes["commits"] = git_commits(repo, window_start, first["time"])
    result["changes_before_first_error"] = changes
    result["ids"] = {
        "emails": len(set(EMAIL.findall(text_of_errors))),
        "order_like_ids": len(set(ORDER_ID.findall(text_of_errors))),
        "ip_addresses": len(set(IP.findall(text_of_errors))),
    }
    marks = [("detected", detected), ("mitigated", mitigated), ("resolved", resolved)]
    if any(t for _, t in marks):
        result["phases"] = {
            "first_error": first["time"].isoformat(),
            "detected": detected.isoformat() if detected else None,
            "mitigated": mitigated.isoformat() if mitigated else None,
            "resolved": resolved.isoformat() if resolved else None,
            "minutes_to_detect": minutes(first["time"], detected),
            "minutes_to_mitigate": minutes(detected, mitigated) if detected else minutes(first["time"], mitigated),
            "minutes_to_resolve": minutes(first["time"], resolved),
            "errors_before_detection": sum(1 for e in errors if detected and e["time"] < detected),
            "errors_after_mitigation": sum(1 for e in errors if mitigated and e["time"] >= mitigated),
        }
    timeline: list[dict[str, Any]] = [
        {"time": d["time"], "kind": "deploy", "text": f"{d['kind']} {d['ref']}", "where": d["line"]} for d in deploys
    ]
    timeline += [
        {
            "time": v["time"],
            "kind": "version_change",
            "text": f"running version {v['from']} became {v['to']}",
            "where": v["line"],
        }
        for v in result["version_changes"]
    ]
    timeline.append(
        {
            "time": first["time"].isoformat(),
            "kind": "first_error",
            "text": result["first_error"]["signature"],
            "where": result["first_error"]["where"],
        }
    )
    failing = True
    for e in entries:
        if e["time"] <= first["time"]:
            continue
        if failing and not e["error"] and e["level"] == "INFO" and RUN_START.search(e["message"]) is None:
            continue
        if failing and not e["error"] and e["level"] == "INFO":
            # a new run after a failure says nothing yet; a success inside it does
            continue
        if e["error"] and not failing:
            failing = True
            timeline.append(
                {
                    "time": e["time"].isoformat(),
                    "kind": "failing_again",
                    "text": signature(e.get("exception") or e["message"]),
                    "where": f"{e['file']}:{e['line']}",
                }
            )
    for run in result["runs"]:
        if run["start"] > first["time"].isoformat() and run["outcome"] == "ok" and failing:
            failing = False
            timeline.append(
                {
                    "time": run["start"],
                    "kind": "working_again",
                    "text": "a run completed without an error",
                    "where": run["line"],
                }
            )
    for kind, when in marks:
        if when:
            timeline.append({"time": when.isoformat(), "kind": kind, "text": f"{kind} (given)"})
    timeline.sort(key=lambda t: t["time"])
    result["timeline"] = timeline
    result["note"] = (
        "Signatures replace numbers, ids, paths, quoted text and e-mail addresses; ids are counted, never shown. "
        "A commit in the window is a place to read, not the cause."
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--repo", type=Path, help="repository whose commits before the first error are listed")
    parser.add_argument("--window", type=float, default=72, help="hours before the first error that count as before")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--detected")
    parser.add_argument("--mitigated")
    parser.add_argument("--resolved")
    parser.add_argument("--max-signatures", type=int, default=20)
    args = parser.parse_args(argv)
    paths = []
    for path in args.logs:
        if path.is_dir():
            paths.extend(sorted(p for p in path.iterdir() if p.is_file() and not p.name.startswith(".")))
        elif path.is_file():
            paths.append(path)
        else:
            print(f"{path} is not a file or a folder", file=sys.stderr)
            return 2
    if not paths:
        print("no log files", file=sys.stderr)
        return 2
    times = {}
    for name in ("since", "until", "detected", "mitigated", "resolved"):
        value = getattr(args, name)
        if value:
            parsed = parse_time(value)
            if parsed is None:
                print(f"--{name} is not a time: {value}", file=sys.stderr)
                return 2
            times[name] = parsed
    repo = args.repo.resolve() if args.repo else None
    if repo is not None and not repo.is_dir():
        print(f"{args.repo} is not a directory", file=sys.stderr)
        return 2
    result = build(
        paths,
        repo,
        args.window,
        times.get("since"),
        times.get("until"),
        times.get("detected"),
        times.get("mitigated"),
        times.get("resolved"),
        max(args.max_signatures, 1),
    )
    json.dump(result, sys.stdout, indent=1, default=str)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
