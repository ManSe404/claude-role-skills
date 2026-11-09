from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL_SKILLS, ROOT, load

render = load(ROOT / "shared" / "render_page.py")


def page(**extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "skill": "impact",
        "title": "Changing order_total",
        "sections": [{"title": "Notes", "blocks": [{"type": "text", "text": "Plain."}]}],
    }
    base.update(extra)
    return base


def test_a_minimal_page_renders() -> None:
    assert render.validate(page()) == []
    html = render.render(page())
    assert html.startswith("<!doctype html>")
    assert "<h1>Changing order_total</h1>" in html


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"title": None}, "page.title: must be a string"),
        ({"sections": []}, "page.sections: at least one section"),
        ({"verdict": {"text": "x", "tone": "great"}}, "page.verdict.tone"),
        ({"stats": [{"label": "n"}]}, "page.stats[0].value"),
    ],
)
def test_page_level_errors(change: dict[str, Any], error: str) -> None:
    assert any(e.startswith(error) for e in render.validate(page(**change)))


def test_block_errors_name_their_path() -> None:
    blocks = [
        {
            "type": "graph",
            "nodes": [{"id": "a", "label": "A"}, {"id": "a", "label": "B"}],
            "edges": [{"from": "a", "to": "z"}],
        },
        {"type": "findings", "items": [{"severity": "high", "title": "t", "status": "declined"}]},
        {"type": "table", "columns": ["a", "b"], "rows": [["only one"]]},
        {"type": "chart"},
    ]
    errors = render.validate(page(sections=[{"title": "S", "blocks": blocks}]))
    assert "page.sections[0].blocks[0].nodes[1].id: duplicate id 'a'" in errors
    assert "page.sections[0].blocks[0].edges[0].to: unknown node id 'z'" in errors
    assert any("blocks[1].items[0].reason" in e for e in errors)
    assert any("blocks[2].rows[0]" in e for e in errors)
    assert any("blocks[3].type" in e for e in errors)


def test_everything_is_escaped_and_unsafe_links_are_dropped() -> None:
    hostile = "<script>alert(1)</script> [x](javascript:alert(1)) [ok](https://example.com) `<b>`"
    blocks = [
        {"type": "text", "text": hostile},
        {"type": "findings", "items": [{"severity": "low", "title": hostile, "where": "<i>"}]},
        {"type": "code", "code": "</code><script>x</script>"},
        {"type": "graph", "nodes": [{"id": "a", "label": "<svg onload=x>"}], "edges": []},
    ]
    html = render.render(page(title="<img src=x>", sections=[{"title": "<b>", "blocks": blocks}]))
    assert "<script>alert" not in html and "<img" not in html and "<svg onload" not in html
    assert html.count("<script") == 1  # only the page's own script
    hrefs = re.findall(r'href="([^"]*)"', html)
    assert "https://example.com" in hrefs
    assert not any(h.lower().startswith("javascript") for h in hrefs)


def test_confidence_tags_become_badges() -> None:
    html = render.render(
        page(sections=[{"title": "S", "blocks": [{"type": "text", "text": "Checked [high], maybe [med]"}]}])
    )
    assert 'class="tag tag-high"' in html and 'class="tag tag-med"' in html


def test_findings_are_shown_high_first() -> None:
    items = [{"severity": s, "title": s} for s in ("low", "info", "high", "medium")]
    html = render.render(page(sections=[{"title": "S", "blocks": [{"type": "findings", "items": items}]}]))
    assert [m for m in re.findall(r'class="chip sev-(\w+)"', html)] == ["high", "medium", "low", "info"]


def test_a_cycle_is_drawn_as_a_back_edge() -> None:
    graph = {
        "type": "graph",
        "nodes": [{"id": n, "label": n} for n in "abc"],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "a"}],
    }
    html = render.render(page(sections=[{"title": "S", "blocks": [graph]}]))
    assert len(re.findall(r'class="edge \w+ back"', html)) == 1
    assert len(re.findall(r'class="edge \w+"', html)) == 2


def test_edges_follow_the_change() -> None:
    graph = {
        "type": "graph",
        "nodes": [
            {"id": "in", "label": "caller", "group": "module"},
            {"id": "x", "label": "the change", "group": "changed"},
            {"id": "a", "label": "a use", "group": "affected"},
            {"id": "b", "label": "a table", "group": "data"},
            {"id": "c", "label": "elsewhere", "group": "module"},
        ],
        "edges": [
            {"from": "in", "to": "x"},
            {"from": "x", "to": "a"},
            {"from": "a", "to": "b"},
            {"from": "c", "to": "b"},
        ],
    }
    html = render.render(page(sections=[{"title": "S", "blocks": [graph]}]))
    assert re.findall(r'class="edge (\w+)"', html) == ["dim", "up", "down", "warm"]  # dim edges are drawn first


