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
        {"type": "pie"},
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
    assert "color-scheme:dark" in css and "--ground:#111419" in css
    html = render.render(page())
    assert html.count("src:url(data:font/woff2;base64,") == 8
    assert "unicode-range:U+0100-0101, U+0104-0130" in html  # Latin 2: č ć đ, and š ž further on


@pytest.mark.parametrize("skill", ALL_SKILLS, ids=lambda p: p.name)
def test_each_example_page_is_valid(skill: Path, tmp_path: Path) -> None:
    example = skill / "references" / "example.json"
    assert example.is_file(), f"{skill.name} has no references/example.json"
    data = json.loads(example.read_text(encoding="utf-8"))
    assert render.validate(data) == []
    assert data["skill"] == skill.name
    out = tmp_path / "page.html"
    assert render.main([str(example), "-o", str(out)]) == 0
    assert out.stat().st_size < 500_000  # ~200 KB of it are the inlined fonts


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


def model_block() -> dict[str, Any]:
    return {
        "type": "model",
        "title": "Sales",
        "areas": [{"id": "sales", "label": "Sales"}, {"id": "stock", "label": "Stock"}],
        "tables": [
            {
                "id": "fct",
                "label": "fct_sales",
                "kind": "fact",
                "area": "sales",
                "grain": "one row per order line",
                "columns": [
                    {"name": "order_id", "key": "pk", "type": "bigint"},
                    {"name": "line_no", "key": "pk", "type": "int"},
                    {"name": "customer_key", "key": "fk"},
                    {"name": "amount", "type": "decimal(18,2)"},
                ],
            },
            {
                "id": "cust",
                "label": "dim_customer",
                "kind": "dimension",
                "area": "sales",
                "history": "new row on change",
                "columns": [
                    {"name": "customer_key", "key": "pk"},
                    {"name": "email", "personal": True, "mask": "hashed in gold"},
                ],
            },
            {"id": "snap", "label": "fct_stock", "kind": "fact", "area": "stock", "columns": [{"name": "sku"}]},
        ],
        "relations": [{"from": "fct", "to": "cust", "on": "customer_key", "cardinality": "n:1"}],
    }


def test_model_references_are_checked() -> None:
    block = model_block()
    block["tables"][0]["area"] = "nope"
    block["tables"][0]["columns"].append({"name": "amount"})
    block["tables"][1]["kind"] = "lake"
    block["tables"][1]["columns"][1]["key"] = "secret"
    block["relations"] = [
        {"from": "fct", "to": "ghost"},
        {"from": "fct", "to": "cust", "on": "customer_key=nothing", "cardinality": "many"},
    ]
    errors = render.validate(with_blocks(block))
    start = "page.sections[0].blocks[0]"
    assert f"{start}.tables[0].area: unknown area id 'nope'" in errors
    assert f"{start}.tables[0].columns[4].name: duplicate column 'amount'" in errors
    assert any(e.startswith(f"{start}.tables[1].kind") for e in errors)
    assert any(e.startswith(f"{start}.tables[1].columns[1].key") for e in errors)
    assert f"{start}.relations[0].to: unknown table id 'ghost'" in errors
    assert f"{start}.relations[1].on: 'cust' has no column 'nothing'" in errors
    assert any(e.startswith(f"{start}.relations[1].cardinality") for e in errors)


def test_model_shows_keys_on_the_box_and_everything_on_the_card() -> None:
    data = with_blocks(model_block())
    assert render.validate(data) == []
    html = render.render(data)
    assert html == render.render(json.loads(json.dumps(data)))
    assert html.count('<article class="arch-card model-card plate"') == 3
    assert ">PK order_id</text>" in html and ">PK line_no</text>" in html
    assert ">+ 2 more columns</text>" in html and "+ 1 more column · 1 personal" in html
    assert ">no primary key</text>" in html
    assert "one row per order line" in html and "mask: hashed in gold" in html
    assert 'data-set-area="stock"' in html
    # The many side stands left of the one side, whichever way the relation is written.
    block = model_block()
    block["relations"] = [{"from": "cust", "to": "fct", "on": "customer_key", "cardinality": "1:n"}]
    flipped = render.render(with_blocks(block))
    for page_html in (html, flipped):
        xs = {
            m["k"]: float(m["x"])
            for m in re.finditer(r'data-k="(?P<k>fct|cust)"[^>]*>.*?<rect class="plate" x="(?P<x>[\d.]+)"', page_html)
        }
        assert xs["fct"] < xs["cust"]


