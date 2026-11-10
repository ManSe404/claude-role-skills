#!/usr/bin/env python3
"""Measure the structure of a repository: the module graph, its cycles and layer breaks, and what git says.

Usage: python3 code_graph.py REPO [--depth N] [--layers domain,application,infrastructure,api]
       python3 code_graph.py REPO --git [--months 12] [--max-files 40]

Modules: C# namespaces, Java packages, Go packages, Python modules (ast, exact) and JavaScript or
TypeScript folders (relative imports by pattern: path aliases and dynamic imports are missed). Other
languages are counted under not_covered. --depth keeps the first N parts of a module name.

For each module: files, lines, fan-in, fan-out and instability (fan-out / (fan-in + fan-out)). Cycles are
groups of modules that reach each other. A layer break is a module of an inner layer using one of an
outer layer; --layers lists the layers from the innermost out and matches them against module names.

--git adds, from the history: files changed together more often than chance, and whether any import links
their modules (a pair with no link is hidden coupling); hot spots (commits x lines); and per module the
commits, the authors and the share of the top author.

Read-only, standard library only, JSON on stdout. Git calls have a timeout.
"""

from __future__ import annotations

import argparse
import ast
import itertools
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
OTHER = {".kt": "Kotlin", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".swift": "Swift", ".scala": "Scala"}
JS_IMPORT = re.compile(
    r"""(?:import\s[^'"]*?from\s*|import\s*\(\s*|require\s*\(\s*|export\s[^'"]*?from\s*|import\s+)['"]([^'"]+)['"]"""
)
CS_NAMESPACE = re.compile(r"^\s*namespace\s+([\w.]+)", re.M)
CS_USING = re.compile(r"^\s*(?:global\s+)?using\s+(?:static\s+)?(?:\w+\s*=\s*)?([\w.]+)\s*;", re.M)
JAVA_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)(?:\.\*)?\s*;", re.M)
GO_MODULE = re.compile(r"^module\s+(\S+)", re.M)
GO_IMPORT = re.compile(r'"([^"\n]+)"')
GO_BLOCK = re.compile(r"^import\s*(\([^)]*\)|\"[^\"]+\")", re.M)
LAYERS = ["domain", "application", "infrastructure", "api"]
LAYER_WORDS = {
    "domain": "domain|core|model|entities",
    "application": "application|usecases|use_cases",
    "infrastructure": "infrastructure|infra|persistence|repositories|adapters",
    "api": "api|web|controllers|ui|presentation|endpoints",
}


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


def is_test(rel: str) -> bool:
    name = PurePosixPath(rel).name.lower()
    parts = {p.lower() for p in PurePosixPath(rel).parts[:-1]}
    return bool(parts & {"test", "tests", "__tests__", "spec"}) or bool(
        re.search(r"(^test_|_test\.|\.test\.|\.spec\.|tests?\.cs$)", name)
    )


class Graph:
    """Modules, and which file makes which module depend on which."""

    def __init__(self, depth: int) -> None:
        self.depth = depth
        self.files: dict[str, str] = {}  # file -> module
        self.lines: Counter[str] = Counter()
        self.edges: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    def group(self, module: str, sep: str = ".") -> str:
        return sep.join(module.split(sep)[: self.depth]) if self.depth else module

    def add_file(self, rel: str, module: str, source: str) -> None:
        self.files[rel] = module
        self.lines[module] += source.count("\n") + 1

    def add_edge(self, source: str, target: str, rel: str, line: int) -> None:
        if source != target:
            self.edges[(source, target)].append({"file": rel, "line": line})


