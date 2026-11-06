#!/usr/bin/env python3
"""Inventory a repository's dependencies; with --online, add known vulnerabilities, latest versions and licences.

Usage: python3 deps.py [REPO] [--online] [--timeout 10]

Offline (the default) it reads manifests and lock files only: Python (pyproject.toml,
requirements*.txt, uv.lock, poetry.lock, Pipfile.lock), npm (package.json, package-lock.json)
and NuGet (*.csproj, Directory.Packages.props, packages.lock.json). It reports direct and
locked versions, ranges without a lock, duplicates, and for Python and npm where each direct
dependency is imported.

--online sends package names and versions, nothing else, to api.osv.dev (vulnerabilities),
pypi.org, registry.npmjs.org and api.nuget.org (latest version, release dates, licence). Every
request has a timeout; a failed request is reported, not fatal. Version comparison is
approximate (no packaging library): check the edge cases by hand. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

USER_AGENT = "claude-role-skills-dependency-audit/0.1"
OSV = "https://api.osv.dev/v1"
ECOSYSTEM = {"python": "PyPI", "npm": "npm", "nuget": "NuGet"}
IMPORT_NAMES = {
    "pyyaml": "yaml",
    "python-dateutil": "dateutil",
    "beautifulsoup4": "bs4",
    "pillow": "PIL",
    "scikit-learn": "sklearn",
    "opencv-python": "cv2",
    "opencv-python-headless": "cv2",
    "python-dotenv": "dotenv",
    "pyjwt": "jwt",
    "protobuf": "google.protobuf",
    "psycopg2-binary": "psycopg2",
    "attrs": "attr",
    "python-multipart": "multipart",
    "typing-extensions": "typing_extensions",
    "faiss-cpu": "faiss",
    "msgpack-python": "msgpack",
    "pymupdf": "fitz",
    "python-docx": "docx",
    "python-pptx": "pptx",
    "google-cloud-storage": "google.cloud.storage",
    "azure-storage-blob": "azure.storage.blob",
    "azure-identity": "azure.identity",
    "pycryptodome": "Crypto",
    "dnspython": "dns",
    "pyzmq": "zmq",
}
REQ = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*([^;#]*?)\s*(;[^#]*)?(#.*)?$")
PRE = re.compile(r"[-.]?(a|b|c|rc|alpha|beta|pre|preview|dev)[.-]?(\d*)", re.I)


# ---------------------------------------------------------------------------- versions


def norm(ecosystem: str, name: str) -> str:
    if ecosystem == "python":
        return re.sub(r"[-_.]+", "-", name).lower()
    return name.lower() if ecosystem == "nuget" else name


def vkey(version: str) -> tuple[tuple[int, ...], tuple[int, str, int]]:
    """Approximate sort key: numeric release parts, then pre-releases before the final release."""
    v = version.strip().lstrip("vV=[(").split("+")[0].rstrip("])")
    match = PRE.search(v)
    base = v[: match.start()] if match else v
    nums = [int(x) for x in re.findall(r"\d+", base)][:6]
    nums += [0] * (6 - len(nums))
    pre = (0, match.group(1).lower(), int(match.group(2) or 0)) if match else (1, "", 0)
    return tuple(nums), pre


def is_pre(version: str) -> bool:
    return PRE.search(version) is not None


def exact(ecosystem: str, spec: str | None) -> str | None:
    """The version a spec pins exactly, or None for a range."""
    if not spec:
        return None
    spec = spec.strip()
    if ecosystem == "python":
        match = re.fullmatch(r"===?\s*([\w.!+-]+)", spec)
        return match.group(1) if match and "*" not in match.group(1) else None
    if ecosystem == "npm":
        return spec.lstrip("=v") if re.fullmatch(r"=?v?\d+\.\d+\.\d+(-[\w.]+)?", spec) else None
    match = re.fullmatch(r"\[?\s*(\d[\w.-]*)\s*\]?", spec)  # NuGet "1.2.3" resolves to the lowest match
    return match.group(1) if match else None


def lowest_allowed(ecosystem: str, spec: str | None) -> str | None:
    """The lowest version a range allows, when the range states one (>=, ~=, ^, ~, ==X.*)."""
    if not spec:
        return None
    if ecosystem == "python":
        match = re.search(r"(?:>=|~=)\s*([\w.]+)|==\s*([\d.]+)\.\*", spec)
        return (match.group(1) or match.group(2)) if match else None
    if ecosystem == "npm":
        match = re.match(r"\s*(?:>=|\^|~)?\s*v?(\d+\.\d+\.\d+)", spec)
        return match.group(1) if match else None
    match = re.match(r"\s*[\[(]?\s*(\d[\w.-]*)", spec)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------- manifests


def files_of(repo: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout
        listed = [f for f in out.split("\0") if f and (repo / f).is_file()]
        if listed:
            return sorted(listed)
    except (OSError, subprocess.SubprocessError):
        pass
    skip = {".git", "node_modules", ".venv", "venv", "__pycache__", "bin", "obj", "dist", "build"}
    return sorted(
        p.relative_to(repo).as_posix()
        for p in repo.rglob("*")
        if p.is_file() and not skip & set(p.relative_to(repo).parts)
    )


def parse_req(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith(("#", "-", "git+", "http:", "https:", "file:", ".")):
        return None
    match = REQ.match(line)
    if not match:
        return None
    return match.group(1), match.group(3).strip()


def python_manifest(repo: Path, rel: str, add: Any, notes: list[dict[str, str]]) -> None:
    name = PurePosixPath(rel).name
    text = (repo / rel).read_text(encoding="utf-8", errors="replace")
    if name == "pyproject.toml":
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            notes.append({"kind": "unreadable manifest", "detail": f"{rel}: {exc}"})
            return
        project = data.get("project", {})
        for req in project.get("dependencies", []):
            if parsed := parse_req(req):
                add("python", parsed[0], parsed[1], rel, "main")
        for extra, reqs in project.get("optional-dependencies", {}).items():
            for req in reqs:
                if parsed := parse_req(req):
                    add("python", parsed[0], parsed[1], rel, f"extra:{extra}")
        for group, reqs in data.get("dependency-groups", {}).items():
            for req in reqs:
                if isinstance(req, str) and (parsed := parse_req(req)):
                    add("python", parsed[0], parsed[1], rel, f"group:{group}")
        for req in data.get("tool", {}).get("uv", {}).get("dev-dependencies", []):
            if parsed := parse_req(req):
                add("python", parsed[0], parsed[1], rel, "dev")
        poetry = data.get("tool", {}).get("poetry", {})
        tables = [("main", poetry.get("dependencies", {})), ("dev", poetry.get("dev-dependencies", {}))]
        tables += [(f"group:{g}", t.get("dependencies", {})) for g, t in poetry.get("group", {}).items()]
        for scope, table in tables:
            for dep, spec in table.items():
                if dep.lower() != "python":
                    version = spec.get("version", "") if isinstance(spec, dict) else str(spec)
                    add("python", dep, version, rel, scope)
    else:
        for line in text.splitlines():
            if line.strip().startswith(("-r", "-c", "--requirement", "--constraint")):
                notes.append({"kind": "include not followed", "detail": f"{rel}: {line.strip()}"})
            elif parsed := parse_req(line):
                add("python", parsed[0], parsed[1], rel, "requirements")


def npm_manifest(repo: Path, rel: str, add: Any, notes: list[dict[str, str]]) -> None:
    try:
        data = json.loads((repo / rel).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        notes.append({"kind": "unreadable manifest", "detail": f"{rel}: {exc}"})
        return
    for key, scope in (
        ("dependencies", "main"),
        ("devDependencies", "dev"),
        ("optionalDependencies", "optional"),
        ("peerDependencies", "peer"),
    ):
        for dep, spec in (data.get(key) or {}).items():
            add("npm", dep, str(spec), rel, scope)


def nuget_manifest(repo: Path, rel: str, add: Any, notes: list[dict[str, str]], central: dict[str, str]) -> None:
    try:
        root = ET.fromstring((repo / rel).read_text(encoding="utf-8-sig"))
    except ET.ParseError as exc:
        notes.append({"kind": "unreadable manifest", "detail": f"{rel}: {exc}"})
        return
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        if tag not in ("PackageReference", "PackageVersion"):
            continue
        dep = element.get("Include") or element.get("Update")
        if not dep:
            continue
        version = element.get("Version") or next(
            (c.text or "" for c in element if c.tag.split("}")[-1] == "Version"), ""
        )
        if tag == "PackageVersion":
            central[dep.lower()] = version
        else:
            add("nuget", dep, version or central.get(dep.lower(), ""), rel, "main")


def lock_entries(repo: Path, rel: str) -> list[tuple[str, str, str]]:
    """(ecosystem, name, version) from one lock file."""
    name = PurePosixPath(rel).name
    text = (repo / rel).read_text(encoding="utf-8", errors="replace")
    entries: list[tuple[str, str, str]] = []
    try:
        if name in ("uv.lock", "poetry.lock"):
            for package in tomllib.loads(text).get("package", []):
                source = package.get("source", {})
                if isinstance(source, dict) and ({"editable", "virtual"} & set(source)):
                    continue
                entries.append(("python", package["name"], str(package.get("version", ""))))
        elif name == "Pipfile.lock":
            data = json.loads(text)
            for section in ("default", "develop"):
                for dep, info in data.get(section, {}).items():
                    entries.append(("python", dep, str(info.get("version", "")).lstrip("=")))
        elif name == "package-lock.json":
            data = json.loads(text)
            for path, info in (data.get("packages") or {}).items():
                if path and "node_modules/" in path and info.get("version"):
                    entries.append(("npm", path.rsplit("node_modules/", 1)[1], info["version"]))
            if not data.get("packages"):
                stack = [data.get("dependencies") or {}]
                while stack:
                    for dep, info in stack.pop().items():
                        entries.append(("npm", dep, info.get("version", "")))
                        stack.append(info.get("dependencies") or {})
        elif name == "packages.lock.json":
            for framework in json.loads(text).get("dependencies", {}).values():
                for dep, info in framework.items():
                    entries.append(("nuget", dep, info.get("resolved", "")))
    except (tomllib.TOMLDecodeError, json.JSONDecodeError, KeyError, AttributeError):
        return []
    return entries


def imports_of(repo: Path, files: list[str]) -> dict[str, dict[str, list[str]]]:
    """Top-level imported names per language, with the files that import them."""
    found: dict[str, dict[str, list[str]]] = {"python": defaultdict(list), "npm": defaultdict(list)}
    py = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w., ]+))", re.M)
    js = re.compile(r"""(?:from\s*|require\(\s*|import\(\s*|import\s+)['"]([^'"./][^'"]*)['"]""")
    for rel in files:
        suffix = PurePosixPath(rel).suffix
        if suffix not in (".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".svelte", ".vue"):
            continue
        try:
            text = (repo / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if suffix == ".py":
            for match in py.finditer(text):
                modules = (
                    [match.group(1)] if match.group(1) else [m.strip().split(" ")[0] for m in match.group(2).split(",")]
                )
                for module in modules:
                    for depth in (1, 2, 3):
                        key = ".".join(module.split(".")[:depth])
                        if rel not in found["python"][key]:
                            found["python"][key].append(rel)
        else:
            for spec in js.findall(text):
                key = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
                if rel not in found["npm"][key]:
                    found["npm"][key].append(rel)
    return found


def inventory(repo: Path) -> dict[str, Any]:
    files = files_of(repo)
    deps: dict[tuple[str, str], dict[str, Any]] = {}
    notes: list[dict[str, str]] = []
    manifests: list[dict[str, str]] = []
    locks: dict[str, list[str]] = defaultdict(list)
    locked: dict[tuple[str, str], set[str]] = defaultdict(set)
    central: dict[str, str] = {}

    def add(ecosystem: str, name: str, spec: str, manifest: str, scope: str) -> None:
        key = (ecosystem, norm(ecosystem, name))
        entry = deps.setdefault(
            key,
            {
                "ecosystem": ecosystem,
                "name": name,
                "direct": True,
                "scopes": [],
                "declared": {},
                "locked": None,
            },
        )
        if scope not in entry["scopes"]:
            entry["scopes"].append(scope)
        entry["declared"][manifest] = spec

    ordered = sorted(files, key=lambda f: (PurePosixPath(f).name != "Directory.Packages.props", f))
    for rel in ordered:
        name = PurePosixPath(rel).name
        if name == "pyproject.toml" or re.fullmatch(r"requirements[\w.-]*\.(txt|in)", name):
            manifests.append({"path": rel, "ecosystem": "python"})
            python_manifest(repo, rel, add, notes)
        elif name == "package.json" and "node_modules/" not in rel:
            manifests.append({"path": rel, "ecosystem": "npm"})
            npm_manifest(repo, rel, add, notes)
        elif name.endswith((".csproj", ".fsproj", ".vbproj")) or name == "Directory.Packages.props":
            manifests.append({"path": rel, "ecosystem": "nuget"})
            nuget_manifest(repo, rel, add, notes, central)
        elif name in ("uv.lock", "poetry.lock", "Pipfile.lock", "package-lock.json", "packages.lock.json"):
            for ecosystem, dep, version in lock_entries(repo, rel):
                if rel not in locks[ecosystem]:
                    locks[ecosystem].append(rel)
                locked[(ecosystem, norm(ecosystem, dep))].add(version)
                if (ecosystem, norm(ecosystem, dep)) not in deps:
                    deps[(ecosystem, norm(ecosystem, dep))] = {
                        "ecosystem": ecosystem,
                        "name": dep,
                        "direct": False,
                        "scopes": [],
                        "declared": {},
                        "locked": None,
                    }
        elif name in ("yarn.lock", "pnpm-lock.yaml"):
            notes.append({"kind": "lock file not parsed", "detail": f"{rel}: only package-lock.json is read for npm"})

    imported = imports_of(repo, files)
    for key, entry in deps.items():
        ecosystem = entry["ecosystem"]
        versions = sorted(locked.get(key, set()), key=vkey)
        entry["locked"] = versions[-1] if versions else None
        if len(versions) > 1:
            entry["locked_all"] = versions
        specs = set(entry["declared"].values())
        pins = {exact(ecosystem, s) for s in specs}
        entry["pinned"] = bool(specs) and None not in pins
        entry["version"] = entry["locked"] or (next(iter(pins)) if len(pins) == 1 and None not in pins else None)
        if entry["version"]:
            entry["lookup"] = {"version": entry["version"], "basis": "locked" if entry["locked"] else "pinned"}
        else:
            lows = [v for v in (lowest_allowed(ecosystem, s) for s in specs) if v]
            entry["lookup"] = (
                {"version": max(lows, key=vkey), "basis": "lowest version the range allows"} if lows else None
            )
        if entry["direct"] and ecosystem in imported:
            module = IMPORT_NAMES.get(norm(ecosystem, entry["name"]), entry["name"].replace("-", "_").lower())
            if ecosystem == "npm":
                module = entry["name"]
            entry["imported_in"] = imported[ecosystem].get(module, [])[:5]
        if entry["direct"] and len(specs) > 1:
            notes.append({"kind": "declared twice", "name": entry["name"], "detail": json.dumps(entry["declared"])})
        if entry["direct"] and specs == {""}:
            notes.append(
                {"kind": "no version constraint", "name": entry["name"], "detail": ", ".join(entry["declared"])}
            )
    for ecosystem in sorted({d["ecosystem"] for d in deps.values() if d["direct"]}):
        ranged = [d["name"] for d in deps.values() if d["ecosystem"] == ecosystem and d["direct"] and not d["pinned"]]
        if ranged and not locks.get(ecosystem):
            notes.append(
                {
                    "kind": "no lock file",
                    "ecosystem": ecosystem,
                    "detail": f"{len(ranged)} direct dependencies are ranges and nothing locks them: "
                    + ", ".join(ranged),
                }
            )
    ordered_deps = sorted(deps.values(), key=lambda d: (not d["direct"], d["ecosystem"], d["name"].lower()))
    return {
        "repo": repo.name,
        "manifests": manifests,
        "lock_files": {k: v for k, v in locks.items()},
        "counts": {
            "direct": sum(1 for d in deps.values() if d["direct"]),
            "transitive": sum(1 for d in deps.values() if not d["direct"]),
        },
        "dependencies": ordered_deps,
        "offline_findings": notes,
        "online": {"done": False},
    }


# ---------------------------------------------------------------------------- online


def http_json(url: str, timeout: float, body: Any = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fixed_for(vuln: dict[str, Any], ecosystem: str, name: str) -> list[str]:
    fixed: set[str] = set()
    for affected in vuln.get("affected", []):
        package = affected.get("package", {})
        if package.get("ecosystem") != ECOSYSTEM[ecosystem] or norm(ecosystem, package.get("name", "")) != norm(
            ecosystem, name
        ):
            continue
        for rng in affected.get("ranges", []):
            for event in rng.get("events", []):
                if "fixed" in event:
                    fixed.add(event["fixed"])
    return sorted(fixed, key=vkey)


def severity_of(vuln: dict[str, Any]) -> str:
    label = (vuln.get("database_specific") or {}).get("severity")
    if isinstance(label, str):
        return {"MODERATE": "medium"}.get(label.upper(), label.lower())
    vectors = [s.get("score", "") for s in vuln.get("severity", []) if isinstance(s, dict)]
    return vectors[0] if vectors else "unknown"


def registry(entry: dict[str, Any], timeout: float) -> dict[str, Any]:
    ecosystem, name, version = entry["ecosystem"], entry["name"], entry.get("version")
    info: dict[str, Any] = {}
    if ecosystem == "python":
        data = http_json(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json", timeout)
        latest = data["info"]["version"]
        releases = data.get("releases", {})

        def released(v: str | None) -> str | None:
            uploads = releases.get(v or "", [])
            return min((u["upload_time_iso_8601"] for u in uploads), default=None) if uploads else None

        classifiers = [c.split(" :: ")[-1] for c in data["info"].get("classifiers", []) if c.startswith("License ::")]
        licence = data["info"].get("license_expression") or (data["info"].get("license") or "").strip()
        info = {
            "latest": latest,
            "latest_date": (released(latest) or "")[:10] or None,
            "version_date": (released(version) or "")[:10] or None,
            "license": (licence if licence and len(licence) < 80 else None) or ", ".join(classifiers) or None,
        }
    elif ecosystem == "npm":
        data = http_json(f"https://registry.npmjs.org/{name.replace('/', '%2F')}", timeout)
        latest = data.get("dist-tags", {}).get("latest")
        times = data.get("time", {})
        licence = data.get("license")
        info = {
            "latest": latest,
            "latest_date": (times.get(latest) or "")[:10] or None,
            "version_date": (times.get(version or "") or "")[:10] or None,
            "license": licence if isinstance(licence, str) else (licence or {}).get("type"),
            "deprecated": (data.get("versions", {}).get(version or "", {}) or {}).get("deprecated"),
        }
    elif ecosystem == "nuget":
        data = http_json(f"https://api.nuget.org/v3-flatcontainer/{name.lower()}/index.json", timeout)
        stable = [v for v in data.get("versions", []) if not is_pre(v)]
        info = {"latest": stable[-1] if stable else None, "latest_date": None, "version_date": None, "license": None}
    return info


def go_online(result: dict[str, Any], timeout: float) -> None:
    deps = [d for d in result["dependencies"] if d.get("lookup")]
    errors: list[str] = []
    queries = [
        {"package": {"name": d["name"], "ecosystem": ECOSYSTEM[d["ecosystem"]]}, "version": d["lookup"]["version"]}
        for d in deps
    ]
    ids_per_dep: list[list[str]] = []
    for start in range(0, len(queries), 500):
        try:
            batch = http_json(f"{OSV}/querybatch", timeout, {"queries": queries[start : start + 500]})
            ids_per_dep += [[v["id"] for v in (r.get("vulns") or [])] for r in batch.get("results", [])]
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            errors.append(f"osv querybatch: {exc}")
            ids_per_dep += [[] for _ in queries[start : start + 500]]
    unique = sorted({i for ids in ids_per_dep for i in ids})

    def fetch_vuln(vid: str) -> tuple[str, dict[str, Any] | None]:
        try:
            return vid, http_json(f"{OSV}/vulns/{urllib.parse.quote(vid)}", timeout)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            errors.append(f"osv {vid}: {exc}")
            return vid, None

    def fetch_registry(entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            return entry, registry(entry, timeout)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
            errors.append(f"registry {entry['ecosystem']} {entry['name']}: {exc}")
            return entry, {}

    with ThreadPoolExecutor(max_workers=8) as pool:
        vulns = dict(pool.map(fetch_vuln, unique))
        direct = [d for d in result["dependencies"] if d["direct"]]
        for entry, info in pool.map(fetch_registry, direct):
            entry.update(info)
    today = datetime.now(UTC).date()
    for entry, ids in zip(deps, ids_per_dep, strict=True):
        merged: dict[str, dict[str, Any]] = {}
        for vid in ids:
            vuln = vulns.get(vid)
            if vuln is None:
                merged.setdefault(vid, {"ids": [vid], "summary": "details not fetched"})
                continue
            cves = sorted(a for a in [*vuln.get("aliases", []), vid] if a.startswith("CVE-"))
            key = cves[0] if cves else vid
            fixes = fixed_for(vuln, entry["ecosystem"], entry["name"])
            newer = [f for f in fixes if vkey(f) > vkey(entry["lookup"]["version"])]
            item = {
                "ids": [vid],
                "cve": cves[0] if cves else None,
                "summary": (vuln.get("summary") or (vuln.get("details") or "")[:160]).strip(),
                "severity": severity_of(vuln),
                "published": (vuln.get("published") or "")[:10],
                "fixed_in": newer[0] if newer else (fixes[-1] if fixes else None),
            }
            if key not in merged:
                merged[key] = item
                continue
            kept = merged[key]
            kept["ids"].append(vid)
            labelled = kept.get("severity") in ("low", "medium", "high", "critical")
            if not labelled and item["severity"] in ("low", "medium", "high", "critical"):
                kept["severity"] = item["severity"]
            if vid.startswith("GHSA-"):
                kept["summary"] = item["summary"]
        entry["vulns"] = sorted(merged.values(), key=lambda v: vkey(v.get("fixed_in") or "0"))
        entry["vulns_checked_for"] = entry["lookup"]
    for entry in result["dependencies"]:
        if entry.get("latest") and entry.get("version"):
            behind = vkey(entry["latest"])[0], vkey(entry["version"])[0]
            entry["major_behind"] = behind[0][0] - behind[1][0]
        if entry.get("latest_date"):
            age = (today - datetime.fromisoformat(entry["latest_date"]).date()).days
            entry["latest_release_age_days"] = age
            entry["maybe_abandoned"] = age > 730
    result["online"] = {
        "done": True,
        "hosts": ["api.osv.dev", "pypi.org", "registry.npmjs.org", "api.nuget.org"],
        "checked_on": today.isoformat(),
        "packages_with_versions": len(deps),
        "vulnerabilities": len(unique),
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dependency inventory, optionally with vulnerabilities and latest versions."
    )
    parser.add_argument("repo", nargs="?", default=".", type=Path)
    parser.add_argument("--online", action="store_true", help="query OSV and the package registries")
    parser.add_argument("--timeout", type=float, default=10.0, help="seconds per request")
    args = parser.parse_args(argv)
    result = inventory(args.repo.resolve())
    if args.online:
        go_online(result, args.timeout)
    json.dump(result, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