def test_model_is_escaped() -> None:
    block = model_block()
    block["tables"][0]["label"] = "<img src=x onerror=alert(1)>"
    block["tables"][0]["columns"][0]["name"] = "<script>x</script>"
    block["relations"] = []
    html = render.render(with_blocks(block))
    assert "<img" not in html and html.count("<script") == 1


def reach_block() -> dict[str, Any]:
    block = arch_block()
    block["reach"] = {"label": "Personal data", "from": ["customer"], "stops": ["fetch"], "targets": ["mail", "fetch"]}
    return block


def test_reach_goes_the_way_the_links_point_and_stops_where_told() -> None:
    block = reach_block()
    touched, paths = render.reach(block, "now")
    assert paths == [["customer", "agent", "mail"], ["customer", "agent", "fetch"]]
    assert "web" not in touched  # against the arrow
    block["reach"]["stops"] = ["agent"]
    touched, paths = render.reach(block, "now")
    assert paths == [] and "agent" in touched and "mail" not in touched
    html = render.render(with_blocks(block))
    assert "None of the listed targets is reached" in html


def test_reach_ids_are_checked_and_shown_only_when_asked() -> None:
    block = reach_block()
    block["reach"]["from"] = ["ghost"]
    block["reach"]["targets"] = []
    errors = render.validate(with_blocks(block))
    assert "page.sections[0].blocks[0].reach.from[0]: unknown component id 'ghost'" in errors
    assert "page.sections[0].blocks[0].reach.targets: at least one component id" in errors
    html = render.render(with_blocks(reach_block()))
    assert 'class="arch-reach"' in html and "Personal data: what it reaches" in html
    assert "<td>Customer → Agent loop → send_email</td>" in html
    plain = render.render(with_blocks(arch_block()))
    assert 'class="arch-reach"' not in plain and "data-reach=" not in plain and "data-rpath=" not in plain


FACTS: dict[str, Any] = {
    "version": 1,
    "scope": "the platform",
    "regions": [{"name": "EU", "why": "residency"}],
    "data": [{"name": "contact", "class": "personal", "where": ["silver.customers"]}],
    "components": [{"id": "lake", "label": "Lakehouse", "kind": "store"}],
    "costs": [{"item": "x", "monthly": 420.0, "currency": "EUR", "as_of": "2026-11-09", "source": "price list"}],
    "decisions": [{"title": "Platform", "chosen": "Lakehouse", "because": "files"}],
    "assumptions": ["one"],
    "open": ["two"],
}


def test_facts_are_checked_but_not_drawn() -> None:
    data = page(facts=FACTS)
    assert render.validate(data) == []
    assert "Lakehouse" not in render.render(data)
    broken = {
        **FACTS,
        "version": 2,
        "costs": [{"item": "x", "monthly": "a lot", "currency": "EUR", "as_of": "last week", "source": "memory"}],
        "decisions": [{"title": "no choice"}],
        "open": [1],
    }
    errors = render.validate(page(facts=broken))
    assert "page.facts.version: must be 1" in errors
    assert "page.facts.costs[0].monthly: must be a number" in errors
    assert "page.facts.costs[0].as_of: must be a date, YYYY-MM-DD" in errors
    assert any(e.startswith("page.facts.decisions[0].chosen") for e in errors)
    assert "page.facts.open[0]: must be a string" in errors


