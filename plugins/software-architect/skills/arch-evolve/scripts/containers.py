#!/usr/bin/env python3
"""Find what runs in a repository, what it talks to, and what deployables share.

Usage: python3 containers.py REPO

Reads docker-compose files, Dockerfiles, .NET project files, package.json and pyproject.toml. Reports
the deployables and their stores and brokers, depends_on, calls between services found as URLs with a
service's name, loops among those calls, outside hosts, tables touched by more than one deployable, and
the settings the code reads, by name.

Compose files are read by indentation, because the standard library has no YAML: anchors and merges are
not followed. Values of settings are never read or printed. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", "bin", "obj"}
CODE = {".cs", ".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".sql"}
STORES = {
    "postgres": "database",
    "mysql": "database",
    "mariadb": "database",
    "mssql": "database",
    "sqlserver": "database",
    "mongo": "database",
    "redis": "cache",
    "memcached": "cache",
    "rabbitmq": "broker",
    "kafka": "broker",
    "nats": "broker",
    "elasticsearch": "search",
    "opensearch": "search",
    "qdrant": "search",
    "minio": "object store",
}
URL = re.compile(r"""https?://([a-zA-Z][\w.-]*)(?::\d+)?""")
TABLE_WRITE = re.compile(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO)\s+[\"\[`]?([a-zA-Z_]\w*)", re.I)
TABLE_READ = re.compile(r"\b(?:FROM|JOIN)\s+[\"\[`]?([a-zA-Z_]\w*)", re.I)
NOT_TABLES = {"select", "set", "where", "the", "a", "an", "values", "and", "or", "this", "that", "to", "of"}
SQL_HINT = re.compile(r"\b(select|insert|update|delete|merge)\b", re.I)
SETTINGS = [
    re.compile(r"""os\.(?:environ\.get|getenv)\(\s*['"](\w+)['"]"""),
    re.compile(r"""os\.environ\[\s*['"](\w+)['"]"""),
    re.compile(r"""process\.env\.(\w+)"""),
    re.compile(r"""Environment\.GetEnvironmentVariable\(\s*"(\w+)"\s*\)"""),
    re.compile(r"""(?:Configuration|config)\[\s*"([\w:]+)"\s*\]"""),
    re.compile(r"""GetConnectionString\(\s*"(\w+)"\s*\)"""),
]


def walk(repo: Path) -> list[str]:
    found = []
    for path in sorted(p for p in repo.rglob("*") if p.is_file()):
        rel = path.relative_to(repo)
        if not (SKIP_DIRS & set(rel.parts)):
            found.append(rel.as_posix())
    return found


def read_compose(text: str) -> dict[str, dict[str, Any]]:
    """Services, from indentation."""
    services: dict[str, dict[str, Any]] = {}
    in_services = False
    service_indent = -1
    current: dict[str, Any] | None = None
    key = ""
    key_indent = -1
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        body = raw.strip()
        if indent == 0:
            in_services = body.startswith("services:")
            current, service_indent = None, -1
            continue
        if not in_services:
            continue
        if service_indent < 0:
            service_indent = indent
        if indent == service_indent and body.endswith(":"):
            current = {"image": None, "build": None, "depends_on": [], "ports": [], "environment": []}
            services[body[:-1].strip("'\"")] = current
            key = ""
            continue
        if current is None:
            continue
        if indent > service_indent and (key_indent < 0 or indent <= key_indent or not key):
            match = re.match(r"([\w-]+):\s*(.*)$", body)
            if match:
                key, value = match.group(1), match.group(2).strip().strip("'\"")
                key_indent = indent
                if key in ("image", "build") and value:
                    current[key] = value
                elif key == "depends_on" and value.startswith("["):
                    current["depends_on"] = [v.strip(" '\"") for v in value.strip("[]").split(",")]
                continue
        if indent > key_indent:
            item = body[2:].strip() if body.startswith("- ") else body
            if key == "depends_on":
                current["depends_on"].append(item.rstrip(":").strip("'\""))
            elif key == "ports":
                current["ports"].append(item.strip("'\""))
            elif key == "environment":
                current["environment"].append(re.split(r"[:=]", item, maxsplit=1)[0].strip("'\" "))
            elif key == "build" and item.startswith("context:"):
                current["build"] = item.split(":", 1)[1].strip().strip("'\"")
    return services


def store_kind(image: str | None) -> str | None:
    text = (image or "").lower()
    return next((kind for name, kind in STORES.items() if name in text), None)


def read_csproj(repo: Path, rel: str) -> dict[str, Any]:
    try:
        root = ET.fromstring((repo / rel).read_text(encoding="utf-8", errors="replace").lstrip("﻿"))
    except ET.ParseError:
        return {"path": rel, "note": "could not be parsed"}
    output = root.findtext(".//OutputType")
    sdk = root.get("Sdk", "")
    folder = PurePosixPath(rel).parent
    references = []
    for item in root.iter("ProjectReference"):
        include = (item.get("Include") or "").replace("\\", "/")
        parts: list[str] = list(folder.parts)
        for part in PurePosixPath(include).parts:
            if part == "..":
                parts = parts[:-1]
            elif part != ".":
                parts.append(part)
        references.append("/".join(parts))
    kind = "web" if sdk.endswith(".Web") else "console" if (output or "").lower() == "exe" else "library"
    return {"path": rel, "kind": kind, "framework": root.findtext(".//TargetFramework"), "references": references}


