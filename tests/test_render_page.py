from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT, SKILLS, load

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
    assert "<script" not in html and "<img" not in html and "<svg onload" not in html
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
    assert "<script" not in html and "<link" not in html
    assert set(re.findall(r'https?://[^"\s)]+', html)) <= {"http://www.w3.org/2000/svg"}


def test_the_design_is_dark_and_the_fonts_are_inlined() -> None:
    css = render.CSS
    assert css.count("{") == css.count("}")
    assert "color-scheme:dark" in css and "--ground:#080513" in css
    html = render.render(page())
    assert html.count("src:url(data:font/woff2;base64,") == 4
    assert "unicode-range:U+0100-02BA" in html  # latin-ext: č ć š ž đ


@pytest.mark.parametrize("skill", sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").exists()))
def test_each_example_page_is_valid(skill: str, tmp_path: Path) -> None:
    example = SKILLS / skill / "references" / "example.json"
    assert example.is_file(), f"{skill} has no references/example.json"
    data = json.loads(example.read_text(encoding="utf-8"))
    assert render.validate(data) == []
    assert data["skill"] == skill
    out = tmp_path / "page.html"
    assert render.main([str(example), "-o", str(out)]) == 0
    assert out.stat().st_size < 400_000  # ~200 KB of it are the inlined fonts
