#!/usr/bin/env python3
"""Map a stack trace onto the repository and show what last changed at each frame.

Usage: python3 suspects.py TRACE_FILE [--repo .] [--commits 5]
       some-command 2>&1 | python3 suspects.py - [--repo .]

Understands Python tracebacks, Node/JavaScript, Java, .NET and Go stack frames, and plain
`path:line` mentions. Deployment paths such as /srv/app/src/x.py are matched to the repo by
their longest common path suffix. For each frame in the repo: the code line as it is now, the
commit that last changed that line (git blame) and the latest commits to the file. When the
trace holds several tracebacks, the last one is used. Read-only; standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

FRAME_PATTERNS = (
    ("python", re.compile(r'^\s*File "(?P<path>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>.+))?$')),
    ("dotnet", re.compile(r"^\s*at (?P<func>.+?) in (?P<path>.+?):line (?P<line>\d+)\s*$")),
    (
        "node",
        re.compile(
            r"^\s*at (?:(?P<func>[^\s(]+(?: \[as \w+\])?) )?\(?(?P<path>(?:file://)?[^\s():]+(?::\\[^\s():]+)?):(?P<line>\d+):\d+\)?\s*$"
        ),
    ),
    ("java", re.compile(r"^\s*at (?P<func>[\w.$<>]+)\((?P<path>[\w$.-]+\.\w+):(?P<line>\d+)\)\s*$")),
    ("go", re.compile(r"^\s+(?P<path>/?[^\s:]+\.go):(?P<line>\d+)(?: \+0x[0-9a-f]+)?\s*$")),
)
GENERIC = re.compile(r"(?P<path>[\w./\\-]+\.(?:py|js|mjs|cjs|ts|tsx|cs|java|kt|go|rs|rb|php|scala)):(?P<line>\d+)")
TRACE_START = re.compile(r"^Traceback \(most recent call last\):|^\S*(Error|Exception)\b.*:|^Unhandled exception", re.M)


def git(repo: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout


def last_trace(text: str) -> str:
    """Keep the last traceback when a log holds several."""
    starts = [m.start() for m in re.finditer(r"^Traceback \(most recent call last\):", text, re.M)]
    if len(starts) <= 1:
        return text
    tail = text[starts[-1] :]
    end = re.search(r"^\d{4}-\d{2}-\d{2}[T ]", tail, re.M)
    return tail[: end.start()] if end else tail


def parse_frames(text: str) -> tuple[list[dict[str, Any]], str]:
    frames: list[dict[str, Any]] = []
    lines = text.splitlines()
    error = ""
    for i, line in enumerate(lines):
        for style, pattern in FRAME_PATTERNS:
            match = pattern.match(line)
            if match:
                frames.append(
                    {
                        "style": style,
                        "raw": line.strip(),
                        "path": match.group("path").removeprefix("file://"),
                        "line": int(match.group("line")),
                        "func": (match.groupdict().get("func") or "").strip() or None,
                        "shown_code": lines[i + 1].strip()
                        if style == "python" and i + 1 < len(lines) and not lines[i + 1].lstrip().startswith("File ")
                        else None,
                    }
                )
                break
    if not frames:
        for match in GENERIC.finditer(text):
            frames.append(
                {
                    "style": "generic",
                    "raw": match.group(0),
                    "path": match.group("path"),
                    "line": int(match.group("line")),
                    "func": None,
                    "shown_code": None,
                }
            )
    tail = [ln for ln in lines if ln.strip()]
    if tail:
        error = next((ln.strip() for ln in reversed(tail) if not ln.startswith((" ", "\t"))), tail[-1].strip())
    return frames, error


def match_path(path: str, files: list[str]) -> tuple[str | None, list[str]]:
    """Return the repo file with the longest common path suffix, and the ties if it is ambiguous."""
    parts = PurePosixPath(path.replace("\\", "/")).parts
    best: list[str] = []
    best_len = 0
    for rel in files:
        rparts = PurePosixPath(rel).parts
        n = 0
        while n < min(len(parts), len(rparts)) and parts[-1 - n] == rparts[-1 - n]:
            n += 1
        if n > best_len:
            best, best_len = [rel], n
        elif n == best_len and n > 0:
            best.append(rel)
    if best_len == 0:
        return None, []
    return (best[0] if len(best) == 1 else None), (best if len(best) > 1 else [])


def blame(repo: Path, rel: str, line: int) -> dict[str, Any] | None:
    out = git(repo, "blame", "--porcelain", "-L", f"{line},{line}", "--", rel)
    if not out:
        return None
    first = out.splitlines()[0].split()
    info: dict[str, Any] = {"commit": first[0][:7]}
    for row in out.splitlines()[1:]:
        if row.startswith("author-time "):
            info["date"] = git(repo, "show", "-s", "--format=%as", first[0]) or ""
            info["date"] = info["date"].strip()
        elif row.startswith("summary "):
            info["summary"] = row[len("summary ") :]
    if info["commit"].strip("0") == "":
        info["summary"] = "not committed yet"
    return info


def recent(repo: Path, rel: str, count: int) -> list[dict[str, str]]:
    out = git(repo, "log", f"-n{count}", "--format=%h%x09%as%x09%s", "--", rel) or ""
    return [dict(zip(("commit", "date", "summary"), row.split("\t", 2), strict=False)) for row in out.splitlines()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Map a stack trace to the repo and its recent changes.")
    parser.add_argument("trace", help="a file with the trace or log, or - for stdin")
    parser.add_argument("--repo", default=".", type=Path)
    parser.add_argument("--commits", type=int, default=5, help="latest commits listed per file")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    text = sys.stdin.read() if args.trace == "-" else Path(args.trace).read_text(encoding="utf-8", errors="replace")
    count = len(re.findall(r"^Traceback \(most recent call last\):", text, re.M))
    frames, error = parse_frames(last_trace(text))
    files = [f for f in (git(repo, "ls-files") or "").splitlines() if f]
    head = (git(repo, "log", "-1", "--format=%h %as %s") or "").strip()
    for frame in frames:
        rel = frame["path"] if frame["path"] in files else None
        ties: list[str] = []
        if rel is None:
            rel, ties = match_path(frame["path"], files)
        frame["repo_path"] = rel
        frame["ambiguous"] = ties
        frame["in_repo"] = rel is not None
        if rel is None:
            continue
        code = (repo / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        frame["code_now"] = code[frame["line"] - 1].strip() if 0 < frame["line"] <= len(code) else None
        if frame["shown_code"] is not None and frame["code_now"] is not None:
            frame["code_moved"] = frame["shown_code"] != frame["code_now"]
        frame["last_change_of_line"] = blame(repo, rel, frame["line"])
        frame["latest_commits"] = recent(repo, rel, args.commits)
    result = {
        "repo": repo.name,
        "head": head,
        "tracebacks_in_input": count,
        "error": error,
        "frames": frames,
        "innermost_in_repo": next((f for f in reversed(frames) if f.get("in_repo")), None),
    }
    json.dump(result, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