def test_the_fields_for_joining_pages_are_optional_and_checked() -> None:
    joined = {
        **FACTS,
        "components": [{"id": "lake", "label": "Lakehouse", "region": "West Europe"}],
        "costs": [
            {
                "item": "x",
                "monthly": 1.0,
                "currency": "EUR",
                "as_of": "2026-11-09",
                "source": "list",
                "cloud": "Azure",
                "variant": "A",
            }
        ],
        "budget": {"monthly": 6000, "currency": "EUR", "source": "brief"},
        "specialists": ["ai-pattern"],
    }
    assert render.validate(page(facts=joined)) == []
    broken = {
        **FACTS,
        "components": [{"id": "lake", "label": "Lakehouse", "region": 1}],
        "costs": [{"item": "x", "monthly": 1.0, "currency": "EUR", "as_of": "2026-11-09", "source": "s", "cloud": 1}],
        "budget": {"monthly": "much", "currency": 1},
        "specialists": [1],
    }
    errors = render.validate(page(facts=broken))
    assert "page.facts.components[0].region: must be a string" in errors
    assert "page.facts.costs[0].cloud: must be a string" in errors
    assert "page.facts.budget.monthly: must be a number" in errors
    assert "page.facts.budget.currency: must be a string" in errors
    assert "page.facts.budget.source: missing" in errors
    assert "page.facts.specialists[0]: must be a string" in errors


def test_a_label_shared_by_links_into_one_box_is_drawn_once() -> None:
    block = {
        "type": "architecture",
        "zones": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        "components": [
            {"id": "one", "label": "One", "zone": "a"},
            {"id": "two", "label": "Two", "zone": "a"},
            {"id": "load", "label": "Load", "zone": "b"},
        ],
        "links": [{"from": "one", "to": "load", "label": "daily"}, {"from": "two", "to": "load", "label": "daily"}],
    }
    html = render.render(with_blocks(block))
    assert html.count(">daily</text>") == 1 and html.count('<path class="link"') == 2


def nested_block() -> dict[str, Any]:
    return {
        "type": "nested",
        "title": "Acme",
        "levels": [
            {"id": "context", "label": "Context", "open": []},
            {"id": "containers", "label": "Containers", "open": ["sys"]},
            {"id": "inside", "label": "Inside the API", "open": ["sys", "api"]},
        ],
        "boxes": [
            {"id": "user", "label": "Clerk", "kind": "user"},
            {"id": "sys", "label": "System"},
            {"id": "web", "label": "Web", "parent": "sys", "kind": "channel", "tech": "Angular"},
            {"id": "api", "label": "API", "parent": "sys", "tech": ".NET", "flag": "warn"},
            {"id": "db", "label": "Database", "parent": "sys", "kind": "store", "tech": "PostgreSQL"},
            {"id": "ctrl", "label": "Controllers", "parent": "api"},
            {"id": "repo", "label": "Repository", "parent": "api"},
            {"id": "mail", "label": "Mail service", "kind": "system"},
        ],
        "links": [
            {"from": "user", "to": "web", "label": "uses"},
            {"from": "web", "to": "ctrl", "label": "JSON"},
            {"from": "ctrl", "to": "repo", "label": "calls"},
            {"from": "repo", "to": "db", "label": "SQL", "flag": "bad"},
            {"from": "ctrl", "to": "mail", "label": "sends"},
        ],
        "flows": [
            {
                "id": "book",
                "title": "Book",
                "variants": ["containers"],
                "steps": [
                    {"from": "web", "to": "api", "text": "Books."},
                    {"from": "api", "to": "db", "text": "Saves."},
                ],
            }
        ],
    }


def svg_of(html: str, level: str) -> str:
    match = re.search(rf'<svg class="arch-svg nested" data-variant="{level}".*?</svg>', html, re.S)
    assert match
    return match.group(0)