def test_the_page_fetches_nothing() -> None:
    html = render.render(page())
    assert html.count("<script>") == 1 and " src=" not in html and "<link" not in html
    assert set(re.findall(r'https?://[^"\s)]+', html)) <= {"http://www.w3.org/2000/svg"}


def test_the_design_is_dark_and_the_fonts_are_inlined() -> None:
    css = render.CSS
    assert css.count("{") == css.count("}")
    assert "color-scheme:dark" in css and "--ground:#080513" in css
    html = render.render(page())
    assert html.count("src:url(data:font/woff2;base64,") == 4
    assert "unicode-range:U+0100-02BA" in html  # latin-ext: č ć š ž đ


@pytest.mark.parametrize("skill", ALL_SKILLS, ids=lambda p: p.name)
def test_each_example_page_is_valid(skill: Path, tmp_path: Path) -> None:
    example = skill / "references" / "example.json"
    assert example.is_file(), f"{skill.name} has no references/example.json"
    data = json.loads(example.read_text(encoding="utf-8"))
    assert render.validate(data) == []
    assert data["skill"] == skill.name
    out = tmp_path / "page.html"
    assert render.main([str(example), "-o", str(out)]) == 0
    assert out.stat().st_size < 400_000  # ~200 KB of it are the inlined fonts


def test_the_script_never_turns_content_into_markup() -> None:
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "http"):
        assert unsafe not in render.SCRIPT, unsafe


def test_graph_elements_carry_their_keys() -> None:
    graph = {
        "type": "graph",
        "nodes": [{"id": "a", "label": 'A "quoted"'}, {"id": "b", "label": "B"}],
        "edges": [{"from": "a", "to": "b", "label": "calls"}],
    }
    html = render.render(page(sections=[{"title": "S", "blocks": [graph]}]))
    assert 'data-k="a" data-label="A &quot;quoted&quot;" tabindex="0" role="button"' in html
    assert html.count('data-a="a" data-b="b"') == 2  # the edge and its label


# ---------------------------------------------------------------------------- decision and architecture


def decision_block(**extra: Any) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "decision",
        "factors": ["Predictability", "Live state"],
        "options": [
            {
                "label": "RAG",
                "status": "eliminated",
                "eliminated_by": "Live state",
                "why": "stale copy",
                "cells": [{"rating": "pass"}, {"rating": "fail", "text": "nightly index"}],
            },
            {
                "label": "Routed workflow",
                "status": "chosen",
                "why": "known steps",
                "cells": [{"rating": "pass"}, {"rating": "pass", "text": "ERP call"}],
            },
        ],
    }
    block.update(extra)
    return block


def arch_block(**extra: Any) -> dict[str, Any]:
    """A small agent with a web fetch and a mail tool; the 'reviewed' variant puts a person before the mail."""
    block: dict[str, Any] = {
        "type": "architecture",
        "title": "Prototype",
        "zones": [{"id": "u", "label": "User"}, {"id": "ai", "label": "AI layer"}, {"id": "sys", "label": "Systems"}],
        "variants": [
            {"id": "now", "label": "As built"},
            {"id": "fixed", "label": "Reviewed", "note": "a person sends"},
        ],
        "components": [
            {"id": "customer", "label": "Customer", "zone": "u", "kind": "user"},
            {"id": "agent", "label": "Agent loop", "zone": "ai", "kind": "model", "tech": "tool calling"},
            {"id": "fetch", "label": "fetch_url", "zone": "sys", "kind": "tool"},
            {"id": "web", "label": "Any web page", "zone": "sys", "kind": "system"},
            {"id": "staff", "label": "Support staff", "zone": "sys", "kind": "human", "variants": ["fixed"]},
            {"id": "mail", "label": "send_email", "zone": "sys", "kind": "tool", "side_effect": True, "flag": "bad"},
        ],
        "links": [
            {"from": "customer", "to": "agent", "label": "question", "trust": "untrusted"},
            {"from": "agent", "to": "fetch", "label": "url"},
            {"from": "web", "to": "fetch", "label": "page text", "trust": "untrusted"},
            {"from": "agent", "to": "mail", "label": "send", "variants": ["now"]},
            {"from": "agent", "to": "staff", "label": "draft", "variants": ["fixed"]},
            {"from": "staff", "to": "mail", "label": "send", "variants": ["fixed"]},
        ],
        "flows": [
            {
                "id": "ask",
                "title": "A question",
                "steps": [
                    {"from": "customer", "to": "agent", "text": "Asks."},
                    {"from": "agent", "to": "fetch", "text": "Fetches a page."},
                ],
            },
        ],
    }
    block.update(extra)
    return block


def with_blocks(*blocks: dict[str, Any]) -> dict[str, Any]:
    return page(sections=[{"title": "S", "blocks": list(blocks)}])


