#!/usr/bin/env python3
"""Count what a repository holds, so the map starts from numbers rather than impressions.

Usage: python3 inventory.py [REPO] [--days 180] [--top 15]

Prints JSON: files and lines per language and per top folder, manifests, entry points, tests,
CI, containers, docs, environment variable names (never values), TODO markers, the largest
files and git activity. Churn is counted back from the last commit, not from today, so an idle
repo still shows where work went. Read-only; standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "target",
    "bin",
    "obj",
    ".idea",
    ".vscode",
    "coverage",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".angular",
    "vendor",
    ".gradle",
    ".terraform",
}
LANGUAGES = {
    ".py": "Python",
    ".pyi": "Python",
    ".ipynb": "Notebook",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".svelte": "Svelte",
    ".vue": "Vue",
    ".astro": "Astro",
    ".cs": "C#",
    ".csproj": "MSBuild",
    ".fs": "F#",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".scala": "Scala",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".xml": "XML",
    ".tf": "Terraform",
    ".graphql": "GraphQL",
    ".proto": "Protobuf",
    ".dart": "Dart",
    ".lua": "Lua",
    ".r": "R",
    ".jl": "Julia",
}
CODE_LANGUAGES = {
    "Python",
    "JavaScript",
    "TypeScript",
    "Svelte",
    "Vue",
    "Astro",
    "C#",
    "F#",
    "Java",
    "Kotlin",
    "Go",
    "Rust",
    "Ruby",
    "PHP",
    "Swift",
    "C",
    "C++",
    "Scala",
    "SQL",
    "Shell",
    "PowerShell",
    "Dart",
    "Lua",
    "R",
    "Julia",
}
MANIFESTS = {
    "pyproject.toml": "python-project",
    "setup.py": "python-setup",
    "setup.cfg": "python-setup",
    "requirements.txt": "python-requirements",
    "uv.lock": "python-lock",
    "poetry.lock": "python-lock",
    "Pipfile": "python-pipenv",
    "Pipfile.lock": "python-lock",
    "package.json": "node-package",
    "package-lock.json": "node-lock",
    "pnpm-lock.yaml": "node-lock",
    "yarn.lock": "node-lock",
    "go.mod": "go-module",
    "Cargo.toml": "rust-crate",
    "Gemfile": "ruby-gems",
    "composer.json": "php-composer",
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
    "Directory.Packages.props": "nuget-central",
    "global.json": "dotnet-sdk",
    "Makefile": "make",
    "justfile": "just",
    "Taskfile.yml": "task",
}
CI_PATTERNS = (
    re.compile(r"^\.github/workflows/[^/]+\.ya?ml$"),
    re.compile(r"(^|/)azure-pipelines[^/]*\.ya?ml$"),
    re.compile(r"^\.gitlab-ci\.yml$"),
    re.compile(r"(^|/)Jenkinsfile$"),
    re.compile(r"^\.circleci/config\.yml$"),
    re.compile(r"^bitbucket-pipelines\.yml$"),
    re.compile(r"^\.pipelines?/.+\.ya?ml$"),
)
TEST_PATTERNS = (
    re.compile(r"(^|/)tests?/"),
    re.compile(r"(^|/)test_[^/]+\.py$"),
    re.compile(r"_test\.(py|go)$"),
    re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$"),
    re.compile(r"(^|/)__tests__/"),
    re.compile(r"Tests?\.cs$"),
    re.compile(r"(^|/)[^/]*\.Tests?/"),
    re.compile(r"(^|/)src/test/"),
    re.compile(r"(^|/)spec/"),
)
ENV_PATTERNS = (
    re.compile(r"os\.environ(?:\.get)?\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"os\.environ\[\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"os\.getenv\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]{2,})"),
    re.compile(r"process\.env\[\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"import\.meta\.env\.([A-Z][A-Z0-9_]{2,})"),
    re.compile(r"GetEnvironmentVariable\(\s*\"([A-Z][A-Z0-9_]{2,})\""),
    re.compile(r"env::var\(\s*\"([A-Z][A-Z0-9_]{2,})\""),
    re.compile(r"os\.Getenv\(\s*\"([A-Z][A-Z0-9_]{2,})\""),
    re.compile(r"^\s*ENV\s+([A-Z][A-Z0-9_]{2,})[= ]"),
)
ENV_EXAMPLES = {".env.example", ".env.sample", ".env.template", ".env.dist", "example.env"}
SERVER_HINTS = (
    (re.compile(r"\bFastAPI\("), "FastAPI app"),
    (re.compile(r"\bFlask\(__name__"), "Flask app"),
    (re.compile(r"\buvicorn\.run\("), "uvicorn server"),
    (re.compile(r"\b(Threading)?HTTPServer\("), "http.server"),
    (re.compile(r"\bexpress\(\)"), "Express app"),
    (re.compile(r"\bWebApplication\.CreateBuilder\("), "ASP.NET app"),
    (re.compile(r"\bCelery\("), "Celery worker"),
    (re.compile(r"\bcreateServer\("), "Node server"),
    (re.compile(r"\bBackgroundService\b"), ".NET background service"),
    (re.compile(r"@app\.task\b"), "task queue"),
)
MARKERS = ("TODO", "FIXME", "HACK", "XXX")
MAX_BYTES = 2_000_000


def run_git(repo: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout


def list_files(repo: Path) -> tuple[list[str], bool]:
    out = run_git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if out is not None and run_git(repo, "rev-parse", "--is-inside-work-tree"):
        files = sorted({f for f in out.split("\0") if f and (repo / f).is_file()})
        return files, True
    found: list[str] = []
    for root, dirs, names in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            found.append((Path(root) / name).relative_to(repo).as_posix())
    return found, False


def read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def language_of(rel: str) -> str:
    name = PurePosixPath(rel).name
    if name == "Dockerfile" or name.startswith("Dockerfile."):
        return "Dockerfile"
    return LANGUAGES.get(PurePosixPath(rel).suffix.lower(), "other")


def is_test(rel: str) -> bool:
    return any(p.search(rel) for p in TEST_PATTERNS)


def is_env_file(rel: str) -> bool:
    name = PurePosixPath(rel).name
    return (name == ".env" or name.startswith(".env.")) and name not in ENV_EXAMPLES


def python_scripts(repo: Path, rel: str, files: set[str]) -> list[dict[str, Any]]:
    try:
        data = tomllib.loads((repo / rel).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    tables = [
        ("console script", data.get("project", {}).get("scripts", {})),
        ("gui script", data.get("project", {}).get("gui-scripts", {})),
        ("poetry script", data.get("tool", {}).get("poetry", {}).get("scripts", {})),
    ]
    found = []
    base = PurePosixPath(rel).parent
    for kind, table in tables:
        for name, target in table.items() if isinstance(table, dict) else []:
            module = str(target).split(":")[0]
            candidates = [
                (base / prefix / (module.replace(".", "/") + suffix)).as_posix().lstrip("./")
                for prefix in ("src", ".")
                for suffix in (".py", "/__init__.py")
            ]
            path = next((c for c in candidates if c in files), None)
            found.append({"kind": kind, "name": name, "target": str(target), "path": path or rel, "line": None})
    return found


def node_scripts(repo: Path, rel: str) -> list[dict[str, Any]]:
    try:
        data = json.loads((repo / rel).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    found: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return found
    bins = data.get("bin")
    if isinstance(bins, str):
        bins = {data.get("name", "bin"): bins}
    for name, target in (bins or {}).items():
        found.append({"kind": "npm bin", "name": name, "target": target, "path": rel, "line": None})
    if isinstance(data.get("main"), str):
        found.append({"kind": "npm main", "name": "main", "target": data["main"], "path": rel, "line": None})
    for name, command in (data.get("scripts") or {}).items():
        if name in {"start", "dev", "serve", "preview", "worker", "build"} or name.startswith(("start:", "dev:")):
            found.append({"kind": "npm script", "name": name, "target": command, "path": rel, "line": None})
    return found


def scan_text(rel: str, text: str, out: dict[str, Any]) -> None:
    lines = text.splitlines()
    name = PurePosixPath(rel).name
    lang = language_of(rel)
    for no, line in enumerate(lines, 1):
        if lang == "Python" and re.match(r"if\s+__name__\s*==\s*['\"]__main__['\"]\s*:", line.strip()):
            out["entry_points"].append(
                {"kind": "python __main__ guard", "name": rel, "target": "", "path": rel, "line": no}
            )
        if lang == "Dockerfile" and re.match(r"\s*(CMD|ENTRYPOINT)\b", line):
            out["entry_points"].append(
                {"kind": "container command", "name": name, "target": line.strip(), "path": rel, "line": no}
            )
        if name == "Procfile" and ":" in line:
            out["entry_points"].append(
                {"kind": "Procfile", "name": line.split(":")[0], "target": line.strip(), "path": rel, "line": no}
            )
        if lang in ("C#",) and re.search(r"\bstatic\s+(async\s+)?[\w<>]+\s+Main\s*\(", line):
            out["entry_points"].append({"kind": ".NET Main", "name": rel, "target": "", "path": rel, "line": no})
        if lang == "Go" and re.match(r"func\s+main\s*\(\s*\)", line):
            out["entry_points"].append({"kind": "go main", "name": rel, "target": "", "path": rel, "line": no})
        if lang in CODE_LANGUAGES:
            for pattern, label in SERVER_HINTS:
                if pattern.search(line):
                    out["entry_points"].append(
                        {"kind": "hint: " + label, "name": rel, "target": line.strip()[:120], "path": rel, "line": no}
                    )
        for pattern in ENV_PATTERNS:
            for match in pattern.finditer(line):
                out["env"][match.group(1)].append(f"{rel}:{no}")
        for marker in MARKERS:
            if re.search(rf"\b{marker}\b", line) and lang in CODE_LANGUAGES:
                out["markers"][marker] += 1
                if len(out["marker_examples"]) < 12:
                    out["marker_examples"].append(
                        {"marker": marker, "where": f"{rel}:{no}", "text": line.strip()[:140]}
                    )
    if name == "__main__.py" and lang == "Python":
        out["entry_points"].append({"kind": "python -m package", "name": rel, "target": "", "path": rel, "line": 1})


def git_activity(repo: Path, days: int, top: int, files: set[str]) -> dict[str, Any]:
    head = run_git(repo, "log", "-1", "--format=%h%x09%cI")
    if not head:
        return {"is_repo": False}
    short, head_date = head.strip().split("\t")
    first = (run_git(repo, "log", "--reverse", "--format=%cI") or "").splitlines()
    count = len((run_git(repo, "rev-list", "HEAD") or "").split())
    authors = {a for a in (run_git(repo, "log", "--format=%aE") or "").splitlines() if a}
    since = (datetime.fromisoformat(head_date) - timedelta(days=days)).isoformat()
    churn: Counter[str] = Counter()
    log = run_git(repo, "log", f"--since={since}", "--format=", "--name-only", "--no-renames") or ""
    for line in log.splitlines():
        if line and line in files:
            churn[line] += 1
    branch = (run_git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
    return {
        "is_repo": True,
        "head": short,
        "branch": branch,
        "commits": count,
        "first_commit": first[0][:10] if first else None,
        "last_commit": head_date[:10],
        "authors": len(authors),
        "churn_window": f"{days} days before the last commit ({since[:10]} to {head_date[:10]})",
        "churn": [{"path": p, "commits": n} for p, n in churn.most_common(top)],
        "commits_per_file": dict(sorted(churn.items())[:400]),
    }


def inventory(repo: Path, days: int, top: int) -> dict[str, Any]:
    files, is_git = list_files(repo)
    file_set = set(files)
    by_lang: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_folder: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    sizes: list[tuple[int, str]] = []
    scan: dict[str, Any] = {"entry_points": [], "env": defaultdict(list), "markers": Counter(), "marker_examples": []}
    manifests, ci, docker, docs, env_files, env_examples = [], [], [], [], [], []
    tests: dict[str, Any] = {"files": 0, "lines": 0, "folders": set()}
    skipped: Counter[str] = Counter()
    for rel in files:
        path = repo / rel
        name = PurePosixPath(rel).name
        if is_env_file(rel):
            env_files.append(rel)  # never read: it may hold secrets
            continue
        text = read_text(path)
        if text is None:
            skipped["binary or over 2 MB"] += 1
            continue
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        lang = language_of(rel)
        by_lang[lang][0] += 1
        by_lang[lang][1] += lines
        top_folder = rel.split("/")[0] if "/" in rel else "(root)"
        by_folder[top_folder][0] += 1
        by_folder[top_folder][1] += lines
        if lang in CODE_LANGUAGES:
            sizes.append((lines, rel))
        if (
            name in MANIFESTS
            or name.endswith((".csproj", ".fsproj", ".sln"))
            or re.match(r"requirements[\w.-]*\.txt$", name)
        ):
            kind = MANIFESTS.get(name, "python-requirements" if name.startswith("requirements") else "dotnet")
            manifests.append({"path": rel, "kind": kind})
            if name == "pyproject.toml":
                scan["entry_points"].extend(python_scripts(repo, rel, file_set))
            elif name == "package.json":
                scan["entry_points"].extend(node_scripts(repo, rel))
        if any(p.search(rel) for p in CI_PATTERNS):
            ci.append(rel)
        if lang == "Dockerfile" or re.match(r"(docker-)?compose[\w.-]*\.ya?ml$", name):
            docker.append(rel)
        if lang in ("Markdown", "reStructuredText") and (
            rel.startswith("docs/") or "/" not in rel or "adr" in rel.lower()
        ):
            docs.append(rel)
        if name in ENV_EXAMPLES:
            env_examples.append(rel)
            for no, line in enumerate(text.splitlines(), 1):
                match = re.match(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]{2,})\s*=", line)
                if match:
                    scan["env"][match.group(1)].append(f"{rel}:{no}")
        if is_test(rel) and lang in CODE_LANGUAGES:
            tests["files"] += 1
            tests["lines"] += lines
            tests["folders"].add(rel.rsplit("/", 1)[0] if "/" in rel else "(root)")
        if lang in CODE_LANGUAGES or lang == "Dockerfile" or name == "Procfile":
            scan_text(rel, text, scan)
    code_lines = sum(v[1] for k, v in by_lang.items() if k in CODE_LANGUAGES)
    return {
        "repo": repo.name,
        "path": str(repo),
        "git": git_activity(repo, days, top, file_set) if is_git else {"is_repo": False},
        "files": {
            "total": len(files),
            "code_lines": code_lines,
            "by_language": [
                {"language": k, "files": v[0], "lines": v[1]}
                for k, v in sorted(by_lang.items(), key=lambda kv: -kv[1][1])
            ],
            "by_folder": [
                {"folder": k, "files": v[0], "lines": v[1]}
                for k, v in sorted(by_folder.items(), key=lambda kv: -kv[1][1])
            ],
            "skipped": dict(skipped),
        },
        "manifests": manifests,
        "entry_points": scan["entry_points"],
        "tests": {
            "files": tests["files"],
            "lines": tests["lines"],
            "folders": sorted(tests["folders"]),
            "share_of_code_lines": round(tests["lines"] / code_lines, 2) if code_lines else None,
        },
        "ci": ci,
        "containers": docker,
        "docs": docs,
        "env_vars": [{"name": k, "where": sorted(set(v))[:6]} for k, v in sorted(scan["env"].items())],
        "env_files_not_read": env_files,
        "markers": dict(scan["markers"]),
        "marker_examples": scan["marker_examples"],
        "largest_code_files": [{"path": p, "lines": n} for n, p in sorted(sizes, reverse=True)[:top]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory a repository as JSON.")
    parser.add_argument("repo", nargs="?", default=".", type=Path)
    parser.add_argument("--days", type=int, default=180, help="churn window before the last commit")
    parser.add_argument("--top", type=int, default=15, help="how many churn and size entries to keep")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if not repo.is_dir():
        print(f"not a directory: {repo}", file=sys.stderr)
        return 2
    json.dump(inventory(repo, args.days, args.top), sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
