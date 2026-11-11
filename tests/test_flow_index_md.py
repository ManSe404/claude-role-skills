from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT, load

render = load(ROOT / "shared" / "render_page.py")


def page(*blocks: dict[str, Any], **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "skill": "arch-evolve",
        "title": "The way there",
        "sections": [{"title": "Path", "blocks": list(blocks)}],
    }
    base.update(extra)
    return base


def flow_block() -> dict[str, Any]:
    return {
        "type": "flowchart",
        "title": "Steps and checks",
        "nodes": [
            {"id": "s", "kind": "start", "label": "Pin behaviour"},
            {"id": "p", "label": "Proxy", "note": "two instances"},
            {"id": "d", "kind": "decision", "label": "Healthy?"},
            {"id": "e", "kind": "end", "label": "Remove the old path"},
        ],
        "edges": [
            {"from": "s", "to": "p"},
            {"from": "p", "to": "d"},
            {"from": "d", "to": "e", "label": "yes"},
            {"from": "d", "to": "p", "label": "no"},
        ],
    }


# ---------------------------------------------------------------------------- flowchart


def test_a_flowchart_draws_each_kind_in_its_shape() -> None:
    html = render.render(page(flow_block()))
    plates = {
        m["k"]: m["d"]
        for m in re.finditer(
            r'class="node f-(?P<kind>\w+)" data-k="(?P<k>\w+)"[^>]*>.*?<path class="plate"[^>]*d="(?P<d>[^"]+)"', html
        )
    }
    assert set(plates) == {"s", "p", "d", "e"}
    assert "A" in plates["s"] and "A" in plates["e"]  # capsules have arcs
    assert "A" not in plates["p"] and "A" not in plates["d"]  # cells have straight edges
    node = {"id": "d", "label": "Healthy?"}
    assert render._node_box({**node, "kind": "decision"}, True)[0] > render._node_box(node, True)[0]  # deep points
    assert render._node_box({**node, "kind": "start"}, True)[0] > render._node_box(node, True)[0]  # round ends
    assert 'class="edge dim back"' in html  # "no" goes back to the proxy
    assert "The flowchart as a list · 4 links" in html
    for kind in ("start", "step", "decision", "end"):
        assert f'<i class="swatch f-{kind}"></i>{kind}' in html


def test_a_flowchart_is_checked_like_a_graph() -> None:
    block = {
        "type": "flowchart",
        "nodes": [{"id": "a", "label": "A", "kind": "loop"}],
        "edges": [{"from": "a", "to": "b"}],
    }
    errors = render.validate(page(block))
    assert "page.sections[0].blocks[0].nodes[0].kind: must be one of start, step, decision, end" in errors
    assert "page.sections[0].blocks[0].edges[0].to: unknown node id 'b'" in errors


# ---------------------------------------------------------------------------- markdown


def every_block_page() -> dict[str, Any]:
    return page(
        {"type": "text", "text": "Plain `code` and **bold**."},
        {"type": "callout", "tone": "warn", "text": "Mind the gap."},
        {"type": "list", "items": ["one", "two"], "ordered": True},
        {"type": "table", "title": "Numbers", "columns": ["Thing", "Count"], "rows": [["a | b", 1200], ["c", 2.5]]},
        {"type": "kv", "items": [["Repo", "acme"], ["Lines", 387]]},
        {"type": "code", "where": "src/x.py:12", "code": "x = 1\ny = 2\n"},
        {"type": "steps", "items": [{"title": "Start", "where": "cli.py:3", "text": "Runs first."}]},
        {
            "type": "findings",
            "items": [
                {"severity": "low", "title": "Small", "evidence": "e"},
                {"severity": "high", "title": "Big", "where": "a.py:1", "evidence": "Seen.", "fix": "Do it."},
            ],
        },
        flow_block(),
        {
            "type": "chart",
            "kind": "bar",
            "title": "By driver",
            "unit": "EUR",
            "categories": ["Mix", "Volume"],
            "series": [{"name": "Effect", "values": [-7488, 960]}],
        },
        {
            "type": "decision",
            "factors": ["Team"],
            "options": [
                {
                    "label": "One deployable",
                    "status": "eliminated",
                    "eliminated_by": "Rule 2",
                    "cells": [{"rating": "fail", "text": "no"}],
                },
                {"label": "Services", "status": "chosen", "cells": [{"rating": "pass", "text": "yes"}]},
            ],
        },
        verdict={"text": "Go, in steps.", "tone": "ok"},
        stats=[{"label": "Steps", "value": 12, "note": "two optional"}],
        meta={"repo": "acme", "date": "2026-11-11"},
    )


