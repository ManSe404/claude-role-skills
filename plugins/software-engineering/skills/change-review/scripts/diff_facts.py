#!/usr/bin/env python3
"""The facts of a change, for a review that reads every hunk: what changed, what it touches, where to read first.

Usage: python3 diff_facts.py REPO [--range A..B | --patch FILE] [--description FILE] [--max-hunks N]

The default range is `HEAD~1..HEAD`. A range with `...` is taken from the merge base, as git does; a range that ends
open (`main..`) compares with the working tree. --patch reads a unified diff instead and then has no before or after
text to parse, so symbols and rule hits come from the hunks alone.

What comes out, read-only, standard library only, JSON on stdout:
- `commits`: the commits in the range
- `files`: each changed file with its kind (source, test, config, migration, dependency, ci, docs, other), its
  language, lines added and removed, and its hunks with the line numbers each adds and removes
- `symbols`: Python functions, methods and classes the change touches, adds or removes, from the before and after
  text; a removed `test_*` is listed under `tests_removed`
- `tests`: the test files touched, and the source files whose module no touched test names or imports
- `risk_files`: migrations, dependency manifests, CI, configuration and files whose name suggests secrets
- `hits`: the audit rules (audit_scan.py beside this script) on the added lines only; orphan-key needs the whole
  repository and is left out. A hit is a place to read, not a finding
- `claims`: the sentences of --description (a PR body, a ticket) and of the commit messages, each with the kind of
  promise it makes, so the review can hold the diff against what it says
- `size`: files, hunks, lines added and removed

Files named .env or .env.* are never shown. Every git call has a timeout.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_scan as audit

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")
DIFF_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+)$")
MIGRATION = re.compile(r"(^|/)(migrations?|alembic|db/migrate|flyway|liquibase)/", re.IGNORECASE)
DEPENDENCY = re.compile(
    r"(^|/)(pyproject\.toml|requirements[\w.-]*\.txt|setup\.(py|cfg)|Pipfile(\.lock)?|poetry\.lock|uv\.lock|package(-lock)?\.json"
    r"|yarn\.lock|pnpm-lock\.yaml|go\.(mod|sum)|Cargo\.(toml|lock)|[^/]+\.csproj|packages\.lock\.json|Gemfile(\.lock)?|pom\.xml|build\.gradle(\.kts)?)$"
)
CI = re.compile(
    r"(^|/)(\.github/workflows/|\.gitlab-ci\.yml|azure-pipelines[\w.-]*\.yml|Jenkinsfile|\.circleci/|bitbucket-pipelines\.yml)"
)
CONFIG = re.compile(
    r"(^|/)(Dockerfile[\w.-]*|docker-compose[\w.-]*\.ya?ml|[^/]+\.(toml|ya?ml|ini|cfg|conf|env\.example|properties))$"
)
SECRET_NAME = re.compile(
    r"(^|/)(\.env(\..*)?|[^/]*(secret|credential|private|\.pem|\.key|id_rsa)[^/]*)$", re.IGNORECASE
)
TEST_WORDS = re.compile(r"^(?:test_|tests?_)|(?:_test|_spec|\.test|\.spec)$")
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9`\"'(\[*_-])")
MAX_CLAIMS = 40


def run_git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=60, check=False)
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args[:2])} failed: {done.stderr.strip()[:200]}")
    return done.stdout


def refs_of(range_text: str) -> tuple[str, str | None, bool]:
    """(base, head or None for the working tree, three_dots)."""
    if "..." in range_text:
        base, _, head = range_text.partition("...")
        return base, head or None, True
    base, _, head = range_text.partition("..")
    return base, head or None, False


def parse_diff(text: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    hunk: dict[str, Any] | None = None
    old_line = new_line = 0
    for raw in text.splitlines():
        header = DIFF_HEADER.match(raw)
        if header:
            current = {
                "path": header.group(2),
                "old_path": header.group(1),
                "status": "modified",
                "hunks": [],
                "added": 0,
                "removed": 0,
            }
            files.append(current)
            hunk = None
            continue
        if current is None:
            continue
        if raw.startswith("new file mode"):
            current["status"] = "added"
        elif raw.startswith("deleted file mode"):
            current["status"] = "deleted"
        elif raw.startswith("rename from"):
            current["status"] = "renamed"
        elif raw.startswith("Binary files"):
            current["binary"] = True
        match = HUNK.match(raw)
        if match:
            old_line, new_line = int(match.group(1)), int(match.group(3))
            hunk = {
                "id": f"{current['path']}:{new_line}",
                "old_start": old_line,
                "old_lines": int(match.group(2) or 1),
                "new_start": new_line,
                "new_lines": int(match.group(4) or 1),
                "context": match.group(5).strip(),
                "added_lines": [],
                "removed_lines": [],
            }
            current["hunks"].append(hunk)
            continue
        if hunk is None or raw.startswith(("---", "+++", "\\ ")):
            continue
        if raw.startswith("+"):
            hunk["added_lines"].append(new_line)
            current["added"] += 1
            new_line += 1
        elif raw.startswith("-"):
            hunk["removed_lines"].append(old_line)
            current["removed"] += 1
            old_line += 1
        else:
            old_line += 1
            new_line += 1
    return files


def kind_of(path: str) -> str:
    if SECRET_NAME.search(path):
        return "secrets"
    if audit.is_test(path) or TEST_WORDS.search(PurePosixPath(path).stem):
        return "test"
    if MIGRATION.search(path) or (path.lower().endswith(".sql") and "migrat" in path.lower()):
        return "migration"
    if DEPENDENCY.search(path):
        return "dependency"
    if CI.search(path):
        return "ci"
    if audit.is_doc(path):
        return "docs"
    if CONFIG.search(path):
        return "config"
    if audit.language(path) in audit.CODE or audit.language(path) == "sql":
        return "source"
    return "other"


def symbols_in(text: str) -> dict[str, tuple[int, int, str]]:
    """name -> (first line, last line, kind) for functions, methods and classes of a Python file."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return {}
    found: dict[str, tuple[int, int, str]] = {}

    def visit(nodes: list[ast.stmt], prefix: str) -> None:
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                found[prefix + node.name] = (node.lineno, node.end_lineno or node.lineno, "class")
                visit(node.body, prefix + node.name + ".")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "method" if prefix else "function"
                found[prefix + node.name] = (node.lineno, node.end_lineno or node.lineno, kind)

    visit(tree.body, "")
    return found


