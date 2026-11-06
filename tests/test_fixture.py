"""The acme-orders fixture tells a consistent story: the skills' examples and evals depend on it."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from conftest import ROOT, git

FILES = ROOT / "fixtures" / "acme-orders" / "files"


def test_history_has_every_commit_and_stable_hashes(acme: Path) -> None:
    log = git(acme, "log", "--format=%h %s").splitlines()
    assert len(log) == 13
    assert log[0] == "f36ec1c docs: how finance reads the totals"
    assert "49bc16d importer: simplify amount parsing" in log


def test_last_commit_equals_the_stored_files(acme: Path) -> None:
    for path in FILES.rglob("*"):
        if path.is_file():
            rel = path.relative_to(FILES).as_posix().removesuffix(".fixture")
            assert git(acme, "show", f"HEAD:{rel}") == path.read_text(encoding="utf-8"), rel


def test_extras_are_on_disk_but_ignored(acme: Path) -> None:
    assert (acme / "logs" / "acme-orders.log").is_file()
    assert git(acme, "status", "--porcelain") == ""


def test_the_fixture_suite_passes_despite_the_bug(acme: Path) -> None:
    env = {**os.environ, "PYTHONPATH": "src"}
    done = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=acme, env=env, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    assert "Ran 7 tests" in done.stderr


def test_the_bug_reproduces(acme: Path) -> None:
    env = {**os.environ, "PYTHONPATH": "src"}
    done = subprocess.run(
        [sys.executable, "-m", "acme_orders", "check", "data/orders-2026-10-02.csv"],
        cwd=acme,
        env=env,
        capture_output=True,
        text=True,
    )
    assert done.returncode != 0
    assert "decimal.InvalidOperation" in done.stderr


def test_the_bug_was_absent_before_its_commit(acme: Path, tmp_path: Path) -> None:
    git(acme, "worktree", "add", "-q", "--detach", str(tmp_path / "before"), "49bc16d~1")
    try:
        env = {**os.environ, "PYTHONPATH": "src"}
        done = subprocess.run(
            [sys.executable, "-m", "acme_orders", "check", str(acme / "data" / "orders-2026-10-02.csv")],
            cwd=tmp_path / "before",
            env=env,
            capture_output=True,
            text=True,
        )
        assert done.returncode == 0, done.stderr
        assert "A-1045 34.20" in done.stdout  # (12.50 + 2 x 8.00) x 1.20
    finally:
        git(acme, "worktree", "remove", "--force", str(tmp_path / "before"))


def test_log_frames_match_the_code_and_deploys_exist(acme: Path) -> None:
    log = (acme / "logs" / "acme-orders.log").read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(log):
        match = re.match(r'\s*File "/srv/acme-orders/(?P<rel>[^"]+)", line (?P<no>\d+)', line)
        if match:
            code = (acme / match["rel"]).read_text(encoding="utf-8").splitlines()
            assert code[int(match["no"]) - 1].strip() == log[i + 1].strip(), line
    for commit in set(re.findall(r"deploy(?:ed)? ([0-9a-f]{7})", "\n".join(log))):
        git(acme, "cat-file", "-e", f"{commit}^{{commit}}")