def test_a_level_shows_only_what_is_open_and_moves_links_out() -> None:
    block = nested_block()
    assert render.validate(with_blocks(block)) == []
    html = render.render(with_blocks(block))
    context = svg_of(html, "context")
    keys = set(re.findall(r'<g class="comp[^"]*" data-k="([^"]+)"', context))
    assert keys == {"user", "sys", "mail"}
    links = set(re.findall(r'<path class="link[^"]*"[^>]*data-a="([^"]+)" data-b="([^"]+)"', context))
    assert links == {("user", "sys"), ("sys", "mail")}
    containers = svg_of(html, "containers")
    keys = set(re.findall(r'<g class="comp[^"]*" data-k="([^"]+)"', containers))
    assert keys == {"user", "sys", "web", "api", "db", "mail"} and "open-box" in containers
    links = set(re.findall(r'<path class="link[^"]*"[^>]*data-a="([^"]+)" data-b="([^"]+)"', containers))
    assert links == {("user", "web"), ("web", "api"), ("api", "db"), ("api", "mail")}
    inside = svg_of(html, "inside")
    assert {"ctrl", "repo"} <= set(re.findall(r'data-k="([^"]+)"', inside))


def test_a_lifted_link_keeps_the_worst_flag_and_counts_its_labels() -> None:
    block = nested_block()
    block["links"].append({"from": "ctrl", "to": "db", "label": "reads"})
    lifted = render._nest_links(block, render._nest_visible(block, {"sys"}))
    merged = next(link for link in lifted if (link["from"], link["to"]) == ("api", "db"))
    assert merged["flag"] == "bad" and merged["label"] == "SQL +1"


def test_children_sit_inside_their_open_box() -> None:
    html = render.render(with_blocks(nested_block()))
    inside = svg_of(html, "inside")
    rect = {
        m["k"]: tuple(float(m[f]) for f in ("x", "y", "w", "h"))
        for m in re.finditer(
            r'data-k="(?P<k>[^"]+)"[^>]*><title>[^<]*</title><rect class="plate" x="(?P<x>[\d.]+)" y="(?P<y>[\d.]+)" '
            r'width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)"',
            inside,
        )
    }
    for child, parent in (("web", "sys"), ("api", "sys"), ("ctrl", "api"), ("repo", "api")):
        x, y, w, h = rect[child]
        px, py, pw, ph = rect[parent]
        assert px < x and py < y and x + w < px + pw and y + h < py + ph


def test_a_store_stands_under_its_writer_not_in_a_column_of_its_own() -> None:
    block = nested_block()
    block["levels"] = [{"id": "containers", "label": "C", "open": ["sys"]}]
    html = render.render(with_blocks(block))
    rect = dict(re.findall(r'data-k="(api|db)"[^>]*>(?:<title>[^<]*</title>)<rect class="plate" x="([\d.]+)"', html))
    assert rect["api"] == rect["db"]


def test_nested_shares_the_architecture_page() -> None:
    html = render.render(with_blocks(nested_block()))
    assert 'data-set-variant="containers"' in html and 'data-set-flow="book"' in html
    assert html.count('<article class="arch-card plate"') == 8
    assert "only in some variants" not in html
    assert "Top level" in html


def test_without_levels_everything_is_open_in_one_view() -> None:
    block = nested_block()
    del block["levels"]
    block["flows"] = []
    html = render.render(with_blocks(block))
    assert '<button type="button" data-set-variant' not in html
    assert {"ctrl", "repo", "db"} <= set(re.findall(r'data-k="([^"]+)"', html))


def test_nested_references_are_checked() -> None:
    block = nested_block()
    block["boxes"][1]["parent"] = "api"  # sys inside api, api inside sys
    errors = render.validate(with_blocks(block))
    assert any("boxes contain each other" in e for e in errors)
    block = nested_block()
    block["boxes"][2]["parent"] = "ghost"
    block["links"][0]["to"] = "nobody"
    block["levels"][1]["open"] = ["ghost"]
    errors = render.validate(with_blocks(block))
    start = "page.sections[0].blocks[0]"
    assert f"{start}.boxes[2].parent: unknown box id 'ghost'" in errors
    assert f"{start}.links[0].to: unknown box id 'nobody'" in errors
    assert f"{start}.levels[1].open[0]: unknown box id 'ghost'" in errors


