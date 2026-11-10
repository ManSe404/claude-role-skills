"""The change-review facts script, on the acme-orders fixture and on small repositories of its own."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from conftest import SKILLS, git, load, make_repo, run_json

DIFF = SKILLS / "change-review" / "scripts" / "diff_facts.py"
diff_facts = load(DIFF)


@pytest.fixture(scope="module")
def since_deploy(acme: Path) -> dict[str, Any]:
    """The three commits after the last deploy (d22ee8f): the amount parsing change, the adjustments file, a doc."""
    result: dict[str, Any] = run_json(DIFF, str(acme), "--range", "d22ee8f..HEAD")
    return result


def test_commits_files_and_size(since_deploy: dict[str, Any]) -> None:
    assert [c["message"] for c in since_deploy["commits"]] == [
        "docs: how finance reads the totals",
        "report: add the manual adjustments file",
        "importer: simplify amount parsing",
    ]
    kinds = {f["path"]: (f["kind"], f["status"]) for f in since_deploy["files"]}
    assert kinds == {
        "docs/finance-export.md": ("docs", "added"),
        "src/acme_orders/cli.py": ("source", "modified"),
        "src/acme_orders/importer.py": ("source", "modified"),
        "src/acme_orders/report.py": ("source", "modified"),
        "tests/test_importer.py": ("test", "modified"),
    }
    assert since_deploy["size"] == {"files": 5, "hunks": 8, "added": 23, "removed": 7}


def test_hunks_carry_line_numbers_and_symbols(since_deploy: dict[str, Any]) -> None:
    importer = next(f for f in since_deploy["files"] if f["path"].endswith("importer.py"))
    (hunk,) = importer["hunks"]
    assert hunk["added_lines"] == [28] and hunk["removed_lines"] == [28]
    assert hunk["symbols"] == ["parse_amount"]
    report = next(f for f in since_deploy["files"] if f["path"].endswith("report.py"))
    assert {s for h in report["hunks"] for s in h["symbols"]} == {"daily_report", "read_adjustments"}


def test_removed_test_and_untested_source_are_listed(since_deploy: dict[str, Any]) -> None:
    removed = since_deploy["tests"]["tests_removed"]
    assert [r["name"] for r in removed] == ["ParseAmountTest.test_decimal_comma"]
    assert removed[0]["file"] == "tests/test_importer.py"
    assert since_deploy["tests"]["touched"] == ["tests/test_importer.py"]
    # importer.py has a touched test of its own name; cli.py and report.py do not
    assert since_deploy["tests"]["source_without_test_change"] == [
        "src/acme_orders/cli.py",
        "src/acme_orders/report.py",
    ]
    added = {s["name"] for s in since_deploy["symbols"]["added"]}
    changed = {s["name"] for s in since_deploy["symbols"]["changed"]}
    assert "read_adjustments" in added and "parse_amount" in changed


def test_rule_hits_are_on_added_lines_only(since_deploy: dict[str, Any]) -> None:
    hits = {(h["rule"], h["file"], h["line"]) for h in since_deploy["hits"]}
    assert ("path-from-input", "src/acme_orders/report.py", 21) in hits
    assert not [h for h in since_deploy["hits"] if h["rule"] == "orphan-key"]
    report = next(f for f in since_deploy["files"] if f["path"].endswith("report.py"))
    added = {line for h in report["hunks"] for line in h["added_lines"]}
    assert all(h["line"] in added for h in since_deploy["hits"] if h["file"].endswith("report.py"))


def test_claims_come_from_commit_messages_and_the_description(acme: Path, tmp_path: Path) -> None:
    description = tmp_path / "pr.md"
    description.write_text(
        "Simplifies amount parsing. The importer never fails on a comma since this change.\n- also adds adjustments\n"
    )
    out = run_json(DIFF, str(acme), "--range", "d22ee8f..HEAD", "--description", str(description))
    texts = [c["text"] for c in out["claims"]]
    assert "Simplifies amount parsing." in texts
    comma = next(c for c in out["claims"] if "never fails" in c["text"])
    assert comma["kind"] == "error-handling" and comma["where"] == "pr.md:1"
    assert any(c["where"].startswith("commit ") for c in out["claims"])


def test_patch_mode_reads_a_unified_diff(acme: Path, tmp_path: Path) -> None:
    patch = tmp_path / "change.patch"
    patch.write_text(git(acme, "diff", "49bc16d^..49bc16d"))
    out = run_json(DIFF, str(acme), "--patch", str(patch))
    assert out["patch"] == "change.patch" and out["commits"] == []
    assert {f["path"] for f in out["files"]} == {"src/acme_orders/importer.py", "tests/test_importer.py"}
    assert out["size"]["removed"] == 4 and out["size"]["added"] == 1
    # no before and after text in patch mode, so no symbols and no hits, but the hunks are there
    assert out["symbols"] == {"changed": [], "added": [], "removed": []} and out["hits"] == []
    assert sum(len(f["hunks"]) for f in out["files"]) == 2


def test_open_range_compares_with_the_working_tree(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path / "wt",
        {"app.py": "def run():\n    return 1\n", "tests/test_app.py": "def test_run():\n    assert True\n"},
    )
    (repo / "app.py").write_text("import os\n\n\ndef run(cmd):\n    os.system(cmd)\n    return 1\n")
    out = run_json(DIFF, str(repo), "--range", "HEAD..")
    assert out["head"] == "working tree" and [f["path"] for f in out["files"]] == ["app.py"]
    assert [(h["rule"], h["line"]) for h in out["hits"]] == [("shell-input", 5)]
    assert out["tests"]["source_without_test_change"] == ["app.py"]


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("migrations/0007_add_index.py", "migration"),
        ("pyproject.toml", "dependency"),
        ("package-lock.json", "dependency"),
        (".github/workflows/ci.yml", "ci"),
        ("tests/test_x.py", "test"),
        ("src/x.spec.ts", "test"),
        (".env", "secrets"),
        ("deploy/id_rsa", "secrets"),
        ("docker-compose.yml", "config"),
        ("README.md", "docs"),
        ("src/app.py", "source"),
        ("assets/logo.png", "other"),
    ],
)
def test_kind_of(path: str, kind: str) -> None:
    assert diff_facts.kind_of(path) == kind


def test_secret_files_are_named_not_shown(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "s", {"app.py": "x = 1\n"})
    (repo / ".env").write_text("API_KEY=sk-live-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456\n")
    subprocess.run(["git", "add", "-f", ".env"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-q", "-m", "oops"],
        cwd=repo,
        check=True,
    )
    out = run_json(DIFF, str(repo), "--range", "HEAD~1..HEAD")
    text = json.dumps(out)
    assert "sk-live" not in text
    (env,) = out["files"]
    assert env["kind"] == "secrets" and env["hunks"] == [] and "secret" in env["note"]


def test_a_bad_range_fails_loudly(acme: Path) -> None:
    done = subprocess.run(
        ["python3", str(DIFF), str(acme), "--range", "nope..HEAD"], capture_output=True, text=True, check=False
    )
    assert done.returncode == 1 and "git" in done.stderr