def line_of(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def read_csharp(repo: Path, files: list[str], graph: Graph) -> None:
    sources: dict[str, str] = {}
    declared: set[str] = set()
    for rel in files:
        if rel.endswith(".cs"):
            text = (repo / rel).read_text(encoding="utf-8", errors="replace")
            found = CS_NAMESPACE.search(text)
            if found:
                sources[rel] = text
                declared.add(found.group(1))
    for rel, text in sources.items():
        match = CS_NAMESPACE.search(text)
        assert match is not None
        module = graph.group(match.group(1))
        graph.add_file(rel, module, text)
        for found in CS_USING.finditer(text):
            if found.group(1) in declared:
                graph.add_edge(module, graph.group(found.group(1)), rel, line_of(text, found.start()))


def read_java(repo: Path, files: list[str], graph: Graph) -> None:
    sources: dict[str, tuple[str, str]] = {}
    declared: set[str] = set()
    for rel in files:
        if rel.endswith(".java"):
            text = (repo / rel).read_text(encoding="utf-8", errors="replace")
            found = JAVA_PACKAGE.search(text)
            if found:
                sources[rel] = (found.group(1), text)
                declared.add(found.group(1))
    for rel, (package, text) in sources.items():
        module = graph.group(package)
        graph.add_file(rel, module, text)
        for found in JAVA_IMPORT.finditer(text):
            name = found.group(1)
            while name and name not in declared:
                name = name.rpartition(".")[0]
            if name:
                graph.add_edge(module, graph.group(name), rel, line_of(text, found.start()))


def read_go(repo: Path, files: list[str], graph: Graph) -> None:
    modules = [rel for rel in files if PurePosixPath(rel).name == "go.mod"]
    if not modules:
        return
    found = GO_MODULE.search((repo / modules[0]).read_text(encoding="utf-8", errors="replace"))
    if not found:
        return
    base = found.group(1)
    root = str(PurePosixPath(modules[0]).parent)
    root = "" if root == "." else f"{root}/"
    for rel in files:
        if not rel.endswith(".go") or rel.endswith("_test.go"):
            continue
        text = (repo / rel).read_text(encoding="utf-8", errors="replace")
        folder = str(PurePosixPath(rel).parent)
        module = graph.group(folder if folder != "." else "(root)", "/")
        graph.add_file(rel, module, text)
        for block in GO_BLOCK.finditer(text):
            for path in GO_IMPORT.finditer(block.group(1)):
                if path.group(1).startswith(base):
                    target = root + path.group(1)[len(base) :].lstrip("/")
                    graph.add_edge(
                        module, graph.group(target.rstrip("/") or "(root)", "/"), rel, line_of(text, block.start())
                    )


def python_name(rel: str) -> str | None:
    parts = list(PurePosixPath(rel).with_suffix("").parts)
    if "src" in parts:
        parts = parts[parts.index("src") + 1 :]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts or any(not p.isidentifier() for p in parts):
        return None
    return ".".join(parts)


def read_python(repo: Path, files: list[str], graph: Graph, notes: list[str]) -> None:
    names = {python_name(rel): rel for rel in files if rel.endswith(".py")}
    names.pop(None, None)
    depth = graph.depth or 2

    def group(name: str) -> str:
        return ".".join(name.split(".")[:depth])

    def resolve(target: str) -> str | None:
        while target:
            if target in names:
                return target
            target = target.rpartition(".")[0]
        return None

    for name, rel in names.items():
        assert name is not None
        source = (repo / rel).read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source, filename=rel)
        except (SyntaxError, ValueError):
            notes.append(f"{rel}: could not be parsed")
            continue
        module = group(name)
        graph.add_file(rel, module, source)
        package = name if rel.endswith("__init__.py") else name.rpartition(".")[0]
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parts = package.split(".")
                    parts = parts[: len(parts) - (node.level - 1)]
                    base = ".".join([*parts, *([node.module] if node.module else [])])
                targets = [f"{base}.{alias.name}" if base else alias.name for alias in node.names]
            for target in targets:
                internal = resolve(target)
                if internal:
                    graph.add_edge(module, group(internal), rel, getattr(node, "lineno", 1))


