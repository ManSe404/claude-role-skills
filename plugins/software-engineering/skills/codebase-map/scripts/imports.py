#!/usr/bin/env python3
"""The import graph of a repository, grouped into modules, plus the outside packages it uses.

Usage: python3 imports.py [REPO] [--depth 2]

Python is parsed with ast (exact). JavaScript and TypeScript relative imports are found with
regular expressions (good, not exact: dynamic paths and path aliases are missed). Other
languages are counted under "not_covered" so the map says what it could not see.

--depth groups modules: for Python, `acme.orders.pricing` at depth 2 is `acme.orders`; for
JS/TS it is the number of folders kept below the root or src/. Read-only; standard library only.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", "bin", "obj"}
JS_EXT = (".ts", ".tsx", ".mts", ".js", ".jsx", ".mjs", ".cjs", ".svelte", ".vue")
OTHER_CODE = {".cs": "C#", ".java": "Java", ".kt": "Kotlin", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP"}
JS_IMPORT = re.compile(
    r"""(?:import\s[^'"]*?from\s*|import\s*\(\s*|require\s*\(\s*|export\s[^'"]*?from\s*|import\s+)['"]([^'"]+)['"]"""
)


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


# ---------------------------------------------------------------------------- Python


def python_module_name(rel: str) -> str | None:
    parts = list(PurePosixPath(rel).with_suffix("").parts)
    if "src" in parts:
        parts = parts[parts.index("src") + 1 :]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts or any(not p.isidentifier() for p in parts):
        return None
    return ".".join(parts)


def python_graph(repo: Path, files: list[str], depth: int) -> dict[str, Any]:
    modules: dict[str, str] = {}
    for rel in files:
        if rel.endswith(".py"):
            name = python_module_name(rel)
            if name:
                modules[name] = rel
    if not modules:
        return {}
    tops = {m.split(".")[0] for m in modules}
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    edges: Counter[tuple[str, str]] = Counter()
    external: dict[str, set[str]] = defaultdict(set)
    errors = []
    lines: Counter[str] = Counter()

    def group(module: str) -> str:
        return ".".join(module.split(".")[:depth])

    def resolve(target: str) -> str | None:
        while target:
            if target in modules:
                return target
            target = target.rpartition(".")[0]
        return None

    for name, rel in modules.items():
        try:
            source = (repo / rel).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=rel)
        except (SyntaxError, ValueError, OSError) as exc:
            errors.append({"path": rel, "error": str(exc)[:200]})
            continue
        lines[group(name)] += source.count("\n")
        package = name if rel.endswith("__init__.py") else name.rpartition(".")[0]
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = package.split(".")
                    base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                    prefix = ".".join(p for p in base if p)
                    mod = f"{prefix}.{node.module}" if node.module else prefix
                else:
                    mod = node.module or ""
                # `from a import b` imports module a.b when it exists, else name b of module a.
                targets = [f"{mod}.{alias.name}" if mod else alias.name for alias in node.names]
            seen: set[str] = set()
            for target in targets:
                internal = resolve(target)
                if internal:
                    dst = group(internal)
                    if dst != group(name) and dst not in seen:
                        edges[(group(name), dst)] += 1
                        seen.add(dst)
                    continue
                top = target.split(".")[0]
                if top and top not in tops and top not in stdlib and top != "__future__":
                    external[top].add(rel)
    nodes = sorted({group(m) for m in modules})
    return {
        "nodes": [{"id": n, "files": sum(1 for m in modules if group(m) == n), "lines": lines[n]} for n in nodes],
        "edges": [{"from": a, "to": b, "imports": c} for (a, b), c in sorted(edges.items())],
        "external": [{"package": k, "files": sorted(v)} for k, v in sorted(external.items())],
        "parse_errors": errors,
    }


# ---------------------------------------------------------------------------- JS / TS


def js_group(rel: str, depth: int) -> str:
    parts = list(PurePosixPath(rel).parent.parts)
    if "src" in parts:
        parts = parts[parts.index("src") + 1 :]
    return "/".join(parts[:depth]) or "(root)"


def js_resolve(spec: str, rel: str, files: set[str]) -> str | None:
    base = (PurePosixPath(rel).parent / spec).as_posix()
    norm = os.path.normpath(base).replace(os.sep, "/")
    candidates = [norm] + [norm + ext for ext in JS_EXT] + [f"{norm}/index{ext}" for ext in JS_EXT]
    if norm.endswith(".js"):
        candidates += [norm[:-3] + ".ts", norm[:-3] + ".tsx"]
    return next((c for c in candidates if c in files), None)


def js_graph(repo: Path, files: list[str], depth: int) -> dict[str, Any]:
    sources = [f for f in files if f.endswith(JS_EXT) and not f.endswith(".d.ts")]
    if not sources:
        return {}
    file_set = set(files)
    edges: Counter[tuple[str, str]] = Counter()
    external: dict[str, set[str]] = defaultdict(set)
    unresolved: Counter[str] = Counter()
    lines: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    for rel in sources:
        try:
            text = (repo / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        src = js_group(rel, depth)
        lines[src] += text.count("\n")
        counts[src] += 1
        for spec in JS_IMPORT.findall(text):
            if spec.startswith("."):
                target = js_resolve(spec, rel, file_set)
                if target is None:
                    unresolved[spec] += 1
                    continue
                dst = js_group(target, depth)
                if dst != src:
                    edges[(src, dst)] += 1
            elif not spec.startswith(("node:", "/", "http")):
                package = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
                if package.startswith(("$", "~")):
                    unresolved[spec] += 1
                else:
                    external[package].add(rel)
    return {
        "nodes": [{"id": n, "files": counts[n], "lines": lines[n]} for n in sorted(counts)],
        "edges": [{"from": a, "to": b, "imports": c} for (a, b), c in sorted(edges.items())],
        "external": [{"package": k, "files": len(v)} for k, v in sorted(external.items())],
        "unresolved_specifiers": dict(unresolved.most_common(20)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Module import graph as JSON.")
    parser.add_argument("repo", nargs="?", default=".", type=Path)
    parser.add_argument("--depth", type=int, default=2, help="how many name parts or folders make a module")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    files = list_files(repo)
    not_covered: Counter[str] = Counter()
    for rel in files:
        lang = OTHER_CODE.get(PurePosixPath(rel).suffix)
        if lang:
            not_covered[lang] += 1
    result = {
        "repo": repo.name,
        "depth": args.depth,
        "python": python_graph(repo, files, args.depth),
        "javascript": js_graph(repo, files, args.depth),
        "not_covered": dict(not_covered),
    }
    json.dump(result, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