def show(repo: Path, ref: str | None, path: str) -> str | None:
    if ref is None:
        target = repo / path
        return target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None
    done = subprocess.run(
        ["git", "show", f"{ref}:{path}"], cwd=repo, capture_output=True, text=True, timeout=60, check=False
    )
    return done.stdout if done.returncode == 0 else None


def rule_hits(path: str, after: str, added: set[int]) -> list[dict[str, Any]]:
    lang = audit.language(path)
    source = audit.Source(path, after)
    if lang == "python":
        try:
            tree = ast.parse(after, filename=path)
        except (SyntaxError, ValueError):
            return []
        hits = audit.python_hits(source, after, tree, audit.written_keys(tree))
    elif lang in audit.SHALLOW:
        hits = audit.shallow_hits(source, after, lang)
    else:
        return []
    return [h for h in hits if h["rule"] != "orphan-key" and h["line"] in added]


def module_of(path: str) -> str:
    return (
        PurePosixPath(path)
        .stem.removeprefix("test_")
        .removesuffix("_test")
        .removesuffix("_spec")
        .removesuffix(".test")
        .removesuffix(".spec")
    )


def claims_in(where: str, text: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line).strip()
        if not stripped or stripped.startswith("#"):
            continue
        for sentence in SENTENCE.split(stripped):
            sentence = sentence.strip()
            if len(sentence) < 12:
                continue
            claims.append({"where": f"{where}:{number}", "text": sentence[:240], "kind": audit.kind_of(sentence)})
    return claims[:MAX_CLAIMS]


