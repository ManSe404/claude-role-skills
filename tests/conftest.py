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
AI_SKILLS = ROOT / "plugins" / "ai-architect" / "skills"
ALL_SKILLS = sorted(p.parent for p in ROOT.glob("plugins/*/skills/*/SKILL.md"))
sys.path.insert(0, str(ROOT / "fixtures"))

import build_fixture  # noqa: E402


def script(skill: str, name: str) -> Path:
    return SKILLS / skill / "scripts" / name


def ai_script(skill: str, name: str) -> Path:
    return AI_SKILLS / skill / "scripts" / name


def load(path: Path) -> ModuleType:
    """Import a skill script as a module, so its functions can be tested directly."""
    spec = importlib.util.spec_from_file_location(
        f"skill_{path.parent.parent.name}_{path.stem}".replace("-", "_"), path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass looks its module up here while it is being defined
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


@pytest.fixture(scope="session")
def assist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-assist fixture, built once per test run. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-assist"
    build_fixture.build("acme-assist", target)
    return target


@pytest.fixture(scope="session")
def data_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-data fixture, built once per test run. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-data"
    build_fixture.build("acme-data", target)
    return target


@pytest.fixture(scope="session")
def logistics_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-logistics fixture, built once per test run. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-logistics"
    build_fixture.build("acme-logistics", target)
    return target


@pytest.fixture(scope="session")
def cloud_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-cloud fixture, built once per test run. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-cloud"
    build_fixture.build("acme-cloud", target)
    return target


@pytest.fixture(scope="session")
def aws_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-cloud-aws fixture, built once per test run. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-cloud-aws"
    build_fixture.build("acme-cloud-aws", target)
    return target


@pytest.fixture(scope="session")
def solution_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-solution fixture, built once per test run. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-solution"
    build_fixture.build("acme-solution", target)
    return target


@pytest.fixture(scope="session")
def sales_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-sales fixture, built once per test run. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-sales"
    build_fixture.build("acme-sales", target)
    return target


@pytest.fixture(scope="session")
def churn_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-churn fixture, built once per test run. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-churn"
    build_fixture.build("acme-churn", target)
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