def test_a_flow_must_be_visible_at_its_levels() -> None:
    block = nested_block()
    block["flows"][0]["variants"] = ["context"]
    errors = render.validate(with_blocks(block))
    assert any("'web' is not visible at level context" in e for e in errors)


def test_nested_is_escaped_deterministic_and_offline() -> None:
    block = nested_block()
    block["boxes"][1]["label"] = "<img src=x onerror=alert(1)>"
    block["boxes"][3]["details"] = [["<b>", "<script>x</script>"]]
    data = with_blocks(block)
    html = render.render(data)
    assert html == render.render(json.loads(json.dumps(data)))
    assert "<img" not in html and html.count("<script") == 1
    assert set(re.findall(r'https?://[^"\s)]+', html)) <= {"http://www.w3.org/2000/svg"}


# ---------------------------------------------------------------------------- chart

BAR = {
    "type": "chart",
    "kind": "bar",
    "title": "Drivers",
    "unit": "EUR",
    "categories": ["mix: premium", "mix: value", "volume"],
    "series": [{"name": "Effect", "values": [-7488, -3696, 960]}],
}
LINE = {
    "type": "chart",
    "kind": "line",
    "title": "Daily revenue",
    "unit": "EUR",
    "categories": ["10-25", "10-26", "10-27"],
    "series": [{"name": "Revenue", "values": [2900, 3100, 1800]}, {"name": "Target", "values": [3000, 3000, None]}],
}
WATERFALL = {
    "type": "chart",
    "kind": "waterfall",
    "title": "September to October",
    "unit": "EUR",
    "items": [
        {"label": "September", "value": 96000, "total": True},
        {"label": "Volume", "value": 960},
        {"label": "Mix", "value": -11160},
        {"label": "Rate", "value": -410},
        {"label": "October", "value": 85390, "total": True},
    ],
}
HEATMAP = {
    "type": "chart",
    "kind": "heatmap",
    "title": "Cohort retention",
    "unit": "%",
    "rows": ["2026-08", "2026-09"],
    "columns": ["M0", "M1", "M2"],
    "values": [[100, 42.5, 30], [100, 38, None]],
}
CHARTS = [BAR, LINE, WATERFALL, HEATMAP]


def chart_page(*blocks: dict[str, Any]) -> dict[str, Any]:
    return page(sections=[{"title": "Charts", "blocks": list(blocks)}])


@pytest.mark.parametrize("chart", CHARTS, ids=lambda c: c["kind"])
def test_chart_renders_svg_with_a_title_per_mark_and_a_data_table(chart: dict[str, Any]) -> None:
    html = render.render(chart_page(chart))
    assert render.validate(chart_page(chart)) == []
    assert html.count('<svg class="chart-svg"') == 1
    assert "<title>" in html and 'class="chart-data table-wrap"' in html
    # Every drawn mark carries its tooltip, and the data follows as a table.
    assert html.count("<title>") >= 3


def test_every_chart_value_is_escaped_and_nothing_is_fetched() -> None:
    hostile = '<img src=x onerror=alert(1)> "quoted" & </text><script>alert(1)</script>'
    charts = [
        {
            "type": "chart",
            "kind": "bar",
            "title": hostile,
            "unit": hostile,
            "categories": [hostile],
            "series": [{"name": hostile, "values": [1]}],
        },
        {
            "type": "chart",
            "kind": "line",
            "title": hostile,
            "categories": [hostile, "b"],
            "series": [{"name": hostile, "values": [1, 2]}, {"name": "x", "values": [2, 1]}],
        },
        {
            "type": "chart",
            "kind": "waterfall",
            "items": [{"label": hostile, "value": 1, "total": True}, {"label": hostile, "value": 1}],
        },
        {
            "type": "chart",
            "kind": "heatmap",
            "rows": [hostile],
            "columns": [hostile],
            "values": [[1]],
        },
    ]
    html = render.render(chart_page(*charts))
    assert "<img" not in html and "<script>alert" not in html
    assert set(re.findall(r'https?://[^"\s)]+', html)) <= {"http://www.w3.org/2000/svg"}


