"""The page schema, the archetypes and `render_page.py --check` (ADR 0009)."""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from conftest import ALL_SKILLS, ROOT, load

render = load(ROOT / "shared" / "render_page.py")
SCHEMA = json.loads((ROOT / "shared" / "page-schema.json").read_text(encoding="utf-8"))
ARCHETYPES = json.loads((ROOT / "shared" / "page-archetypes.json").read_text(encoding="utf-8"))
EXAMPLES = sorted(ROOT.glob("plugins/*/skills/*/references/example.json"))


def review_page(**extra: Any) -> dict[str, Any]:
    page: dict[str, Any] = {
        "skill": "code-audit",
        "archetype": "review",
        "title": "acme-index, audited",
        "verdict": {"text": "Safe to build on after one fix.", "tone": "warn"},
        "facts": {"version": 1, "open": []},
        "sections": [
            {
                "title": "Findings",
                "blocks": [{"type": "findings", "items": [{"severity": "high", "title": "Totals drift"}]}],
            }
        ],
    }
    page.update(extra)
    return page


def test_the_schema_is_a_json_schema_and_names_every_archetype() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["properties"]["archetype"]["enum"] == list(ARCHETYPES["archetypes"])
    rule_names = set(ARCHETYPES["rules"])
    for name, spec in ARCHETYPES["archetypes"].items():
        assert spec["summary"], name
        for level in ("required", "recommended"):
            assert set(spec.get(level, {})) <= rule_names, f"{name}.{level} uses a rule the checker does not know"


def test_the_schema_knows_every_block_type_of_the_renderer() -> None:
    branches = {ref["$ref"].removeprefix("#/$defs/block_") for ref in SCHEMA["$defs"]["block"]["anyOf"]}
    assert branches == set(render.BLOCK_TYPES)


@pytest.mark.parametrize("example", EXAMPLES, ids=[p.parts[-3] for p in EXAMPLES])
def test_every_example_matches_the_schema(example: Path) -> None:
    page = json.loads(example.read_text(encoding="utf-8"))
    jsonschema.validate(page, SCHEMA)
    assert render.schema_problems(page, SCHEMA) == []


def test_a_valid_review_page_has_no_problems() -> None:
    assert render.check_page(review_page()) == ([], [])


@pytest.mark.parametrize(
    ("change", "error"),
    [
        (lambda p: p["sections"][0]["blocks"][0]["items"][0].update(sevrity="x"), "items[0].sevrity: unknown field"),
        (lambda p: p.update(verdict={"text": "x", "colour": "red"}), "page.verdict.colour: unknown field"),
        (lambda p: p["facts"].update(open="none"), "page.facts.open: must be a list"),
        (lambda p: p.update(archetype="essay"), "page.archetype: must be one of"),
        (lambda p: p["sections"][0]["blocks"].__setitem__(0, {"type": "text", "text": "x"}), "has a `findings` block"),
        (lambda p: p.pop("verdict"), "page.verdict: a review page has a verdict"),
    ],
)
def test_a_declared_archetype_turns_problems_into_errors(change: Any, error: str) -> None:
    page = review_page()
    change(page)
    errors, _ = render.check_page(page)
    assert any(error in e for e in errors), errors


def test_a_decision_page_needs_a_decision_in_its_facts() -> None:
    page = review_page(archetype="decision", facts={"version": 1, "decisions": []})
    errors, warnings = render.check_page(page)
    assert "page.facts.decisions: a decision page fills it with at least one item" in errors
    assert any("decision (recommended)" in w for w in warnings)


def test_recommended_rules_only_warn() -> None:
    page = review_page()
    del page["facts"]
    errors, warnings = render.check_page(page)
    assert errors == []
    assert warnings == ["page.facts.open: a review page fills it (an empty list is allowed) (recommended)"]


def test_a_page_without_an_archetype_is_held_to_validate_only() -> None:
    page = review_page()
    del page["archetype"]
    page["sections"][0]["blocks"][0]["items"][0]["sevrity"] = "x"
    errors, warnings = render.check_page(page)
    assert errors == []
    assert warnings[0].startswith("page.archetype: none declared")
    assert any("sevrity: unknown field" in w for w in warnings)


def test_shape_errors_come_first_and_alone() -> None:
    errors, warnings = render.check_page(review_page(title=None))
    assert errors == ["page.title: must be a string"]
    assert warnings == []


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "table", "columns": ["a"], "rows": [["x"]], "aling": ["left"]},
        {"type": "chart", "kind": "pie", "categories": ["a"], "series": [{"name": "n", "values": [1]}]},
        {"type": "code", "code": "x", "start": 0},
        {"type": "decision", "factors": [], "options": [{"label": "a", "cells": []}]},
    ],
)
def test_the_checker_and_a_standard_validator_agree(bad: dict[str, Any]) -> None:
    page = review_page()
    page["sections"][0]["blocks"].append(bad)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(page, SCHEMA)
    assert render.schema_problems(page, SCHEMA)


def _run(page: dict[str, Any], tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "page.json"
    source.write_text(json.dumps(page), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(ROOT / "shared" / "render_page.py"), str(source), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_names_the_archetype_of_a_valid_page(tmp_path: Path) -> None:
    result = _run(review_page(), tmp_path, "--check")
    assert result.returncode == 0
    assert result.stdout.strip().endswith(": valid (review)")


def test_check_fails_on_an_archetype_problem_and_prints_its_path(tmp_path: Path) -> None:
    page = review_page()
    page["sections"][0]["blocks"][0] = {"type": "text", "text": "No findings block."}
    result = _run(page, tmp_path, "--check")
    assert result.returncode == 1
    assert "page.sections: a review page has a `findings` block" in result.stderr


def test_an_old_page_still_renders_with_a_warning(tmp_path: Path) -> None:
    page = copy.deepcopy(review_page())
    del page["archetype"]
    result = _run(page, tmp_path, "-o", str(tmp_path / "page.html"))
    assert result.returncode == 0
    assert "warning: page.archetype: none declared" in result.stderr
    assert (tmp_path / "page.html").read_text(encoding="utf-8").startswith("<!doctype html>")


def test_every_skill_that_draws_a_page_ships_the_schema_and_the_archetypes() -> None:
    for skill in ALL_SKILLS:
        if (skill / "scripts" / "render_page.py").exists():
            for name in ("page-schema.json", "page-archetypes.json"):
                assert (skill / "references" / name).exists(), f"{skill.name} lacks references/{name}"


@pytest.mark.parametrize("skill", ALL_SKILLS, ids=[s.name for s in ALL_SKILLS])
def test_every_skill_names_its_archetype_and_its_example_is_one(skill: Path) -> None:
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    named = re.findall(r"^Page archetype: `([a-z]+)`", text, re.M)
    assert len(named) == 1, "SKILL.md names its archetype once, in a line starting 'Page archetype:'"
    assert named[0] in ARCHETYPES["archetypes"]
    assert "PAGE.json --check" in text, "SKILL.md runs render_page.py --check before the page is done"
    page = json.loads((skill / "references" / "example.json").read_text(encoding="utf-8"))
    assert page.get("archetype") == named[0], "the example page declares the archetype SKILL.md names"
    errors, _ = render.check_page(page)
    assert errors == []
