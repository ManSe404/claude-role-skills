"""The selection check: its cases name real skills, and the judging is right. Nothing here calls Claude."""

from __future__ import annotations

import json
from typing import Any

from conftest import ROOT, load

check = load(ROOT / "tools" / "selection_check.py")
CASES: list[dict[str, Any]] = json.loads(check.CASES.read_text("utf-8"))
OURS = check.our_skills()


def test_every_case_is_well_formed() -> None:
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)), "duplicate ids"
    for case in CASES:
        assert set(case) == {"id", "prompt", "expect"}
        assert set(case["expect"]) <= OURS, case["id"]


def test_every_skill_has_a_case() -> None:
    covered = {skill for case in CASES for skill in case["expect"]}
    assert covered == OURS


def test_no_prompt_names_a_skill() -> None:
    for case in CASES:
        for skill in OURS:
            assert skill not in case["prompt"], (case["id"], skill)


def test_there_are_cases_where_nothing_should_fire() -> None:
    assert sum(1 for case in CASES if not case["expect"]) >= 10


def test_a_namespaced_skill_counts_as_its_bare_name() -> None:
    assert check.bare_name("data-scientist:ds-explore") == "ds-explore"
    assert check.bare_name("impact") == "impact"


def test_judging() -> None:
    ours = {"a", "b"}
    assert check.judge("a", ["a"], ours)
    assert check.judge("b", ["a", "b"], ours), "either accepted skill passes"
    assert not check.judge("b", ["a"], ours), "the wrong skill fails"
    assert not check.judge(None, ["a"], ours), "no skill fails when one was expected"
    assert check.judge(None, [], ours), "no skill passes when none was expected"
    assert check.judge("somebody-elses", [], ours), "a skill from elsewhere is not one of ours"
    assert not check.judge("a", [], ours), "one of ours firing when none should fails"


def stream(*events: dict[str, Any]) -> list[str]:
    return [json.dumps(e) for e in events]


def test_the_first_skill_call_is_the_answer() -> None:
    lines = stream(
        {"type": "system", "subtype": "init", "model": "m", "skills": ["x", "y", "z"]},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "I will use it."},
                    {"type": "tool_use", "name": "Skill", "input": {"skill": "pack:first"}},
                    {"type": "tool_use", "name": "Skill", "input": {"skill": "pack:second"}},
                ]
            },
        },
        {"type": "result", "total_cost_usd": 0.12},
    )
    found = check.parse_stream(["not json", *lines])
    assert found == {
        "picked": "first",
        "picked_full": "pack:first",
        "plugins": [],
        "first_tool": "Skill",
        "cost": 0.12,
        "model": "m",
        "skills_listed": 3,
        "text": "I will use it.",
    }


def test_a_first_look_at_a_file_is_recorded_and_is_not_a_pick() -> None:
    lines = stream(
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {}}]}},
    )
    found = check.parse_stream(lines)
    assert (found["first_tool"], found["picked"]) == ("Read", None)


def test_a_transcript_without_a_skill_call_picks_nothing() -> None:
    assert check.parse_stream(stream({"type": "assistant", "message": {"content": []}}))["picked"] is None


def test_summary_separates_the_kinds_of_miss() -> None:
    outcomes = [
        check.Outcome("a", 1, ["x"], picked="x", cost=0.1, passed=True),
        check.Outcome("b", 1, ["x"], picked="y", cost=0.1, passed=False),
        check.Outcome("c", 1, ["x"], picked=None, cost=0.1, passed=False),
        check.Outcome("d", 1, [], picked=None, cost=0.1, passed=True),
        check.Outcome("e", 1, [], picked="x", cost=0.1, passed=False),
        check.Outcome("f", 1, ["x"], error="timed out"),
        check.Outcome("g", 1, ["x"], first_tool="Read", passed=False),
    ]
    summary = check.summarise(outcomes)
    assert summary["cases_run"] == 7
    assert summary["errors"] == 1
    assert (summary["should_fire"], summary["should_fire_passed"]) == (4, 1)
    assert (summary["should_not_fire"], summary["should_not_fire_passed"]) == (2, 1)
    assert summary["wrong_skill"] == 1
    assert summary["no_skill_when_one_was_expected"] == 2
    assert summary["looked_first"] == 1
    assert summary["cost_usd"] == 0.5


def test_a_pick_from_another_plugin_keeps_its_full_name() -> None:
    assert check.from_elsewhere("engineering:code-review", OURS) == "engineering:code-review"
    assert check.from_elsewhere("code-review", OURS) == "code-review"
    assert check.from_elsewhere("software-engineering:code-audit", OURS) is None
    assert check.from_elsewhere("code-audit", OURS) is None
    assert check.from_elsewhere(None, OURS) is None


def test_the_summary_counts_picks_from_other_plugins() -> None:
    outcomes = [
        check.Outcome("a", 1, [], picked="code-review", picked_full="engineering:code-review", passed=True),
        check.Outcome("b", 1, [], picked="code-review", picked_full="engineering:code-review", passed=True),
        check.Outcome("c", 1, ["arch-review"], picked="arch-review", picked_full="software-architect:arch-review"),
    ]
    assert check.summarise(outcomes)["picked_elsewhere"] == {"engineering:code-review": 2}


def test_a_pack_loaded_from_an_installed_copy_is_caught() -> None:
    plugins = [ROOT / "plugins" / "software-engineering", ROOT / "plugins" / "data-analyst"]
    loaded = [
        {"name": "software-engineering", "path": str(ROOT / "plugins" / "software-engineering")},
        {"name": "data-analyst", "path": "/home/someone/.claude/plugins/cache/x/data-analyst/0.2.0"},
        {"name": "engineering", "path": "/somewhere/else"},
    ]
    assert check.foreign_packs(loaded, plugins) == [
        "data-analyst from /home/someone/.claude/plugins/cache/x/data-analyst/0.2.0"
    ]


def test_the_start_event_lists_the_plugins() -> None:
    found = check.parse_stream(
        stream({"type": "system", "subtype": "init", "model": "m", "plugins": [{"name": "a", "path": "/p/a", "x": 1}]})
    )
    assert found["plugins"] == [{"name": "a", "path": "/p/a"}]
