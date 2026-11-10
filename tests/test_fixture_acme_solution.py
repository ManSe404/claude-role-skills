"""The acme-solution fixture: the specialist pages of one made-up project, for the solutions-architect skills.

PLANTED_CONFLICTS lists what the join must find between the pages: (type, pages it names, a value it must carry).
PLANTED_GAPS are requirements of the brief that no page covers. COSTS are the group totals the join must show.
The evals and the script tests import these, so keep them in step with the fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

import build_fixture
import pytest
from conftest import ROOT, git, load

render = load(ROOT / "shared" / "render_page.py")

AI_PATTERN = "ai-pattern-2026-11-03.json"
AI_STACK = "ai-stack-2026-11-04.json"
DATA_PLATFORM = "data-platform-2026-11-05.json"
ARCH_STYLE = "arch-style-2026-11-05.json"
CLOUD_DESIGN = "cloud-design-2026-11-07.json"
PAGES = (AI_PATTERN, AI_STACK, DATA_PLATFORM, ARCH_STYLE, CLOUD_DESIGN)
BRIEF = "docs/briefs/claims-platform.md"
BRIEF_SMALL = "docs/briefs/room-booking.md"
# Fixed so the staleness check does not drift as the calendar moves on.
TODAY = "2026-11-10"
STALE_THRESHOLD_DAYS = 90
BUDGET = (6000.0, "EUR")

PLANTED_CONFLICTS: list[tuple[str, tuple[str, ...], str]] = [
    ("region_forbidden", (AI_STACK, DATA_PLATFORM), "East US"),
    ("region_forbidden", (CLOUD_DESIGN, DATA_PLATFORM), "West US 2"),
    ("regions_disagree", (AI_STACK, CLOUD_DESIGN, DATA_PLATFORM), "North Europe"),
    ("decision_differs", (ARCH_STYLE, CLOUD_DESIGN), "Hosting"),
    ("stale_cost", (AI_STACK,), "2026-03-02"),
    ("mixed_currencies", (AI_STACK, CLOUD_DESIGN, DATA_PLATFORM), "USD"),
    ("over_budget", (CLOUD_DESIGN, DATA_PLATFORM), "7360.0"),
    ("budget_other_currency", (AI_STACK, CLOUD_DESIGN), "USD"),
    ("component_technology", (AI_STACK, CLOUD_DESIGN, DATA_PLATFORM), "Azure SQL"),
    ("assumption_numbers", (AI_STACK, ARCH_STYLE, CLOUD_DESIGN), "team_size"),
]

# (currency, cloud, group total) for every group the join must show.
COSTS: list[tuple[str, str, float]] = [
    ("EUR", "AWS", 5640.0),
    ("EUR", "Azure", 7360.0),
    ("USD", "Azure", 2030.0),
]
# Adding across currencies must never produce this.
FORBIDDEN_SUM = 7360.0 + 2030.0

# In the brief, and on no page.
PLANTED_GAPS: tuple[str, ...] = ("single sign-on", "seven years")

FILES = ROOT / "fixtures" / "acme-solution" / "files"


def tracked(repo: Path) -> list[str]:
    return git(repo, "ls-files").split()


def test_the_build_is_deterministic(tmp_path: Path) -> None:
    heads = {build_fixture.build("acme-solution", tmp_path / name) for name in ("one", "two")}
    assert len(heads) == 1


def test_history_has_fictional_authors(solution_repo: Path) -> None:
    assert len(git(solution_repo, "log", "--format=%h").split()) == 2
    assert all(e.endswith("@example.com") for e in git(solution_repo, "log", "--format=%ae").split())


def test_layout_is_exact(solution_repo: Path) -> None:
    expected = {"README.md", BRIEF, BRIEF_SMALL, *(f"pages/{p}" for p in PAGES)}
    assert set(tracked(solution_repo)) == expected


def test_every_page_validates_and_is_the_skill_it_says(solution_repo: Path) -> None:
    for name in PAGES:
        page = json.loads((solution_repo / "pages" / name).read_text(encoding="utf-8"))
        assert render.validate(page) == [], name
        assert name.startswith(page["skill"]), name
        assert page["facts"]["version"] == 1, name


@pytest.mark.parametrize("gap", PLANTED_GAPS)
def test_the_gaps_are_in_the_brief_and_on_no_page(solution_repo: Path, gap: str) -> None:
    assert gap in (solution_repo / BRIEF).read_text(encoding="utf-8")
    for name in PAGES:
        assert gap not in (solution_repo / "pages" / name).read_text(encoding="utf-8").lower(), (gap, name)


def test_the_briefs_state_their_facts_without_naming_a_solution(solution_repo: Path) -> None:
    large = (solution_repo / BRIEF).read_text(encoding="utf-8")
    assert all(t in large for t in ("EUR 6,000 a month", "must stay in the EU", "5 engineers"))
    small = (solution_repo / BRIEF_SMALL).read_text(encoding="utf-8")
    assert "Hosting is decided" in small and "No AI" in small
    for text in (large, small):
        assert not any(word in text for word in ("RAG", "Azure", "AWS", "microservice", "modular monolith"))


def test_the_stored_files_are_the_last_commit(solution_repo: Path) -> None:
    for rel in tracked(solution_repo):
        assert (solution_repo / rel).read_bytes() == (FILES / rel).read_bytes(), rel