def test_the_same_chart_json_gives_the_same_html() -> None:
    first = render.render(chart_page(*CHARTS))
    second = render.render(json.loads(json.dumps(chart_page(*CHARTS))))
    assert first == second


def test_chart_table_lists_the_data() -> None:
    html = render.render(chart_page(WATERFALL))
    table = html[html.index('class="chart-data table-wrap"') :]
    assert "96,000 EUR" in table and "\u221211,160 EUR" in table and "85,390 EUR" in table
    heat = render.render(chart_page(HEATMAP))
    table = heat[heat.index('class="chart-data table-wrap"') :]
    assert "42.50%" in table and "<td" in table


def test_bar_marks_are_thin_and_a_series_of_negatives_starts_at_the_baseline() -> None:
    html = render.render(chart_page(BAR))
    assert 'class="bar cs0"' in html and "Q" in re.search(r'class="bar cs0" d="([^"]+)"', html).group(1)  # type: ignore[union-attr]


def test_line_has_a_legend_for_two_series_and_none_for_one() -> None:
    assert '<span class="legend-item"><i class="swatch sw-cs0">' in render.render(chart_page(LINE))
    one = {"type": "chart", "kind": "line", "categories": ["a", "b"], "series": [{"name": "A", "values": [1, 2]}]}
    assert "legend-item" not in render.render(chart_page(one)).split("</style>", 1)[1]


def test_line_axis_starts_at_zero_unless_told_and_then_says_so() -> None:
    assert "axis does not start at zero" not in render.render(chart_page(LINE))
    relaxed = {**LINE, "zero": False}
    assert "axis does not start at zero" in render.render(chart_page(relaxed))


def test_waterfall_totals_must_add_up() -> None:
    wrong = {
        "type": "chart",
        "kind": "waterfall",
        "items": [
            {"label": "A", "value": 100, "total": True},
            {"label": "x", "value": -10},
            {"label": "B", "value": 95, "total": True},
        ],
    }
    errors = render.validate(chart_page(wrong))
    assert any("blocks[0].items[2].value" in e and "running sum" in e for e in errors)


def test_heatmap_scale_colours_low_to_high() -> None:
    html = render.render(chart_page(HEATMAP))
    assert 'class="heat h0"' in html and 'class="heat h5"' in html
    assert 'class="heat-empty"' in html  # null cell has no fill


@pytest.mark.parametrize(
    ("chart", "error"),
    [
        ({"type": "chart"}, "blocks[0].kind: must be one of"),
        ({"type": "chart", "kind": "pie"}, "blocks[0].kind: must be one of"),
        ({"type": "chart", "kind": "bar", "categories": ["a"], "series": []}, "blocks[0].series: from 1"),
        (
            {"type": "chart", "kind": "bar", "categories": ["a"], "series": [{"name": "s", "values": [1, 2]}]},
            "blocks[0].series[0].values: must have one value per category",
        ),
        (
            {"type": "chart", "kind": "bar", "categories": ["a"], "series": [{"name": "s", "values": ["x"]}]},
            "blocks[0].series[0].values[0]: must be a number or null",
        ),
        (
            {"type": "chart", "kind": "line", "categories": ["a"], "series": [{"name": "s", "values": [1]}], "zero": 1},
            "blocks[0].zero",
        ),
        (
            {"type": "chart", "kind": "waterfall", "items": [{"label": "a", "value": 1}]},
            "blocks[0].items: at least two steps",
        ),
        (
            {"type": "chart", "kind": "heatmap", "rows": ["a"], "columns": ["b", "c"], "values": [[1]]},
            "blocks[0].values[0]: must have one value per column",
        ),
    ],
)
def test_chart_errors_name_their_path(chart: dict[str, Any], error: str) -> None:
    assert any(error in e for e in render.validate(chart_page(chart))), render.validate(chart_page(chart))


def test_a_page_without_a_chart_has_no_chart_markup() -> None:
    html = render.render(page())
    assert 'class="chart' not in html.split("</style>")[1]