def read_package(repo: Path, rel: str) -> dict[str, Any]:
    try:
        data = json.loads((repo / rel).read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {"path": rel, "note": "could not be parsed"}
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    frameworks = [
        name
        for name in ("@angular/core", "react", "vue", "svelte", "next", "express", "fastify", "@nestjs/core")
        if name in deps
    ]
    return {"path": rel, "name": data.get("name"), "frameworks": frameworks, "scripts": sorted(data.get("scripts", {}))}


def read_pyproject(repo: Path, rel: str) -> dict[str, Any]:
    try:
        data = tomllib.loads((repo / rel).read_text(encoding="utf-8", errors="replace"))
    except tomllib.TOMLDecodeError:
        return {"path": rel, "note": "could not be parsed"}
    project = data.get("project", {})
    return {"path": rel, "name": project.get("name"), "entry_points": sorted(project.get("scripts", {}))}


def owners(services: dict[str, dict[str, Any]], projects: list[dict[str, Any]]) -> dict[str, str]:
    """Folder -> the deployable that ships it, following .NET project references."""
    folders: dict[str, str] = {}
    by_path = {p["path"]: p for p in projects}
    for name, service in services.items():
        if not service["build"]:
            continue
        folder = PurePosixPath(service["build"].removeprefix("./")).as_posix()
        folders[folder] = name
        pending = [p for p in by_path if p.startswith(f"{folder}/")]
        seen: set[str] = set()
        while pending:
            path = pending.pop()
            if path in seen:
                continue
            seen.add(path)
            for reference in by_path.get(path, {}).get("references", []):
                folders.setdefault(str(PurePosixPath(reference).parent), name)
                pending.append(reference)
    return folders


def owner_of(rel: str, folders: dict[str, str]) -> str | None:
    matches = [f for f in folders if f == "." or rel.startswith(f"{f}/")]
    return folders[max(matches, key=len)] if matches else None


def loops(calls: dict[tuple[str, str], list[dict[str, Any]]]) -> list[list[str]]:
    found = []
    for a, b in sorted(calls):
        if a < b and (b, a) in calls:
            found.append([a, b])
    graph: dict[str, set[str]] = defaultdict(set)
    for a, b in calls:
        graph[a].add(b)
    for a in sorted(graph):
        for b in sorted(graph[a]):
            for c in sorted(graph.get(b, set())):
                if a < b and a < c and b != c and a in graph.get(c, set()):
                    found.append([a, b, c])
    return found


def inventory(repo: Path) -> dict[str, Any]:
    files = walk(repo)
    services: dict[str, dict[str, Any]] = {}
    compose_files = []
    for rel in files:
        if re.fullmatch(r"(docker-)?compose([.\w-]*)\.ya?ml", PurePosixPath(rel).name):
            compose_files.append(rel)
            services.update(read_compose((repo / rel).read_text(encoding="utf-8", errors="replace")))
    projects: list[dict[str, Any]] = []
    for rel in files:
        name = PurePosixPath(rel).name
        if name.endswith(".csproj"):
            projects.append({"type": ".NET", **read_csproj(repo, rel)})
        elif name == "package.json":
            projects.append({"type": "node", **read_package(repo, rel)})
        elif name == "pyproject.toml":
            projects.append({"type": "python", **read_pyproject(repo, rel)})
    folders = owners(services, projects)
    calls: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    outside: dict[str, list[str]] = defaultdict(list)
    touches: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    settings: dict[str, set[str]] = defaultdict(set)
    for rel in files:
        path = PurePosixPath(rel)
        if path.suffix.lower() not in CODE:
            continue
        owner = owner_of(rel, folders) or "(no deployable)"
        for number, line in enumerate((repo / rel).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for found in URL.finditer(line):
                host = found.group(1).lower()
                if host in services and host != owner:
                    calls[(owner, host)].append({"file": rel, "line": number})
                elif "." in host and not host.endswith(("example.com", "w3.org", "localhost")):
                    outside[host].append(rel)
            if SQL_HINT.search(line):
                written = {m.group(1).lower() for m in TABLE_WRITE.finditer(line)} - NOT_TABLES
                read = {m.group(1).lower() for m in TABLE_READ.finditer(line)} - NOT_TABLES - written
                for table in written:
                    touches[table][owner].append({"file": rel, "line": number, "mode": "write"})
                for table in read:
                    touches[table][owner].append({"file": rel, "line": number, "mode": "read"})
            for pattern in SETTINGS:
                for found in pattern.finditer(line):
                    settings[found.group(1)].add(owner)
    shared = [
        {"table": table, "deployables": {o: places[:3] for o, places in sorted(by.items())}}
        for table, by in sorted(touches.items())
        if len(by) > 1 and any(p["mode"] == "write" for places in by.values() for p in places)
    ]
    deployables = [
        {
            "name": name,
            "kind": store_kind(service["image"]) or ("built here" if service["build"] else "image"),
            "image": service["image"],
            "build": service["build"],
            "depends_on": service["depends_on"],
            "ports": service["ports"],
            "settings": sorted(service["environment"]),
        }
        for name, service in sorted(services.items())
    ]
    return {
        "compose_files": compose_files,
        "dockerfiles": [f for f in files if PurePosixPath(f).name.lower().startswith("dockerfile")],
        "deployables": deployables,
        "projects": projects,
        "calls_between_services": [
            {"from": a, "to": b, "where": places[:3]} for (a, b), places in sorted(calls.items())
        ],
        "loops": loops(calls),
        "outside_hosts": {host: sorted(set(places))[:3] for host, places in sorted(outside.items())},
        "tables_shared": shared,
        "settings_read": {name: sorted(by) for name, by in sorted(settings.items())},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find what runs in a repository and what it talks to.")
    parser.add_argument("repo", type=Path, nargs="?", default=Path("."))
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        print(f"not a folder: {args.repo}", file=sys.stderr)
        return 2
    json.dump(inventory(args.repo), sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