def facts(
    repo: Path, range_text: str | None, patch: Path | None, description: Path | None, max_hunks: int
) -> dict[str, Any]:
    commits: list[dict[str, str]] = []
    base = head = None
    if patch is not None:
        diff_text = patch.read_text(encoding="utf-8", errors="replace")
        source = {"patch": patch.name}
    else:
        range_text = range_text or "HEAD~1..HEAD"
        base, head, three = refs_of(range_text)
        if three:
            base = run_git(repo, "merge-base", base, head or "HEAD").strip()
        target = [range_text] if head else [base]  # a lone ref diffs against the working tree
        diff_text = run_git(repo, "diff", "--no-color", "--find-renames", *target)
        log = run_git(repo, "log", "--no-merges", "--format=%h%x1f%aI%x1f%s", f"{base}..{head or 'HEAD'}")
        for line in log.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 3:
                commits.append({"hash": parts[0], "date": parts[1], "message": parts[2]})
        source = {"range": range_text, "base": base, "head": head or "working tree"}
    files = parse_diff(diff_text)
    changed_symbols: list[dict[str, Any]] = []
    added_symbols: list[dict[str, Any]] = []
    removed_symbols: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    test_files: list[str] = []
    test_texts: list[str] = []
    for item in files:
        path = item["path"]
        item["kind"] = kind_of(path)
        item["language"] = audit.language(path)
        if item["kind"] == "secrets":
            item["hunks"] = []
            item["note"] = "not shown: the name suggests a secret"
            continue
        item["hunks"] = item["hunks"][:max_hunks]
        added = {line for hunk in item["hunks"] for line in hunk["added_lines"]}
        removed = {line for hunk in item["hunks"] for line in hunk["removed_lines"]}
        before = after = None
        if patch is None:
            before = show(repo, base, item["old_path"]) if item["status"] != "added" else None
            after = show(repo, head, path) if item["status"] != "deleted" else None
        if item["kind"] == "test":
            test_files.append(path)
            if after:
                test_texts.append(after)
        if item["language"] == "python":
            old_symbols = symbols_in(before) if before else {}
            new_symbols = symbols_in(after) if after else {}
            for name, (start, end, kind) in new_symbols.items():
                if name not in old_symbols:
                    added_symbols.append({"file": path, "name": name, "kind": kind, "lines": [start, end]})
                elif any(start <= line <= end for line in added):
                    changed_symbols.append({"file": path, "name": name, "kind": kind, "lines": [start, end]})
            for name, (start, end, kind) in old_symbols.items():
                if name not in new_symbols:
                    removed_symbols.append({"file": path, "name": name, "kind": kind, "old_lines": [start, end]})
                elif name not in {s["name"] for s in changed_symbols if s["file"] == path} and any(
                    start <= line <= end for line in removed
                ):
                    changed_symbols.append(
                        {"file": path, "name": name, "kind": kind, "lines": list(new_symbols[name][:2])}
                    )
            for hunk in item["hunks"]:
                hunk["symbols"] = sorted(
                    {
                        s["name"]
                        for s in changed_symbols + added_symbols
                        if s["file"] == path
                        and s["lines"][0] <= hunk["new_start"] + max(hunk["new_lines"] - 1, 0)
                        and s["lines"][1] >= hunk["new_start"]
                    }
                )
        if after and item["kind"] in {"source", "config"} and added:
            hits.extend(rule_hits(path, after, added))
    tests_removed = [
        s for s in removed_symbols if audit.is_test(s["file"]) and s["name"].rsplit(".", 1)[-1].startswith("test")
    ]
    source_files = [f["path"] for f in files if f["kind"] == "source"]
    uncovered = []
    for path in source_files:
        module = module_of(path)
        named = any(module_of(t) == module for t in test_files)
        imported = any(re.search(rf"\b{re.escape(module)}\b", text) for text in test_texts)
        if not (named or imported):
            uncovered.append(path)
    risk = []
    for item in files:
        if item["kind"] in {"migration", "dependency", "ci", "config", "secrets"}:
            risk.append({"path": item["path"], "why": item["kind"]})
    hits.sort(key=lambda h: (audit.RULES.index(h["rule"]), h["file"], h["line"]))
    claims: list[dict[str, Any]] = []
    if description is not None:
        claims += claims_in(description.name, description.read_text(encoding="utf-8", errors="replace"))
    for commit in commits:
        claims += claims_in(f"commit {commit['hash']}", commit["message"])
    return {
        "repo": repo.name,
        **source,
        "commits": commits,
        "files": files,
        "symbols": {"changed": changed_symbols, "added": added_symbols, "removed": removed_symbols},
        "tests": {"touched": test_files, "tests_removed": tests_removed, "source_without_test_change": uncovered},
        "risk_files": risk,
        "hits": hits,
        "claims": claims[:MAX_CLAIMS],
        "size": {
            "files": len(files),
            "hunks": sum(len(f["hunks"]) for f in files),
            "added": sum(f["added"] for f in files),
            "removed": sum(f["removed"] for f in files),
        },
        "note": (
            "Every hunk is to be read; a hit is a place to read first, not a finding. "
            "Symbols and hits come from the text after the change."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", nargs="?", default=".", type=Path)
    parser.add_argument(
        "--range", dest="range_text", help="git range, default HEAD~1..HEAD; `main..` compares with the working tree"
    )
    parser.add_argument("--patch", type=Path, help="a unified diff file instead of a range")
    parser.add_argument("--description", type=Path, help="the PR description or ticket, for its claims")
    parser.add_argument("--max-hunks", type=int, default=200, help="hunks kept per file")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if not repo.is_dir():
        print(f"{args.repo} is not a directory", file=sys.stderr)
        return 2
    if args.patch is not None and not args.patch.is_file():
        print(f"{args.patch} is not a file", file=sys.stderr)
        return 2
    if args.description is not None and not args.description.is_file():
        print(f"{args.description} is not a file", file=sys.stderr)
        return 2
    json.dump(facts(repo, args.range_text, args.patch, args.description, max(args.max_hunks, 1)), sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
