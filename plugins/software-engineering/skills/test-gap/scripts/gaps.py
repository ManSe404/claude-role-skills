#!/usr/bin/env python3
"""Rank source files by where a missing test hurts most: risk x change rate x lack of coverage.

Usage: python3 gaps.py [REPO] [--coverage FILE] [--days 180] [--top 25]

Coverage comes from an existing report (coverage.py JSON, Cobertura XML or lcov), found in the
usual places or given with --coverage. Without a report, a file counts as tested when a test
file names its module, which is weaker and says so in the output. Risk is a count of risk
families the code touches (money, auth, deletion, parsing, time, concurrency, outside calls,
SQL). Churn is counted back from the last commit. The score and its parts are printed so the
ranking can be argued with:

    score = (1 + risk families) x (1 + commits in window) x gap x log2(2 + code lines)
    gap   = 1 - covered share, or without a report: 1.0 untested, 0.4 named by a test

Also checks the tests themselves: tests without an assertion and skipped tests.
Read-only; standard library only.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

CODE_EXT = {
    ".py",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".mts",
    ".svelte",
    ".vue",
    ".cs",
    ".java",
    ".kt",
    ".go",
    ".rs",
    ".rb",
    ".php",
}
TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]+\.py$|_test\.(py|go)$|\.(test|spec)\.[cm]?[jt]sx?$|Tests?\.cs$|(^|/)[^/]*\.Tests?/|conftest\.py$"
)
JS_TEST = re.compile(
    r"\b(it|test)(\.(only|skip|todo|each\([^)]*\)))?\s*\(\s*['\"`]"
    r"|\[(Fact|Test|TestMethod|Theory)\b|@Test\b|func Test\w+\("
)
GENERATED = re.compile(
    r"(^|/)(migrations|Migrations|alembic/versions|generated|__generated__|vendor)/|\.d\.ts$|\.g\.cs$|_pb2\.py$"
)
COVERAGE_FILES = (
    "coverage.json",
    "coverage.xml",
    "cobertura.xml",
    "lcov.info",
    "coverage/lcov.info",
    "coverage/cobertura-coverage.xml",
    "coverage/coverage-final.json",
)
RISKS = {
    "money": r"\b(price|amount|total|vat|tax|discount|invoice|payment|refund|currency|Decimal|cents?)\b",
    "auth": r"\b(password|token|auth\w*|permission|role|login|jwt|secret|session|credential)s?\b",
    "deletion": r"\b(delete|drop|truncate|remove|purge|DELETE FROM|rmtree|unlink)\b",
    "parsing": (
        r"\b(parse(?!_args|_known_args|rs?\b)\w*|csv|json\.loads|fromisoformat|strptime"
        r"|int\(|float\(|Decimal\(|re\.(match|search)|JSON\.parse)"
    ),
    "time": r"\b(datetime|timezone|tzinfo|utc|now\(\)|timedelta|strftime)\b",
    "concurrency": r"\b(thread\w*|Lock\(|asyncio|await|concurrent|multiprocessing|Semaphore)\b",
    "outside calls": r"\b(requests\.|httpx\.|urlopen|fetch\(|HttpClient|subprocess|smtplib|boto3|send_\w+)",
    "sql": r"\b(SELECT|INSERT|UPDATE|execute\(|executemany\(|cursor\(|raw\()",
}
RISK_RE = {k: re.compile(v) for k, v in RISKS.items()}


def git(repo: Path, *args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=120, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def code_lines(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.strip() and not ln.strip().startswith(("#", "//", "/*", "*")))


def suffix_match(path: str, files: list[str]) -> str | None:
    parts = PurePosixPath(path.replace("\\", "/")).parts
    best, best_len, tie = None, 0, False
    for rel in files:
        rparts = PurePosixPath(rel).parts
        n = 0
        while n < min(len(parts), len(rparts)) and parts[-1 - n] == rparts[-1 - n]:
            n += 1
        if n > best_len:
            best, best_len, tie = rel, n, False
        elif n == best_len and n:
            tie = True
    return None if tie or not best_len else best


def read_coverage(path: Path, files: list[str]) -> dict[str, float]:
    """Return covered share (0..1) per repo file from a coverage.py JSON, Cobertura XML or lcov file."""
    raw: dict[str, list[int]] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".json":
        data = json.loads(text)
        if "files" in data:  # coverage.py
            for name, info in data["files"].items():
                summary = info.get("summary", {})
                raw[name] = [summary.get("covered_lines", 0), summary.get("num_statements", 0)]
        else:  # istanbul coverage-final.json
            for name, info in data.items():
                counts = list(info.get("s", {}).values())
                raw[name] = [sum(1 for c in counts if c), len(counts)]
    elif path.suffix == ".xml":
        root = ET.fromstring(text)
        for cls in root.iter("class"):
            name = cls.get("filename", "")
            hits = [int(line.get("hits", "0")) for line in cls.iter("line")]
            entry = raw.setdefault(name, [0, 0])
            entry[0] += sum(1 for h in hits if h)
            entry[1] += len(hits)
    else:  # lcov
        current = None
        for line in text.splitlines():
            if line.startswith("SF:"):
                current = line[3:]
                raw[current] = [0, 0]
            elif current and line.startswith("LH:"):
                raw[current][0] = int(line[3:])
            elif current and line.startswith("LF:"):
                raw[current][1] = int(line[3:])
    shares: dict[str, float] = {}
    for name, (hit, total) in raw.items():
        rel = name if name in files else suffix_match(name, files)
        if rel and total:
            shares[rel] = hit / total
    return shares


def module_names(rel: str) -> set[str]:
    path = PurePosixPath(rel)
    stem = path.stem
    names = {stem} if stem not in {"__init__", "index", "main", "mod", "lib", "__main__"} else {path.parent.name}
    parts = list(path.with_suffix("").parts)
    if "src" in parts:
        parts = parts[parts.index("src") + 1 :]
    if rel.endswith(".py") and len(parts) > 1:
        names.add(".".join(p for p in parts if p != "__init__"))
    return {n for n in names if n}


def test_quality(rel: str, text: str) -> dict[str, Any]:
    """Count tests, tests without an assertion, and skipped tests in one test file."""
    tests, no_assert, skipped = 0, [], []
    if rel.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return {"tests": 0, "no_assert": [], "skipped": []}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                tests += 1
                body = ast.dump(node)
                asserts = any(isinstance(n, ast.Assert) for n in ast.walk(node)) or re.search(
                    r"attr='assert\w*'|attr='raises'|attr='fail'|id='assert\w*'|attr='expect\w*'", body
                )
                if not asserts:
                    no_assert.append(f"{rel}:{node.lineno} {node.name}")
                decorators = " ".join(ast.unparse(d) for d in node.decorator_list)
                if re.search(r"skip|xfail", decorators) or "skipTest" in body:
                    skipped.append(f"{rel}:{node.lineno} {node.name}")
    else:
        for no, line in enumerate(text.splitlines(), 1):
            if JS_TEST.search(line):
                tests += 1
            if re.search(
                r"\b(it|test|describe)\.(skip|todo)\(|\bx(it|describe)\(|Skip\s*=|\[Ignore\b|@Disabled\b|t\.Skip\(",
                line,
            ):
                skipped.append(f"{rel}:{no}")
    return {"tests": tests, "no_assert": no_assert, "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rank untested risk.")
    parser.add_argument("repo", nargs="?", default=".", type=Path)
    parser.add_argument("--coverage", type=Path, help="coverage.py JSON, Cobertura XML or lcov file")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--top", type=int, default=25)
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    files = [f for f in (git(repo, "ls-files") or "").splitlines() if f and (repo / f).is_file()]
    if not files:
        print("needs a git repository with tracked files", file=sys.stderr)
        return 2
    tests = [f for f in files if TEST_PATH.search(f) and PurePosixPath(f).suffix in CODE_EXT]
    sources = [f for f in files if PurePosixPath(f).suffix in CODE_EXT and f not in tests and not GENERATED.search(f)]
    report = args.coverage
    if report is None:
        report = next((repo / c for c in COVERAGE_FILES if (repo / c).is_file()), None)
    coverage = read_coverage(report, files) if report else {}

    head_date = (git(repo, "log", "-1", "--format=%cI") or "").strip()
    commits: Counter[str] = Counter()
    changed: Counter[str] = Counter()
    if head_date:
        since = (datetime.fromisoformat(head_date) - timedelta(days=args.days)).isoformat()
        for line in (git(repo, "log", f"--since={since}", "--numstat", "--format=", "--no-renames") or "").splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                commits[parts[2]] += 1
                if parts[0].isdigit() and parts[1].isdigit():
                    changed[parts[2]] += int(parts[0]) + int(parts[1])

    test_texts = {t: (repo / t).read_text(encoding="utf-8", errors="replace") for t in tests}
    quality: dict[str, Any] = {"tests": 0, "no_assert": [], "skipped": []}
    for rel, text in test_texts.items():
        q = test_quality(rel, text)
        quality["tests"] += q["tests"]
        quality["no_assert"].extend(q["no_assert"])
        quality["skipped"].extend(q["skipped"])

    rows: list[dict[str, Any]] = []
    for rel in sources:
        text = (repo / rel).read_text(encoding="utf-8", errors="replace")
        loc = code_lines(text)
        if loc == 0:
            continue
        names = module_names(rel)
        named_by = sorted(
            t
            for t, body in test_texts.items()
            if any(re.search(rf"(?<![\w.]){re.escape(n)}(?!\w)", body) for n in names)
        )
        risks = {k: len(r.findall(text)) for k, r in RISK_RE.items()}
        families = sorted(k for k, v in risks.items() if v)
        if rel in coverage:
            covered = coverage[rel]
            gap = 1 - covered
        else:
            covered = None
            gap = 1.0 if not named_by else (0.4 if not coverage else 1.0)
        churn = commits.get(rel, 0)
        score = (1 + len(families)) * (1 + churn) * gap * math.log2(2 + loc)
        rows.append(
            {
                "path": rel,
                "score": round(score, 1),
                "code_lines": loc,
                "commits": churn,
                "lines_changed": changed.get(rel, 0),
                "covered": None if covered is None else round(covered, 2),
                "named_by_tests": named_by[:5],
                "risk_families": families,
                "risk_hits": {k: v for k, v in risks.items() if v},
            }
        )
    rows.sort(key=lambda r: -r["score"])
    result = {
        "repo": repo.name,
        "coverage_source": str(report.relative_to(repo))
        if report and report.is_relative_to(repo)
        else (str(report) if report else None),
        "coverage_note": "measured coverage"
        if coverage
        else "no coverage report: 'tested' means a test file names the module",
        "churn_window": f"{args.days} days before the last commit",
        "source_files": len(rows),
        "test_files": len(tests),
        "untested_files": sum(1 for r in rows if not r["named_by_tests"] and (r["covered"] or 0) == 0),
        "tests": quality,
        "ranked": rows[: args.top],
    }
    json.dump(result, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