def test_the_markdown_note_carries_every_block() -> None:
    md = render.render_markdown(every_block_page())
    assert md.startswith("# The way there\n")
    assert "`arch-evolve` · repo acme · date 2026-11-11" in md
    assert "> **Verdict (ok):** Go, in steps." in md
    assert "| Steps | 12 | two optional |" in md
    assert "## 1. Path" in md
    assert "> **watch:** Mind the gap." in md
    assert "1. one\n2. two" in md
    assert "### Numbers\n\n| Thing | Count |\n|---|---|\n| a \\| b | 1,200 |\n| c | 2.5 |" in md
    assert "- **Repo:** acme\n- **Lines:** 387" in md
    assert "`src/x.py:12`\n\n```\nx = 1\ny = 2\n```" in md
    assert "1. **Start** — `cli.py:3`\n   Runs first." in md
    assert md.index("**HIGH · Big** — `a.py:1`") < md.index("**LOW · Small**")  # high first
    assert "*Fix:* Do it." in md
    assert "| Healthy? | Remove the old path | yes |" in md
    assert "*bar chart; the drawing is on the page.*\n\n| Driver" not in md  # the x label is not set
    assert "*bar chart; the drawing is on the page.*" in md and "| Mix | " in md and "7,488" in md
    assert "| Option | Team | Status |" in md and "| **Services** | pass: yes | chosen |" in md
    assert "eliminated by Rule 2" in md
    assert md.rstrip().endswith("claims tagged high (checked), med (likely), guess (not checked)*")


def test_md_writes_a_note_beside_the_json(tmp_path: Path) -> None:
    source = tmp_path / "p.json"
    source.write_text(json.dumps(page({"type": "text", "text": "Hi."})), encoding="utf-8")
    assert render.main([str(source), "--md"]) == 0
    assert (tmp_path / "p.md").read_text(encoding="utf-8").startswith("# The way there")
    assert not (tmp_path / "p.html").exists()


# ---------------------------------------------------------------------------- index


def write_page(path: Path, title: str, **extra: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(page({"type": "text", "text": "Hi."}, title=title, **extra)), encoding="utf-8")


def test_the_index_lists_every_page_under_the_folder(tmp_path: Path) -> None:
    write_page(
        tmp_path / "a" / "x.json",
        "Alpha page",
        meta={"date": "2026-11-10"},
        verdict={"text": "Fine `so` far", "tone": "ok"},
    )
    write_page(tmp_path / "b dir" / "y.json", "Beta page")
    (tmp_path / "b dir" / "y.md").write_text("# Beta page\n", encoding="utf-8")  # a note, no page beside it
    (tmp_path / "b dir" / "site.json").write_text(
        '{"title": "B", "pages": [{"label": "Y", "page": "y.json"}]}', encoding="utf-8"
    )
    (tmp_path / "c" / "other.json").parent.mkdir()
    (tmp_path / "c" / "other.json").write_text('{"not": "a page"}', encoding="utf-8")
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "bad.json").write_text('{"skill": "x", "title": "Broken page", "sections": []}', encoding="utf-8")
    assert render.main(["--index", str(tmp_path)]) == 0
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '<a href="a/x.html">Alpha page</a>' in html
    assert '<a href="b%20dir/y.md">Beta page</a>' in html  # the note, since there is no page
    assert "<strong>ok</strong> Fine so far" in html
    assert "other" not in html and "Broken page" not in html
    assert html.index("Beta page") < html.index("Alpha page")  # the undated page is newer: today
    assert f"<title>{tmp_path.name}</title>" in html


def test_the_index_is_checked_without_writing(tmp_path: Path) -> None:
    write_page(tmp_path / "x.json", "X")
    assert render.main(["--index", str(tmp_path), "--check"]) == 0
    assert not (tmp_path / "index.html").exists()


@pytest.mark.parametrize(
    "argv", [["--index", "x", "-o", "y"], ["--index", "x", "--md"], ["--site", "s.json", "--index", "x"], []]
)
def test_the_index_refuses_mixed_options(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        render.main(argv)
    assert stopped.value.code == 2
