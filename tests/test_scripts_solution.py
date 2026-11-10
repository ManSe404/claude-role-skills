"""join_facts.py, on the acme-solution fixture and on small cases of its own."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT, load, run_json
from test_fixture_acme_solution import (
    AI_STACK,
    BUDGET,
    COSTS,
    FORBIDDEN_SUM,
    PAGES,
    PLANTED_CONFLICTS,
    STALE_THRESHOLD_DAYS,
    TODAY,
)

JOIN = ROOT / "plugins" / "solutions-architect" / "skills" / "solution-blueprint" / "scripts" / "join_facts.py"
join_facts = load(JOIN)
BASE_PAGE: dict[str, Any] = {
    "skill": "x",
    "title": "T",
    "sections": [{"title": "S", "blocks": [{"type": "text", "text": "plain"}]}],
}


def cost(item: str, monthly: float, currency: str = "EUR", **extra: Any) -> dict[str, Any]:
    return {"item": item, "monthly": monthly, "currency": currency, "as_of": "2026-11-01", "source": "s", **extra}


def write_page(folder: Path, skill: str, facts: dict[str, Any] | None, name: str | None = None) -> Path:
    page = dict(BASE_PAGE, skill=skill)
    if facts is not None:
        page["facts"] = {"version": 1, **facts}
    path = folder / (name or f"{skill}-2026-11-01.json")
    path.write_text(json.dumps(page), encoding="utf-8")
    return path


def join(folder: Path, *args: str) -> dict[str, Any]:
    result: dict[str, Any] = run_json(JOIN, str(folder), "--today", TODAY, *args)
    return result


def of_type(result: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [c for c in result["conflicts"] if c["type"] == kind]


@pytest.fixture(scope="module")
def result(solution_repo: Path) -> dict[str, Any]:
    joined: dict[str, Any] = run_json(JOIN, str(solution_repo / "pages"), "--today", TODAY)
    return joined


def test_every_page_is_read_and_nothing_is_missing(result: dict[str, Any]) -> None:
    assert sorted(p["file"] for p in result["pages"]["read"]) == sorted(PAGES)
    assert result["pages"]["missing_skills"] == [] and result["pages"]["no_facts"] == []
    assert result["pages"]["brief_page"] is None


@pytest.mark.parametrize(
    ("kind", "pages", "value"), PLANTED_CONFLICTS, ids=[c[0] + "-" + c[2] for c in PLANTED_CONFLICTS]
)
def test_every_planted_conflict_is_found(result: dict[str, Any], kind: str, pages: tuple[str, ...], value: str) -> None:
    candidates = [c for c in result["conflicts"] if c["type"] == kind and value in json.dumps(c["values"])]
    assert candidates, kind
    assert any(set(pages) <= set(c["pages"]) for c in candidates), [c["pages"] for c in candidates]


def test_a_conflict_says_where_to_read_it(result: dict[str, Any]) -> None:
    assert all(c["read"] and c["pages"] and c["values"] for c in result["conflicts"])
    assert result["conflict_counts"]["region_forbidden"] == 2


def test_the_forbidden_region_names_the_component_and_the_rule(result: dict[str, Any]) -> None:
    east = next(c for c in of_type(result, "region_forbidden") if c["values"]["region"] == "East US")
    assert {comp["id"] for comp in east["values"]["components"]} == {"llm", "search"}
    assert east["values"]["area"] == "US" and any(r["rule"] == "EU only" for r in east["values"]["rules"])
    west = next(c for c in of_type(result, "region_forbidden") if c["values"]["region"] == "West US 2")
    assert west["values"]["components"][0]["kind"] == "store"
    assert west["values"]["components"][0]["named_in_rule"] is True


def test_costs_per_currency_and_cloud_match_the_pages(result: dict[str, Any]) -> None:
    groups = {(g["currency"], g["cloud"]): g for g in result["costs"]["groups"]}
    assert {k: g["total"] for k, g in groups.items()} == {(c, cl, t)[:2]: t for c, cl, t in COSTS}
    azure = groups[("EUR", "Azure")]
    assert sorted(azure["added_across_pages"]) == sorted(p for p in PAGES if p.startswith(("cloud", "data")))
    # The stated total stands for its page: the line items beside it are not added again.
    assert next(p for p in azure["per_page"] if p["page"].startswith("cloud"))["total"] == 6180.0
    assert azure["oldest_as_of"] == "2026-11-02" and azure["newest_as_of"] == "2026-11-07"
    assert all(i["source"] and i["as_of"] for g in groups.values() for i in g["items"])


def test_mixed_currencies_are_never_summed(result: dict[str, Any]) -> None:
    assert FORBIDDEN_SUM not in {g["total"] for g in result["costs"]["groups"]}
    assert str(FORBIDDEN_SUM) not in json.dumps(result)
    assert result["costs"]["currencies"] == ["EUR", "USD"]
    assert all(len({i["currency"] for i in g["items"]}) == 1 for g in result["costs"]["groups"])


def test_mixed_currencies_are_never_summed_in_a_small_case(tmp_path: Path) -> None:
    write_page(tmp_path, "cloud-design", {"costs": [cost("a", 100.0, "EUR"), cost("b", 100.0, "EUR")]})
    write_page(tmp_path, "ai-stack", {"costs": [cost("c", 50.0, "USD")]})
    joined = join(tmp_path)
    assert sorted((g["currency"], g["total"]) for g in joined["costs"]["groups"]) == [("EUR", 200.0), ("USD", 50.0)]
    assert len(of_type(joined, "mixed_currencies")) == 1
    assert "250" not in json.dumps(joined["costs"])


def test_the_budget_is_compared_in_its_currency_only(result: dict[str, Any]) -> None:
    over = of_type(result, "over_budget")
    assert len(over) == 1 and over[0]["values"]["cloud"] == "Azure"
    assert over[0]["values"]["budget"] == BUDGET[0] and over[0]["values"]["over_by"] == 1360.0
    other = of_type(result, "budget_other_currency")
    assert len(other) == 1 and other[0]["values"]["other_currency"] == "USD"


def test_the_stale_cost_uses_the_named_threshold(result: dict[str, Any]) -> None:
    stale = of_type(result, "stale_cost")[0]
    assert stale["pages"] == [AI_STACK] and stale["values"]["age_days"] == 253
    assert result["thresholds"]["stale_cost_days"] == STALE_THRESHOLD_DAYS == join_facts.STALE_COST_DAYS


def test_stale_days_can_be_changed_and_is_printed(tmp_path: Path) -> None:
    write_page(tmp_path, "ai-stack", {"costs": [cost("a", 1.0, as_of="2026-10-01")]})
    assert of_type(join(tmp_path, "--stale-days", "30"), "stale_cost")
    assert join(tmp_path, "--stale-days", "90")["thresholds"]["stale_cost_days"] == 90
    assert not of_type(join(tmp_path, "--stale-days", "90"), "stale_cost")


def test_a_budget_cost_with_cloud_and_variant_keeps_alternatives_apart(tmp_path: Path) -> None:
    facts = {
        "budget": {"monthly": 100, "currency": "EUR", "source": "brief"},
        "costs": [
            cost("compute", 80.0, cloud="Azure", variant="A"),
            cost("compute", 90.0, cloud="Azure", variant="B"),
        ],
    }
    write_page(tmp_path, "cloud-design", facts)
    joined = join(tmp_path)
    assert {g["variant"]: g["total"] for g in joined["costs"]["groups"]} == {"A": 80.0, "B": 90.0}
    assert not of_type(joined, "over_budget")


def test_unlabelled_alternatives_are_not_added(tmp_path: Path) -> None:
    write_page(
        tmp_path,
        "ai-stack",
        {"costs": [cost("Variant A, models", 10.0), cost("Variant B, models", 20.0)]},
    )
    group = join(tmp_path)["costs"]["groups"][0]
    assert group["total"] is None and "variants" in group["not_added_because"]


def test_two_stated_totals_on_one_page_are_not_added(tmp_path: Path) -> None:
    write_page(tmp_path, "cloud-design", {"costs": [cost("AWS, total", 10.0), cost("Azure, total", 20.0)]})
    group = join(tmp_path)["costs"]["groups"][0]
    assert group["total"] is None and "2 lines say total" in group["not_added_because"]


@pytest.mark.parametrize(
    ("name", "areas"),
    [
        ("West Europe", {"EU"}),
        ("westeurope", {"EU"}),
        ("eu-central-1", {"EU"}),
        ("Germany West Central", {"EU"}),
        ("East US", {"US"}),
        ("eastus2", {"US"}),
        ("us-east-1", {"US"}),
        ("uksouth", {"UK"}),
        ("ap-southeast-1", {"APAC"}),
        ("global", {"GLOBAL"}),
        ("Mars Base", set()),
    ],
)
def test_regions_are_placed_by_name(name: str, areas: set[str]) -> None:
    assert join_facts.areas_of(name) == areas


@pytest.mark.parametrize(
    ("rule", "confined", "refused"),
    [
        ("EU only", {"EU"}, set()),
        ("EU only; masked at the gate before served", {"EU"}, set()),
        ("stays in the EU", {"EU"}, set()),
        ("HelpLine must be in the EU; its location is not known", {"EU"}, set()),
        ("must not leave the EU", {"EU"}, set()),
        ("not to the US", set(), {"US"}),
        ("no rule found in the repository", set(), set()),
        ("hashed in gold", set(), set()),
        ("only in the export", set(), set()),
        ("let us know", set(), set()),
        ("stays in the United States", {"US"}, set()),
        ("kept for comparison only", set(), set()),
    ],
)
def test_data_rules_are_read(rule: str, confined: set[str], refused: set[str]) -> None:
    assert join_facts.rule_areas(rule) == (confined, refused)


def test_a_region_nobody_can_place_is_listed_not_passed(tmp_path: Path) -> None:
    write_page(tmp_path, "cloud-design", {"regions": [{"name": "Mars Base"}]})
    write_page(tmp_path, "data-platform", {"data": [{"name": "d", "class": "personal", "rule": "EU only"}]})
    joined = join(tmp_path)
    assert joined["regions_not_placed"] == [{"region": "Mars Base", "page": "cloud-design-2026-11-01.json"}]
    assert not of_type(joined, "region_forbidden")


def test_a_wide_region_does_not_disagree_with_a_named_one_inside_it(tmp_path: Path) -> None:
    write_page(tmp_path, "data-platform", {"regions": [{"name": "EU"}]})
    write_page(tmp_path, "cloud-design", {"regions": [{"name": "West Europe"}]})
    assert not of_type(join(tmp_path), "regions_disagree")


def test_the_same_region_named_differently_does_not_disagree(tmp_path: Path) -> None:
    write_page(tmp_path, "data-platform", {"regions": [{"name": "West Europe"}]})
    write_page(tmp_path, "cloud-design", {"regions": [{"name": "westeurope"}]})
    assert not of_type(join(tmp_path), "regions_disagree")


def test_a_technology_named_at_two_levels_of_detail_is_not_a_conflict(tmp_path: Path) -> None:
    write_page(tmp_path, "cloud-design", {"components": [{"id": "db", "label": "DB", "tech": "PostgreSQL, 4 vCore"}]})
    write_page(
        tmp_path, "ai-stack", {"components": [{"id": "db", "label": "DB", "tech": "Azure Database for PostgreSQL"}]}
    )
    write_page(tmp_path, "data-platform", {"components": [{"id": "db", "label": "DB", "tech": "not chosen"}]})
    assert not of_type(join(tmp_path), "component_technology")


def test_decision_titles_match_loosely_and_only_across_pages(tmp_path: Path) -> None:
    write_page(tmp_path, "arch-style", {"decisions": [{"title": "Hosting", "chosen": "A"}]})
    write_page(tmp_path, "cloud-design", {"decisions": [{"title": "hosting.", "chosen": "B"}]})
    joined = join(tmp_path)
    assert len(of_type(joined, "decision_differs")) == 1
    write_page(tmp_path, "cloud-design", {"decisions": [{"title": "hosting.", "chosen": "a"}]})
    assert not of_type(join(tmp_path), "decision_differs")


def test_assumptions_are_compared_only_where_a_pattern_can_tell(tmp_path: Path) -> None:
    write_page(tmp_path, "arch-style", {"assumptions": ["Team of 5 engineers.", "The shop is busy on Fridays."]})
    write_page(tmp_path, "cloud-design", {"assumptions": ["We have 12 developers.", "The shop is quiet on Fridays."]})
    numbers = of_type(join(tmp_path), "assumption_numbers")
    assert len(numbers) == 1 and {s["number"] for s in numbers[0]["values"]["said"]} == {5.0, 12.0}


def test_the_newest_page_of_a_skill_wins(tmp_path: Path) -> None:
    write_page(
        tmp_path, "cloud-design", {"decisions": [{"title": "Hosting", "chosen": "old"}]}, "cloud-design-2026-10-01.json"
    )
    write_page(
        tmp_path, "cloud-design", {"decisions": [{"title": "Hosting", "chosen": "new"}]}, "cloud-design-2026-11-01.json"
    )
    joined = join(tmp_path)
    assert joined["pages"]["superseded"] == [
        {"file": "cloud-design-2026-10-01.json", "by": "cloud-design-2026-11-01.json", "skill": "cloud-design"}
    ]
    assert [d["chosen"] for d in joined["merged"]["decisions"]] == ["new"]


def test_an_earlier_blueprint_and_other_files_are_skipped(tmp_path: Path) -> None:
    write_page(tmp_path, "solution-blueprint", {"regions": [{"name": "Mars Base"}]})
    (tmp_path / "SITE.json").write_text('{"title": "x", "pages": []}', encoding="utf-8")
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    write_page(tmp_path, "arch-style", None)
    joined = join(tmp_path)
    assert [p["file"] for p in joined["pages"]["read"]] == ["arch-style-2026-11-01.json"]
    assert joined["pages"]["no_facts"] == ["arch-style-2026-11-01.json"]
    assert {s["file"] for s in joined["pages"]["skipped"]} == {"SITE.json", "solution-blueprint-2026-11-01.json"}
    assert [i["file"] for i in joined["pages"]["invalid"]] == ["broken.json"]
    assert joined["regions_not_placed"] == []


def test_expected_skills_come_from_the_brief_page(tmp_path: Path) -> None:
    write_page(tmp_path, "solution-brief", {"specialists": ["arch-style", "cloud-design"]})
    write_page(tmp_path, "arch-style", {"decisions": []})
    joined = join(tmp_path)
    assert joined["pages"]["missing_skills"] == ["cloud-design"]
    assert joined["pages"]["brief_page"] == "solution-brief-2026-11-01.json"
    assert "specialists on" in joined["pages"]["expected_from"]


def test_expect_overrides_and_the_default_is_the_deciding_skills(tmp_path: Path) -> None:
    write_page(tmp_path, "arch-style", {})
    assert join(tmp_path, "--expect", "arch-style")["pages"]["missing_skills"] == []
    default = join(tmp_path)
    assert set(default["pages"]["missing_skills"]) == set(join_facts.DECIDING_SKILLS) - {"arch-style"}
    assert default["pages"]["expected_from"] == "the deciding skills"


def test_it_is_read_only_and_refuses_a_bad_input(solution_repo: Path) -> None:
    before = {p: p.read_bytes() for p in (solution_repo / "pages").iterdir()}
    run_json(JOIN, str(solution_repo / "pages"), "--today", TODAY)
    assert before == {p: p.read_bytes() for p in (solution_repo / "pages").iterdir()}
    done = subprocess.run([sys.executable, str(JOIN), "/no/such/folder"], capture_output=True, text=True, timeout=120)
    assert done.returncode == 2 and "not found" in done.stderr
    bad = subprocess.run(
        [sys.executable, str(JOIN), ".", "--today", "soon"], capture_output=True, text=True, timeout=120
    )
    assert bad.returncode == 2


def test_a_run_over_the_real_example_pages_does_not_crash() -> None:
    pages = sorted(str(p) for p in ROOT.glob("plugins/*/skills/*/references/example.json"))
    assert len(pages) >= 19
    joined: dict[str, Any] = run_json(JOIN, *pages, "--today", TODAY)
    assert joined["pages"]["read"]
    assert all(c["type"] and c["pages"] for c in joined["conflicts"])
    json.dumps(joined)


def test_the_pack_depends_on_the_four_specialists() -> None:
    manifest = json.loads((ROOT / "plugins" / "solutions-architect" / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["dependencies"] == ["ai-architect", "data-architect", "software-architect", "cloud-architect"]
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    names = {entry["name"] for entry in market["plugins"]}
    assert set(manifest["dependencies"]) <= names
