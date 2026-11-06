#!/usr/bin/env python3
"""Build a fixture project, with its git history, into an empty directory.

Usage: python3 fixtures/build_fixture.py acme-orders TARGET_DIR

A fixture is fixtures/<name>/files/ (the state after the last commit; a `.fixture` suffix is
dropped, so manifests with deliberately old pins are not picked up by dependency scanners in this
repo), fixtures/<name>/history.py (the commits) and optional fixtures/<name>/extras/ (files that
exist on disk but are not committed, such as logs and data exports).

The build is deterministic: the same fixture gives the same commit hashes. Global and system git
config are ignored, so signing, hooks and templates of the machine do not leak in.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SUFFIX = ".fixture"


def load_history(name: str) -> list[dict[str, Any]]:
    """Return the COMMITS list of fixtures/<name>/history.py (plain data, see that file)."""
    path = HERE / name / "history.py"
    spec = importlib.util.spec_from_file_location(f"fixture_history_{name.replace('-', '_')}", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"no history at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commits: list[dict[str, Any]] = module.COMMITS
    return commits


def final_files(name: str) -> dict[str, str]:
    root = HERE / name / "files"
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            files[rel.removesuffix(SUFFIX)] = path.read_text(encoding="utf-8")
    return files


def _undo(content: str, path: str, before: str, after: str, message: str) -> str:
    count = content.count(after)
    if count != 1:
        raise SystemExit(f"{message!r}: {path} holds the edited text {count} times, expected once:\n{after}")
    return content.replace(after, before, 1)


def snapshots(name: str) -> list[tuple[dict[str, Any], dict[str, str]]]:
    """Return (commit, files after that commit) for every commit, oldest first."""
    commits = load_history(name)
    state = final_files(name)
    result: list[tuple[dict[str, Any], dict[str, str]]] = []
    for commit in reversed(commits):
        result.append((commit, dict(state)))
        for path, before, after in reversed(commit.get("edit", [])):
            if path not in state:
                raise SystemExit(f"{commit['message']!r}: edits {path}, which does not exist at that point")
            state[path] = _undo(state[path], path, before, after, commit["message"])
        for path in commit.get("add", []):
            if path not in state:
                raise SystemExit(f"{commit['message']!r}: adds {path}, which is not in files/")
            del state[path]
    if state:
        raise SystemExit(f"files no commit adds: {', '.join(sorted(state))}")
    return list(reversed(result))


def _git(target: Path, *args: str, env: dict[str, str] | None = None) -> str:
    base = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(target),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "LC_ALL": "C",
    }
    done = subprocess.run(
        ["git", *args], cwd=target, env={**base, **(env or {})}, check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def build(name: str, target: Path) -> str:
    """Build the fixture into target and return the HEAD commit hash."""
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"{target} is not empty")
    steps = snapshots(name)
    target.mkdir(parents=True, exist_ok=True)
    _git(target, "init", "-q", "-b", "main")
    previous: dict[str, str] = {}
    for commit, files in steps:
        for path in previous.keys() - files.keys():
            (target / path).unlink()
        for path, content in files.items():
            if previous.get(path) != content:
                dest = target / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
        _git(target, "add", "-A")
        author, email = commit["author"]
        env = {
            "GIT_AUTHOR_NAME": author,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_AUTHOR_DATE": commit["date"],
            "GIT_COMMITTER_NAME": author,
            "GIT_COMMITTER_EMAIL": email,
            "GIT_COMMITTER_DATE": commit["date"],
        }
        _git(target, "commit", "-q", "--no-verify", "-m", commit["message"], env=env)
        previous = files
    extras = HERE / name / "extras"
    if extras.is_dir():
        shutil.copytree(extras, target, dirs_exist_ok=True)
    return _git(target, "rev-parse", "--short", "HEAD")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a fixture project with its git history.")
    parser.add_argument("name", help="fixture name, a folder under fixtures/")
    parser.add_argument("target", type=Path, help="an empty or missing directory")
    args = parser.parse_args(argv)
    head = build(args.name, args.target.resolve())
    print(f"{args.target} at {head}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