def test_decision_errors_name_their_path() -> None:
    bad = decision_block()
    bad["options"][0].pop("why")
    bad["options"][1]["cells"] = [{"rating": "great"}]
    bad["options"].append({"label": "x", "status": "chosen", "cells": [{"rating": "pass"}, {"rating": "pass"}]})
    errors = render.validate(with_blocks(bad))
    path = "page.sections[0].blocks[0]"
    assert f"{path}.options[0].why: an eliminated option keeps what eliminated it and why" in errors
    assert f"{path}.options[1].cells: must hold one cell per factor (2)" in errors
    assert f"{path}.options[1].cells[0].rating: must be one of pass, weak, fail" in errors
    assert f"{path}.options: at most one option is chosen" in errors


def test_decision_marks_the_chosen_and_keeps_the_reason() -> None:
    html = render.render(with_blocks(decision_block()))
    assert '<tr class="o-chosen">' in html and '<tr class="o-eliminated">' in html
    assert '<div class="by">by Live state</div>' in html
    assert '<span class="mark">fail</span>nightly index' in html


def test_architecture_references_are_checked() -> None:
    bad = arch_block()
    bad["components"].append({"id": "x", "label": "X", "zone": "nowhere", "kind": "robot"})
    bad["links"].append({"from": "agent", "to": "ghost"})
    bad["links"].append({"from": "agent", "to": "staff"})  # staff exists only in "fixed"
    bad["flows"][0]["steps"].append({"from": "agent", "to": "staff", "text": "hands over"})
    bad["flows"].append({"id": "ask", "title": "dup", "variants": ["later"], "steps": []})
    errors = render.validate(with_blocks(bad))
    path = "page.sections[0].blocks[0]"
    assert f"{path}.components[6].zone: unknown zone id 'nowhere'" in errors
    assert any(e.startswith(f"{path}.components[6].kind: must be one of") for e in errors)
    assert f"{path}.links[6].to: unknown component id 'ghost'" in errors
    assert f"{path}.links[7].to: 'staff' is not shown in variant now" in errors
    assert f"{path}.flows[0].steps[2].to: 'staff' is not shown in variant now" in errors
    assert f"{path}.flows[1].id: duplicate id 'ask'" in errors
    assert f"{path}.flows[1].variants: unknown variant id 'later'" in errors
    assert f"{path}.flows[1].steps: at least one step" in errors


def test_untrusted_text_reaches_the_mail_tool_unless_a_person_is_in_between() -> None:
    block = arch_block()
    touched, paths = render.taint(block, "now")
    assert {"agent", "fetch", "mail"} <= touched
    assert [(entry["from"], target, path) for entry, target, path in paths] == [
        ("customer", "mail", ["customer", "agent", "mail"]),
        ("web", "mail", ["web", "fetch", "agent", "mail"]),
    ]
    touched, paths = render.taint(block, "fixed")
    assert paths == [] and "staff" in touched and "mail" not in touched
    html = render.render(with_blocks(block))
    assert (
        "<tr><td>As built</td><td>send_email</td><td>Customer → Agent loop; Any web page → fetch_url</td>"
        "<td>Customer → Agent loop → send_email</td></tr>" in html
    )
    assert re.search(r'class="comp k-tool se f-bad"[^>]*data-taint="now" data-risk="now"', html)


def test_architecture_is_escaped_deterministic_and_offline() -> None:
    block = arch_block()
    block["components"][1]["label"] = "<img src=x onerror=alert(1)>"
    block["components"][1]["details"] = [["<b>", "<script>x</script>"]]
    block["flows"][0]["steps"][0]["text"] = "[x](javascript:alert(1)) <svg onload=x>"
    data = with_blocks(decision_block(), block)
    assert render.validate(data) == []
    html = render.render(data)
    assert html == render.render(json.loads(json.dumps(data)))
    assert "<img" not in html and "<svg onload" not in html and html.count("<script") == 1
    assert not any(h.lower().startswith("javascript") for h in re.findall(r'href="([^"]*)"', html))
    assert set(re.findall(r'https?://[^"\s)]+', html)) <= {"http://www.w3.org/2000/svg"}


def test_architecture_lists_everything_for_readers_without_the_script() -> None:
    html = render.render(with_blocks(arch_block()))
    assert html.count('<article class="arch-card plate"') == 6
    assert '<div class="arch-flow" data-flow="ask" data-v="now fixed">' in html
    assert '<p class="arch-vnote" data-variant="fixed"><strong>Reviewed:</strong> a person sends</p>' in html
    assert 'data-set-variant="now" aria-pressed="true"' in html
    assert "Where untrusted text can reach an action" in html


def test_a_page_without_variants_still_toggles_nothing() -> None:
    block = arch_block()
    del block["variants"]
    for item in block["components"] + block["links"]:
        item.pop("variants", None)
    block["links"] = [link for link in block["links"] if (link["from"], link["to"]) != ("staff", "mail")]
    assert render.validate(with_blocks(block)) == []
    html = render.render(with_blocks(block))
    assert 'class="arch" data-default="_"' in html and '<button type="button" data-set-variant' not in html
