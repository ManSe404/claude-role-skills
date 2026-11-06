#!/usr/bin/env python3
"""Every place a name appears, classified, plus the places code is called by a computed name.

Usage: python3 refs.py NAME [NAME ...] [--repo .] [--dynamic] [--max 400]

For each NAME: whole-word matches in tracked text files, each with its area (code, test, docs,
config), its kind (definition, import, string, use) and, in Python files, the function or class
around it, so the next round can ask who calls that one.

--dynamic adds the sites that call or import by a computed name (getattr with a variable,
f-string attribute names, importlib, reflection, dynamic import). A plain text search cannot see
those uses; read each site and decide. Sites whose literal fragments are part of a NAME are
marked as related to it. Read-only; standard library only.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", "bin", "obj"}
SKIP_FILES = re.compile(r"(\.lock|package-lock\.json|\.min\.js|\.map|\.svg|\.snap)$")
CODE_EXT = {
    ".py",
    ".pyi",
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
    ".scala",
    ".sql",
    ".sh",
    ".graphql",
    ".proto",
}
DOC_EXT = {".md", ".rst", ".txt", ".adoc"}
CONFIG_EXT = {".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".xml", ".env.example", ".properties", ".tf"}
TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]+\.py$|_test\.(py|go)$|\.(test|spec)\.[cm]?[jt]sx?$|Tests?\.cs$"
)
IMPORT_LINE = re.compile(r"^\s*(from\s+\S+\s+import\b|import\b|using\b|export\s+\{.*\}\s+from\b)|\brequire\(")
DYNAMIC = (
    (re.compile(r"\bgetattr\(\s*[^,]+,\s*(?!['\"][^'\"{]*['\"]\s*[,)])"), "getattr with a computed name"),
    (re.compile(r"\bsetattr\(\s*[^,]+,\s*(?!['\"][^'\"{]*['\"]\s*[,)])"), "setattr with a computed name"),
    (re.compile(r"\bimportlib\.import_module\("), "importlib.import_module"),
    (re.compile(r"\b__import__\("), "__import__"),
    (re.compile(r"\b(globals|locals|vars)\(\)\s*\["), "namespace lookup"),
    (re.compile(r"(?<![\w.])(eval|exec)\("), "eval or exec"),
    (re.compile(r"\w+\[[^\]'\"]+\]\s*\("), "call through a computed key"),
    (re.compile(r"\b(require|import)\(\s*[^'\"`)\s]"), "import of a computed path"),
    (re.compile(r"\b(GetMethod|GetProperty|GetType|CreateInstance|InvokeMember)\("), "reflection"),
    (re.compile(r"\bReflect\.(get|apply)\("), "reflection"),
)
FSTRING = re.compile(r"""\bf(['"])(.*?)\1|`([^`]*\$\{[^`]*)`""")


def list_files(repo: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout
        files = [f for f in out.split("\0") if f and (repo / f).is_file()]
        if files:
            return sorted(files)
    except (OSError, subprocess.SubprocessError):
        pass
    found: list[str] = []
    for root, dirs, names in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        found.extend((Path(root) / n).relative_to(repo).as_posix() for n in sorted(names))
    return found


def area_of(rel: str) -> str:
    name = PurePosixPath(rel).name
    suffix = PurePosixPath(rel).suffix.lower()
    if TEST_PATH.search(rel):
        return "test"
    if suffix in DOC_EXT:
        return "docs"
    if suffix in CONFIG_EXT or name.startswith(".env.") or name in {"Dockerfile", "Makefile"}:
        return "config"
    if suffix in CODE_EXT:
        return "code"
    return "other"


def kind_of(line: str, name: str) -> str:
    n = re.escape(name)
    definition = (
        rf"^\s*(async\s+)?def\s+{n}\b",
        rf"^\s*class\s+{n}\b",
        rf"^{n}\s*(:[^=]+)?=[^=]",
        rf"^\s*(export\s+)?(default\s+)?(async\s+)?function\*?\s+{n}\b",
        rf"^\s*(export\s+)?(const|let|var)\s+{n}\s*=",
        rf"^\s*(export\s+)?(abstract\s+)?(class|interface|type|enum)\s+{n}\b",
        rf"^\s*(public|private|protected|internal|static|override|virtual|async|readonly|\s)+[\w<>\[\],?\s]*\b{n}\s*[(<{{]",
        rf"^\s*func\s+(\([^)]*\)\s*)?{n}\s*\(",
        rf"^\s*(pub\s+)?(fn|struct|enum|trait)\s+{n}\b",
    )
    if any(re.search(p, line) for p in definition):
        return "definition"
    if IMPORT_LINE.search(line):
        return "import"
    if re.search(rf"""(['"`])[^'"`]*\b{n}\b[^'"`]*\1""", line):
        return "string"
    return "use"


def python_scopes(source: str) -> list[tuple[int, int, str]]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    scopes: list[tuple[int, int, str]] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = f"{prefix}{child.name}"
                scopes.append((child.lineno, child.end_lineno or child.lineno, qual))
                visit(child, qual + ".")
            else:
                visit(child, prefix)

    visit(tree, "")
    return scopes


def enclosing(scopes: list[tuple[int, int, str]], line: int) -> str | None:
    best = None
    for start, end, qual in scopes:
        if start <= line <= end and (best is None or start >= best[0]):
            best = (start, qual)
    return best[1] if best else None


def find(repo: Path, files: list[str], names: list[str], limit: int) -> dict[str, Any]:
    patterns = {name: re.compile(rf"(?<![\w$]){re.escape(name)}(?![\w$])") for name in names}
    result: dict[str, Any] = {name: {"matches": [], "truncated": False} for name in names}
    for rel in files:
        if SKIP_FILES.search(rel) or PurePosixPath(rel).name == ".env":
            continue
        try:
            raw = (repo / rel).read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8192] or len(raw) > 2_000_000:
            continue
        text = raw.decode("utf-8", errors="replace")
        if not any(name in text for name in names):
            continue
        scopes = python_scopes(text) if rel.endswith(".py") else []
        for no, line in enumerate(text.splitlines(), 1):
            for name, pattern in patterns.items():
                if not pattern.search(line):
                    continue
                entry = result[name]
                if len(entry["matches"]) >= limit:
                    entry["truncated"] = True
                    continue
                entry["matches"].append(
                    {
                        "path": rel,
                        "line": no,
                        "area": area_of(rel),
                        "kind": kind_of(line, name),
                        "enclosing": enclosing(scopes, no) if scopes else None,
                        "text": line.strip()[:200],
                    }
                )
    for entry in result.values():
        entry["total"] = len(entry["matches"])
        entry["by_area"] = dict(Counter(m["area"] for m in entry["matches"]))
        entry["by_kind"] = dict(Counter(m["kind"] for m in entry["matches"]))
        entry["files"] = len({m["path"] for m in entry["matches"]})
    return result


def fragments(line: str) -> list[str]:
    parts: list[str] = []
    for match in FSTRING.finditer(line):
        body = match.group(2) if match.group(2) is not None else match.group(3) or ""
        parts.extend(p for p in re.split(r"\$?\{[^}]*\}", body) if len(p) >= 3)
    return parts


def dynamic_sites(repo: Path, files: list[str], names: list[str]) -> list[dict[str, Any]]:
    sites = []
    for rel in files:
        if area_of(rel) not in ("code", "test") or SKIP_FILES.search(rel):
            continue
        try:
            text = (repo / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("#", "//", "*")):
                continue
            for pattern, label in DYNAMIC:
                if pattern.search(line):
                    frags = fragments(line)
                    related = [n for n in names if any(f in n for f in frags)]
                    sites.append(
                        {
                            "path": rel,
                            "line": no,
                            "pattern": label,
                            "text": stripped[:200],
                            "literal_fragments": frags,
                            "related_to": related,
                        }
                    )
                    break
    sites.sort(key=lambda s: (not s["related_to"], s["path"], s["line"]))
    return sites


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find and classify every reference to one or more names.")
    parser.add_argument("names", nargs="+", help="function, class, column, endpoint path, setting, ...")
    parser.add_argument("--repo", default=".", type=Path)
    parser.add_argument("--dynamic", action="store_true", help="also list calls and imports by computed name")
    parser.add_argument("--max", type=int, default=400, help="matches kept per name")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    files = list_files(repo)
    out: dict[str, Any] = {"repo": repo.name, "names": find(repo, files, args.names, args.max)}
    if args.dynamic:
        out["dynamic_sites"] = dynamic_sites(repo, files, args.names)
    json.dump(out, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