def js_module(rel: str, depth: int) -> str:
    parts = [p for p in PurePosixPath(rel).parent.parts if p != "src"]
    return "/".join(parts[: depth or 3]) or "(root)"


def read_js(repo: Path, files: list[str], graph: Graph) -> None:
    known = {rel for rel in files if rel.endswith(JS_EXT)}

    def resolve(spec: str, rel: str) -> str | None:
        base = os.path.normpath(os.path.join(os.path.dirname(rel), spec)).replace(os.sep, "/")
        for candidate in [base, *(base + e for e in JS_EXT), *(f"{base}/index{e}" for e in JS_EXT)]:
            if candidate in known:
                return candidate
        return None

    for rel in sorted(known):
        text = (repo / rel).read_text(encoding="utf-8", errors="replace")
        module = js_module(rel, graph.depth)
        graph.add_file(rel, module, text)
        for found in JS_IMPORT.finditer(text):
            if found.group(1).startswith("."):
                target = resolve(found.group(1), rel)
                if target:
                    graph.add_edge(module, js_module(target, graph.depth), rel, line_of(text, found.start()))


def cycles(edges: list[tuple[str, str]]) -> list[list[str]]:
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 10_000))
    out: dict[str, list[str]] = defaultdict(list)
    for a, b in edges:
        out[a].append(b)
        out[b]
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    found: list[list[str]] = []

    def visit(v: str) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on.add(v)
        for w in out[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            group = []
            while True:
                w = stack.pop()
                on.discard(w)
                group.append(w)
                if w == v:
                    break
            if len(group) > 1:
                found.append(sorted(group))

    for v in sorted(out):
        if v not in index:
            visit(v)
    return sorted(found)


def layer_rank(module: str, layers: list[str]) -> int | None:
    for rank, layer in enumerate(layers):
        words = LAYER_WORDS.get(layer.lower(), re.escape(layer))
        if re.search(rf"(^|[./_-])({words})($|[./_-])", module, re.I):
            return rank
    return None


def history(repo: Path, months: int, max_files: int) -> list[tuple[str, list[str]]]:
    """(author, files) per commit, newest first. Commits touching too many files say nothing about coupling."""
    done = subprocess.run(
        ["git", "log", f"--since={months} months ago", "--no-merges", "--name-only", "--format=%x01%an"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if done.returncode != 0:
        return []
    commits = []
    for chunk in done.stdout.split("\x01")[1:]:
        lines = [line for line in chunk.splitlines() if line.strip()]
        if lines:
            commits.append((lines[0], lines[1:]))
    return [c for c in commits if len(c[1]) <= max_files]


def measure_git(graph: Graph, repo: Path, months: int, max_files: int) -> dict[str, Any]:
    commits = [
        (author, [f for f in touched if f in graph.files]) for author, touched in history(repo, months, max_files)
    ]
    changes: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    authors: dict[str, Counter[str]] = defaultdict(Counter)
    for author, touched in commits:
        changes.update(touched)
        for module in {graph.files[f] for f in touched}:
            authors[module][author] += 1
        pairs.update(itertools.combinations(sorted(touched), 2))
    linked = {frozenset(pair) for pair in graph.edges}
    coupled = []
    for (a, b), together in pairs.most_common():
        confidence = together / min(changes[a], changes[b])
        if together >= 3 and confidence >= 0.6:
            mod_a, mod_b = graph.files[a], graph.files[b]
            same = mod_a == mod_b
            coupled.append(
                {
                    "a": a,
                    "b": b,
                    "together": together,
                    "confidence": round(confidence, 2),
                    "same_module": same,
                    "import_link": same or frozenset((mod_a, mod_b)) in linked,
                }
            )
    sizes = {}
    for rel in changes:
        sizes[rel] = (repo / rel).read_text(encoding="utf-8", errors="replace").count("\n") + 1
    hot = sorted(changes, key=lambda f: (-changes[f] * sizes[f], f))[:15]
    return {
        "commits_read": len(commits),
        "months": months,
        "coupled_files": coupled[:40],
        "hidden_coupling": [c for c in coupled if not c["import_link"]][:20],
        "hot_spots": [
            {"file": f, "commits": changes[f], "lines": sizes[f], "score": changes[f] * sizes[f]} for f in hot
        ],
        "owners": {
            module: {
                "commits": sum(counts.values()),
                "authors": len(counts),
                "top_author": counts.most_common(1)[0][0],
                "top_share": round(counts.most_common(1)[0][1] / sum(counts.values()), 2),
                "one_person": len(counts) == 1 and sum(counts.values()) >= 3,
            }
            for module, counts in sorted(authors.items())
        },
    }


def analyse(repo: Path, depth: int, layers: list[str], tests: bool) -> tuple[Graph, dict[str, Any]]:
    all_files = list_files(repo)
    files = [f for f in all_files if tests or not is_test(f)]
    graph = Graph(depth)
    notes: list[str] = []
    read_csharp(repo, files, graph)
    read_java(repo, files, graph)
    read_go(repo, files, graph)
    read_python(repo, files, graph, notes)
    read_js(repo, files, graph)
    fan_in: Counter[str] = Counter()
    fan_out: Counter[str] = Counter()
    for a, b in graph.edges:
        fan_out[a] += 1
        fan_in[b] += 1
    per_module: Counter[str] = Counter(graph.files.values())
    modules = []
    for name in sorted(per_module):
        total = fan_in[name] + fan_out[name]
        modules.append(
            {
                "name": name,
                "files": per_module[name],
                "lines": graph.lines[name],
                "fan_in": fan_in[name],
                "fan_out": fan_out[name],
                "instability": round(fan_out[name] / total, 2) if total else None,
            }
        )
    breaks = []
    for (a, b), places in sorted(graph.edges.items()):
        ra, rb = layer_rank(a, layers), layer_rank(b, layers)
        if ra is not None and rb is not None and ra < rb:
            breaks.append({"from": a, "to": b, "from_layer": layers[ra], "to_layer": layers[rb], "where": places[:5]})
    found = cycles(list(graph.edges))
    not_covered = Counter(OTHER[s] for f in all_files if (s := PurePosixPath(f).suffix.lower()) in OTHER)
    result = {
        "counts": {"modules": len(modules), "files": len(graph.files), "edges": len(graph.edges), "cycles": len(found)},
        "modules": sorted(modules, key=lambda m: (-int(str(m["fan_in"])) - int(str(m["fan_out"])), str(m["name"]))),
        "edges": [
            {"from": a, "to": b, "imports": len(places), "where": places[:3]}
            for (a, b), places in sorted(graph.edges.items())
        ],
        "cycles": [
            {
                "modules": group,
                "edges": [
                    {"from": a, "to": b, "where": places[:3]}
                    for (a, b), places in sorted(graph.edges.items())
                    if a in group and b in group
                ],
            }
            for group in found
        ],
        "layers": layers,
        "layer_breaks": breaks,
        "not_covered": dict(not_covered),
        "notes": notes,
    }
    return graph, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the structure of a repository.")
    parser.add_argument("repo", type=Path, nargs="?", default=Path("."))
    parser.add_argument("--depth", type=int, default=0, help="keep the first N parts of a module name")
    parser.add_argument("--layers", default=",".join(LAYERS), help="layers from the innermost out, comma separated")
    parser.add_argument("--tests", action="store_true", help="include test files")
    parser.add_argument("--git", action="store_true", help="add change coupling, hot spots and owners")
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--max-files", type=int, default=40, help="ignore commits touching more files than this")
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        print(f"not a folder: {args.repo}", file=sys.stderr)
        return 2
    graph, result = analyse(args.repo, args.depth, [x.strip() for x in args.layers.split(",") if x.strip()], args.tests)
    if args.git:
        result["git"] = measure_git(graph, args.repo, args.months, args.max_files)
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
