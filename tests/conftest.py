from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins" / "software-engineering" / "skills"
sys.path.insert(0, str(ROOT / "fixtures"))

import build_fixture  # noqa: E402


def script(skill: str, name: str) -> Path:
    return SKILLS / skill / "scripts" / name


def load(path: Path) -> ModuleType:
    """Import a skill script as a module, so its functions can be tested directly."""
    spec = importlib.util.spec_from_file_location(
        f"skill_{path.parent.parent.name}_{path.stem}".replace("-", "_"), path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_json(path: Path, *args: str, stdin: str | None = None) -> Any:
    """Run a skill script the way Claude does and parse its JSON output."""
    done = subprocess.run(
        [sys.executable, str(path), *args], input=stdin, capture_output=True, text=True, check=True, timeout=120
    )
    return json.loads(done.stdout)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


@pytest.fixture(scope="session")
def acme(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-orders fixture, built once per test run. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-orders"
    build_fixture.build("acme-orders", target)
    return target


def make_repo(path: Path, files: dict[str, str]) -> Path:
    """A small git repo with one commit, for tests that need their own layout."""
    path.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        dest = path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    env = ["-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", *env, "commit", "-q", "--no-verify", "-m", "init"], cwd=path, check=True)
    return path
