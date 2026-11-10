"""The acme-index fixture: the made-up search library the code-audit skill is tested and shown on.

PLANTED lists the seven bugs an audit of it must find: (id, short name, file, regex for the flawed line). PROMISES
lists the sentence in the docs that each bug breaks: (id, doc file, regex for the sentence). DECOYS lists four
places that look risky and are fine: (id, short name, file, regex for the line). PLANTED_AT, PROMISES_AT and
DECOYS_AT say where each one sits at HEAD, as file:line; they are computed from files/, which is the state after
the last commit, and the tests below check them against the built fixture. The evals and the script tests import
these, so keep them in step with the fixture.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import build_fixture
import pytest
from conftest import ROOT, git

STORE = "src/acme_index/store.py"
PLANS = "src/acme_index/plans.py"
CHUNKS = "src/acme_index/chunks.py"
PARSE = "src/acme_index/parse.py"
EMBEDDER = "src/acme_index/embedder.py"
ANSWERS = "src/acme_index/answers.py"
WORKER = "src/acme_index/worker.py"
CONTRACTS = "docs/contracts.md"
ADR_CHUNKS = "docs/adr/0001-chunks-in-sqlite.md"
ADR_RUNS = "docs/adr/0002-plans-and-runs.md"

PLANTED: list[tuple[str, str, str, str]] = [
    (
        "P1",
        "re-index deletes the chunks before the embedder call",
        STORE,
        r'^\s+self\._conn\.execute\("DELETE FROM chunks WHERE doc_id = \?", \(doc_id,\)\)$',
    ),
    ("P2", "finished run reads a digest key nobody writes", PLANS, r'^\s+new_digest = run\.get\("_digest"\)$'),
    ("P3", "chunk id from the salted built-in hash", CHUNKS, r"\bhash\(text\)"),
    ("P4", "parse errors swallowed into an empty document", PARSE, r"^\s+except Exception:$"),
    ("P5", "embedder call without a timeout", EMBEDDER, r"^\s+with urllib\.request\.urlopen\(request\) as response:$"),
    ("P6", "answer stream can stop without a final event", ANSWERS, r"^\s+except urllib\.error\.URLError as exc:$"),
    ("P7", "job retry loop counts only embedder errors", WORKER, r"^\s+while True:$"),
]

PROMISES: list[tuple[str, str, str]] = [
    ("P1", CONTRACTS, r"Re-indexing a document never removes it from search before its new version is stored\."),
    ("P2", ADR_RUNS, r"Every run stores the digest of the plan it actually executed\."),
    ("P3", ADR_CHUNKS, r"Chunk ids are deterministic; re-indexing overwrites, never duplicates\."),
    ("P4", "README.md", r"Parse errors are reported, never hidden"),
    ("P5", "CLAUDE.md", r"Every outbound call has an explicit timeout\."),
    ("P6", CONTRACTS, r"Every answer stream ends with exactly one `end` or `error` event\."),
    ("P7", "README.md", r"A job is retried at most 3 times, then moved to the dead-letter table\."),
]

DECOYS: list[tuple[str, str, str, str]] = [
    ("D1", "broad except that re-raises as IndexingError", PLANS, r"^\s+except Exception as exc:$"),
    ("D2", "optional tenant with a documented default", WORKER, r'^\s+tenant=raw\.get\("tenant", DEFAULT_TENANT\),$'),
    ("D3", "bounded retry loop around the embedder call", EMBEDDER, r"^\s+while True:$"),
    (
        "D4",
        "metadata delete and insert in one transaction",
        STORE,
        r'^\s+self\._conn\.execute\("DELETE FROM doc_meta WHERE doc_id = \?", \(doc_id,\)\)$',
    ),
]

HEAD = "acd5c88"
COMMITS = 10
FILES = ROOT / "fixtures" / "acme-index" / "files"

LAYOUT = [
    ".gitignore",
    "CLAUDE.md",
    "README.md",
    ADR_CHUNKS,
    ADR_RUNS,
    CONTRACTS,
    "pyproject.toml",
    "src/acme_index/__init__.py",
    ANSWERS,
    CHUNKS,
    EMBEDDER,
    PARSE,
    PLANS,
    STORE,
    WORKER,
    "tests/test_clients.py",
    "tests/test_index.py",
]


def stored(rel: str) -> str:
    """The text of rel in files/, where a manifest may carry the .fixture suffix."""
    path = FILES / rel
    if not path.exists():
        path = FILES / f"{rel}.fixture"
    return path.read_text(encoding="utf-8")


def lines_matching(text: str, pattern: str) -> list[int]:
    return [number for number, line in enumerate(text.splitlines(), start=1) if re.search(pattern, line)]


def where(rel: str, pattern: str) -> str:
    """file:line of the one line in files/ that pattern matches; file:? when it matches none or several."""
    found = lines_matching(stored(rel), pattern)
    return f"{rel}:{found[0]}" if len(found) == 1 else f"{rel}:?"


PLANTED_AT: dict[str, str] = {pid: where(rel, pattern) for pid, _, rel, pattern in PLANTED}
PROMISES_AT: dict[str, str] = {pid: where(rel, pattern) for pid, rel, pattern in PROMISES}
DECOYS_AT: dict[str, str] = {did: where(rel, pattern) for did, _, rel, pattern in DECOYS}

ADDRESS = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")


@pytest.fixture(scope="module")
def index_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-index fixture, built once for this module. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-index"
    build_fixture.build("acme-index", target)
    return target


def read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text(encoding="utf-8")


def tracked(repo: Path) -> list[str]:
    return git(repo, "ls-files").splitlines()


def line_in(repo: Path, rel: str, pattern: str) -> int:
    """The 1-based line in repo/rel that pattern matches; it must match exactly one line."""
    found = lines_matching(read(repo, rel), pattern)
    assert len(found) == 1, f"{pattern!r} matches lines {found} of {rel}, expected exactly one"
    return found[0]


def python_env(**extra: str) -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": "src", "PYTHONDONTWRITEBYTECODE": "1", **extra}


def test_builds_deterministically_with_the_same_head(tmp_path: Path) -> None:
    heads = {build_fixture.build("acme-index", tmp_path / name) for name in ("one", "two")}
    assert heads == {HEAD}


def test_history_has_every_commit_three_authors_and_fictional_dates(index_repo: Path) -> None:
    log = git(index_repo, "log", "--format=%h %s").splitlines()
    assert len(log) == COMMITS
    assert log[0] == f"{HEAD} Chunk ids without hashlib, about 3x faster on long documents"
    assert log[-1].endswith(" Start acme-index: parse, chunk and store documents in SQLite")
    emails = set(git(index_repo, "log", "--format=%ae").split())
    assert len(emails) == 3
    assert all(email.endswith("@example.com") for email in emails)
    days = git(index_repo, "log", "--format=%ad", "--date=short").split()
    assert all("2026-06-01" <= day <= "2026-10-31" for day in days)
    assert days == sorted(days, reverse=True)


def test_layout_is_exact_and_the_last_commit_equals_the_stored_files(index_repo: Path) -> None:
    assert sorted(tracked(index_repo)) == sorted(LAYOUT)
    assert git(index_repo, "status", "--porcelain") == ""
    for path in FILES.rglob("*"):
        if path.is_file():
            rel = path.relative_to(FILES).as_posix().removesuffix(".fixture")
            assert git(index_repo, "show", f"HEAD:{rel}") == path.read_text(encoding="utf-8"), rel


def test_size_is_that_of_a_small_library(index_repo: Path) -> None:
    total = sum(len(read(index_repo, rel).splitlines()) for rel in tracked(index_repo))
    assert 500 <= total <= 900


@pytest.mark.parametrize(("pid", "name", "rel", "pattern"), PLANTED, ids=[p[0] for p in PLANTED])
def test_planted_bug_sits_on_its_line(
    index_repo: Path, record_property: Callable[[str, object], None], pid: str, name: str, rel: str, pattern: str
) -> None:
    line = line_in(index_repo, rel, pattern)
    record_property("planted", f"{pid} {name}: {rel}:{line}")
    assert f"{rel}:{line}" == PLANTED_AT[pid]


@pytest.mark.parametrize(("pid", "rel", "pattern"), PROMISES, ids=[p[0] for p in PROMISES])
def test_the_promise_each_bug_breaks_is_stated_once(index_repo: Path, pid: str, rel: str, pattern: str) -> None:
    assert f"{rel}:{line_in(index_repo, rel, pattern)}" == PROMISES_AT[pid]
    assert len(re.findall(pattern, read(index_repo, rel))) == 1


@pytest.mark.parametrize(("did", "name", "rel", "pattern"), DECOYS, ids=[d[0] for d in DECOYS])
def test_decoy_sits_on_its_line(index_repo: Path, did: str, name: str, rel: str, pattern: str) -> None:
    assert f"{rel}:{line_in(index_repo, rel, pattern)}" == DECOYS_AT[did]


def test_ids_match_across_the_lists() -> None:
    assert [p[0] for p in PLANTED] == [p[0] for p in PROMISES] == [f"P{n}" for n in range(1, 8)]
    assert [d[0] for d in DECOYS] == ["D1", "D2", "D3", "D4"]
    assert "?" not in " ".join([*PLANTED_AT.values(), *PROMISES_AT.values(), *DECOYS_AT.values()])


def test_each_promise_is_in_place_when_its_bug_arrives(index_repo: Path) -> None:
    commits = git(index_repo, "rev-list", "--reverse", "HEAD").split()

    def first(rel: str, pattern: str) -> int:
        for index, commit in enumerate(commits):
            listed = git(index_repo, "ls-tree", "--name-only", commit, rel).strip()
            if listed and re.search(pattern, git(index_repo, "show", f"{commit}:{rel}"), re.MULTILINE):
                return index
        raise AssertionError(f"{pattern!r} never appears in {rel}")

    later = 0
    for (pid, _, code, flaw), (_, doc, promise) in zip(PLANTED, PROMISES, strict=True):
        bug_at, promise_at = first(code, flaw), first(doc, promise)
        assert promise_at <= bug_at, pid
        later += promise_at < bug_at
    assert later == 4


def test_the_digest_key_was_renamed_on_one_side_only(index_repo: Path) -> None:
    before = git(index_repo, "show", f"HEAD~1:{PLANS}")
    assert 'run["_digest"] = plan.digest()' in git(index_repo, "show", f"HEAD~2:{PLANS}")
    assert 'run["_digest"]' not in before and 'run["digest"] = plan.digest()' in before
    assert 'run.get("_digest")' in before
    log = git(index_repo, "log", "--format=%s", "-1", "HEAD~1")
    assert log.strip() == "Runs: one shape for the run dict, no private keys"


def test_the_decoys_are_fine_in_the_code(index_repo: Path) -> None:
    plans = read(index_repo, PLANS)
    assert 'raise IndexingError(f"step {step.name} of the plan for {plan.source} failed") from exc' in plans
    assert "| `tenant` | no | name of the tenant's SQLite file, default `default` |" in read(index_repo, "README.md")
    embedder = read(index_repo, EMBEDDER)
    assert "attempt += 1" in embedder and "if attempt >= MAX_ATTEMPTS:" in embedder
    store = read(index_repo, STORE).splitlines()
    delete = line_in(index_repo, STORE, DECOYS[3][3])
    assert store[delete - 2].strip() == "with self._conn:"
    assert store[delete].strip().startswith("self._conn.executemany(")


def test_the_fixture_suite_passes_without_reaching_the_bugs(index_repo: Path) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=index_repo,
        env=python_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert "Ran 10 tests" in done.stderr
    assert git(index_repo, "status", "--porcelain") == ""
    tests = read(index_repo, "tests/test_index.py") + read(index_repo, "tests/test_clients.py")
    for path in ("_digest", "PYTHONHASHSEED", "JSONDecodeError", "dead_letter", "run_job", ".docx", "timeout"):
        assert path not in tests, path


def test_the_package_imports_with_the_standard_library_only(index_repo: Path) -> None:
    modules = "acme_index.answers, acme_index.plans, acme_index.worker"
    done = subprocess.run(
        [sys.executable, "-S", "-c", f"import {modules}"],
        cwd=index_repo,
        env=python_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr


def test_chunk_ids_differ_between_processes(index_repo: Path) -> None:
    code = "from acme_index.chunks import chunk_id; print(chunk_id('doc', 0, 'Novi Sad'))"

    def chunk_id_with(seed: str) -> str:
        done = subprocess.run(
            [sys.executable, "-c", code],
            cwd=index_repo,
            env=python_env(PYTHONHASHSEED=seed),
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        return done.stdout.strip()

    assert chunk_id_with("1") == chunk_id_with("1")
    assert chunk_id_with("1") != chunk_id_with("2")


def test_only_example_addresses(index_repo: Path) -> None:
    for address in git(index_repo, "log", "--format=%ae%n%ce").split():
        assert address.endswith("@example.com"), address
    for rel in tracked(index_repo):
        for domain in ADDRESS.findall(read(index_repo, rel)):
            assert domain == "example.com", (rel, domain)
