"""The acme-assist fixture: the made-up AI prototype the ai-architect skills are tested and shown on.

PLANTED lists the eight design flaws a review of the prototype must find: (number, short name, file, regex for the
flawed line). PLANTED_AT says where each one sits in the built fixture. The ai-review eval and the script tests
import both, so keep them at the top and keep them in step with the fixture.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import build_fixture
import pytest
from conftest import ROOT, git

PLANTED: list[tuple[int, str, str, str]] = [
    (
        1,
        "live state through retrieval",
        "src/acme_assist/stock.py",
        r"knowledge\.search\(sku_or_name, collection=config\.STOCK_COLLECTION",
    ),
    (2, "unbounded agent loop", "src/acme_assist/agent.py", r"^\s+while True:$"),
    (
        3,
        "prompt injection path to a side effect",
        "src/acme_assist/tools.py",
        r"^def send_email\(to: str, subject: str, body: str\)",
    ),
    (
        4,
        "fake key literal as default",
        "src/acme_assist/config.py",
        r'os\.getenv\("OPENAI_API_KEY", "sk-example-[0-9a-f]{32}"\)',
    ),
    (5, "no evals", "README.md", r"python -m unittest discover -s tests$"),
    (
        6,
        "no timeout on model calls",
        "src/acme_assist/llm.py",
        r"OpenAI\(api_key=config\.OPENAI_API_KEY, base_url=config\.OPENAI_BASE_URL\)$",
    ),
    (7, "model alias instead of a pinned version", "src/acme_assist/config.py", r'^CHAT_MODEL = "gpt-4o"$'),
    (8, "no tracing", "src/acme_assist/agent.py", r"log\.info\("),
]

PLANTED_AT: dict[int, str] = {
    1: "src/acme_assist/stock.py:32",
    2: "src/acme_assist/agent.py:17",
    3: "src/acme_assist/tools.py:68",
    4: "src/acme_assist/config.py:5",
    5: "README.md:34",
    6: "src/acme_assist/llm.py:15",
    7: "src/acme_assist/config.py:7",
    8: "src/acme_assist/agent.py:23",
}

FILES = ROOT / "fixtures" / "acme-assist" / "files"
HEAD = "74dced7"
COMMITS = 9

PDF_PAGES = {
    "knowledge/quick-start/k200-quick-start.pdf": 2,
    "knowledge/quick-start/k300-quick-start.pdf": 2,
    "knowledge/safety/safety-sheet.pdf": 1,
}
CYRILLIC_FILES = [
    "knowledge/care/ciscenje-sr-cyrl.txt",
    "knowledge/faq-sr-cyrl.md",
    "knowledge/policies/garancija-sr-cyrl.md",
]
SERBIAN_LATIN_FILES = [
    "knowledge/faq-sr.md",
    "knowledge/manuals/k200-uputstvo-sr.md",
    "knowledge/policies/garancija-sr.md",
    "knowledge/policies/povracaj-sr.md",
]
CYRILLIC = re.compile("[Ѐ-ӿ]")
SERBIAN_LATIN = re.compile("[čćšžđČĆŠŽĐ]")
TOOLING = re.compile(r"\b(langfuse|opentelemetry|langsmith|ragas|deepeval|promptfoo)\b", re.IGNORECASE)


@pytest.fixture(scope="session")
def assist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-assist fixture, built once per test run. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-assist"
    build_fixture.build("acme-assist", target)
    return target


def planted_line(repo: Path, rel: str, pattern: str) -> int:
    """The 1-based line in repo/rel that pattern matches; it must match exactly one line."""
    lines = (repo / rel).read_text(encoding="utf-8").splitlines()
    hits = [number for number, line in enumerate(lines, start=1) if re.search(pattern, line)]
    assert len(hits) == 1, f"{pattern!r} matches lines {hits} of {rel}, expected exactly one"
    return hits[0]


def tracked(repo: Path) -> list[str]:
    return git(repo, "ls-files").splitlines()


def knowledge_files(repo: Path) -> list[str]:
    return sorted(p.relative_to(repo).as_posix() for p in (repo / "knowledge").rglob("*") if p.is_file())


def test_history_has_every_commit_and_a_stable_head(assist: Path) -> None:
    log = git(assist, "log", "--format=%h %s").splitlines()
    assert len(log) == COMMITS
    assert log[0] == f"{HEAD} Brief: e-mail tagging for the shared inbox"
    assert log[-1].endswith(" Prototype: chat over the Kestrel manuals")


def test_last_commit_equals_the_stored_files(assist: Path) -> None:
    for path in FILES.rglob("*"):
        if path.is_file():
            rel = path.relative_to(FILES).as_posix().removesuffix(".fixture")
            assert git(assist, "show", f"HEAD:{rel}") == path.read_text(encoding="utf-8"), rel


def test_extras_are_on_disk_but_ignored(assist: Path) -> None:
    snapshot = assist / "data" / "stock_snapshot.csv"
    assert snapshot.is_file()
    assert snapshot.read_text(encoding="utf-8").startswith("sku,name,warehouse,qty,exported_at\n")
    assert "data/stock_snapshot.csv" not in tracked(assist)
    assert git(assist, "status", "--porcelain") == ""


@pytest.mark.parametrize(("number", "name", "rel", "pattern"), PLANTED, ids=[p[1] for p in PLANTED])
def test_planted_flaw_sits_on_its_line(
    assist: Path, record_property: Callable[[str, object], None], number: int, name: str, rel: str, pattern: str
) -> None:
    line = planted_line(assist, rel, pattern)
    record_property("planted", f"{number} {name}: {rel}:{line}")
    assert f"{rel}:{line}" == PLANTED_AT[number]


def test_the_planted_flaws_are_not_mitigated_elsewhere(assist: Path) -> None:
    src = assist / "src" / "acme_assist"
    agent = (src / "agent.py").read_text(encoding="utf-8")
    tools = (src / "tools.py").read_text(encoding="utf-8")
    assert "tools.run(call.function.name, call.function.arguments)" in agent
    assert "tools=tools.TOOLS" in agent
    assert not re.search(r"max_(steps|turns|iterations)|for _ in range", agent)
    assert '"fetch_url"' in tools and '"send_email"' in tools
    assert not re.search(r"\b(allow\w*|confirm\w*|approv\w*)\b", tools, re.IGNORECASE)
    assert "timeout" not in (src / "llm.py").read_text(encoding="utf-8")
    assert "stock_level(sku_or_name)" in tools
    assert "STOCK_SNAPSHOT" in (src / "config.py").read_text(encoding="utf-8")


def test_no_eval_or_tracing_tooling(assist: Path) -> None:
    for rel in tracked(assist):
        assert not {"eval", "evals"} & set(Path(rel).parts), rel
        text = (assist / rel).read_text(encoding="utf-8")
        assert not TOOLING.search(text), (rel, TOOLING.findall(text))


def test_the_corpus_has_its_formats_scripts_and_one_duplicate(assist: Path) -> None:
    files = knowledge_files(assist)
    assert len(files) == 21
    assert sorted(f for f in files if f.endswith(".pdf")) == sorted(PDF_PAGES)
    texts = {f: (assist / f).read_text(encoding="utf-8") for f in files}
    assert sorted(f for f, text in texts.items() if CYRILLIC.search(text)) == CYRILLIC_FILES
    assert sorted(f for f, text in texts.items() if SERBIAN_LATIN.search(text)) == SERBIAN_LATIN_FILES
    by_hash: dict[str, list[str]] = defaultdict(list)
    for f in files:
        by_hash[hashlib.sha256((assist / f).read_bytes()).hexdigest()].append(f)
    duplicates = [sorted(group) for group in by_hash.values() if len(group) > 1]
    assert duplicates == [["knowledge/archive/faq-en-old.md", "knowledge/faq-en.md"]]


@pytest.mark.parametrize(("rel", "pages"), PDF_PAGES.items())
def test_pdfs_are_minimal_valid_ascii(assist: Path, rel: str, pages: int) -> None:
    data = (assist / rel).read_bytes()
    assert data.startswith(b"%PDF-1.4\n")
    assert data.isascii()
    assert len(re.findall(rb"/Type\s*/Page(?![s\w])", data)) == pages
    start = int(re.findall(rb"startxref\n(\d+)\n%%EOF", data)[-1])
    table = re.match(rb"xref\n0 (\d+)\n((?:\d{10} \d{5} [fn] \n)+)", data[start:])
    assert table, "the startxref offset does not point at the xref table"
    entries = re.findall(rb"(\d{10}) \d{5} ([fn])", table.group(2))
    assert len(entries) == int(table.group(1))
    for number, (offset, kind) in enumerate(entries):
        if kind == b"n":
            assert data[int(offset) :].startswith(f"{number} 0 obj".encode()), (rel, number)


def test_briefs_state_their_facts_without_naming_an_architecture(assist: Path) -> None:
    briefs = assist / "docs" / "briefs"
    support = " ".join((briefs / "support-v2.md").read_text(encoding="utf-8").split())
    tagging = " ".join((briefs / "email-tagging.md").read_text(encoding="utf-8").split())
    for fact in ["3,000 questions per day", "400 per hour", "~55%", "~25%", "~12%", "~8%", "OrderDesk"]:
        assert fact in support, fact
    for fact in ["41 manuals", "2,400 pages", "RMA number", "6 support agents", "West Europe", "5 seconds"]:
        assert fact in support, fact
    for fact in ["€1,500", "50% of how-to", "4.2", "in stock when they were not"]:
        assert fact in support, fact
    for fact in ["200 e-mails per day", "HelpLine", "5%", "5 minutes", "€50", "nothing is sent to customers"]:
        assert fact in tagging, fact
    for category in ["order", "technical", "returns", "invoice", "partnership", "spam"]:
        assert re.search(rf"\b{category}\b", tagging), category
    architecture = re.compile(r"\b(RAG|retrieval|vector|embeddings?|fine-tun\w*|classifier|LLM|agentic)\b", re.I)
    assert not architecture.search(support + tagging)


def test_the_code_compiles_and_the_unit_test_passes(assist: Path) -> None:
    for path in sorted((assist / "src").rglob("*.py")) + sorted((assist / "tests").rglob("*.py")):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    env = {**os.environ, "PYTHONPATH": "src"}
    done = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=assist,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert "Ran 5 tests" in done.stderr
