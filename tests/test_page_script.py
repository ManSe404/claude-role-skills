"""The page script, run in a real browser: click-to-trace, the table filter and the copy button.

Skipped when no Chrome or Chromium is installed. The harness clicks and types after the page
script has run, then writes what it saw into the DOM, which headless Chrome dumps.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT, load

render = load(ROOT / "shared" / "render_page.py")
CHROME = next((c for c in ("google-chrome", "chromium", "chromium-browser") if shutil.which(c)), None)

HARNESS = """
<script>
(function () {
  function cls(sel) { return Array.prototype.map.call(document.querySelectorAll(sel), function (e) {
    return e.getAttribute("class"); }); }
  var out = {};
  document.querySelector('.node[data-k="b"]').dispatchEvent(new MouseEvent("click", {bubbles: true}));
  out.nodes = cls("svg.graph .node");
  out.edges = cls("svg.graph .edge");
  out.hash = location.hash;
  out.hint = (document.querySelector(".legend .hint") || {}).textContent;
  document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape"}));
  out.cleared = cls("svg.graph .node");
  var input = document.querySelector(".filter input");
  input.value = "row 1";
  input.dispatchEvent(new Event("input"));
  var rows = document.querySelector(".filter").nextElementSibling.querySelectorAll("tbody tr");
  out.visible = Array.prototype.filter.call(rows, function (r) {
    return !r.hidden; }).length;
  out.count = document.querySelector(".filter .count").textContent;
  out.copy = (document.querySelector("figure.code .copy") || {}).textContent;
  var pre = document.createElement("pre");
  pre.id = "result";
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
})();
</script>
"""


def page() -> dict[str, Any]:
    graph = {
        "type": "graph",
        "nodes": [{"id": k, "label": k.upper()} for k in "abcde"],
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "c"},
            {"from": "c", "to": "d"},
            {"from": "e", "to": "d"},
        ],
    }
    table = {"type": "table", "columns": ["Name"], "rows": [[f"row {i}"] for i in range(12)]}
    code = {"type": "code", "code": "def f():\\n    return 1"}
    return {"skill": "impact", "title": "T", "sections": [{"title": "S", "blocks": [graph, table, code]}]}


@pytest.mark.skipif(CHROME is None, reason="needs Chrome or Chromium")
def test_trace_filter_and_copy_in_a_browser(tmp_path: Path) -> None:
    html = render.render(page()).replace("</body>", HARNESS + "</body>")
    target = tmp_path / "page.html"
    target.write_text(html, encoding="utf-8")
    assert CHROME is not None
    done = subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--user-data-dir={tmp_path / 'profile'}",
            "--virtual-time-budget=2000",
            "--dump-dom",
            target.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    match = re.search(r'<pre id="result">(.*?)</pre>', done.stdout, re.S)
    assert match, done.stderr[-2000:]
    out = json.loads(match.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    # b is selected; a leads to it; c and d are what it reaches; e only feeds d, so it fades.
    assert [c.split()[-1] for c in out["nodes"]] == ["on-up", "sel", "on-down", "on-down", "off"]
    assert [c.split()[-1] for c in out["edges"]] == ["on-up", "on-down", "on-down", "off"]
    assert out["hash"] == "#node=b"
    assert out["hint"] == "Click a node to trace it · Esc clears"
    assert all(c.split()[-1] not in ("sel", "on-up", "on-down", "off") for c in out["cleared"])
    assert (out["visible"], out["count"]) == (3, "3 of 12")  # row 1, row 10, row 11
    assert out["copy"] == "Copy"


ARCH_HARNESS = """
<script>
(function () {
  function q(sel) { return document.querySelector(sel); }
  function keys(sel, attr) {
    return Array.prototype.map.call(document.querySelectorAll(sel), function (e) { return e.getAttribute(attr); });
  }
  var out = {};
  out.js = document.documentElement.classList.contains("js");
  out.deep = {
    pressed: q('button[data-set-variant="fixed"]').getAttribute("aria-pressed"),
    now: q('.arch-flow.open li.now').getAttribute("data-b"),
    caption: q(".arch-caption").textContent,
    staffGone: q('.comp[data-k="staff"]').classList.contains("gone")
  };
  q('.comp[data-k="agent"]').dispatchEvent(new MouseEvent("click", {bubbles: true}));
  out.cards = keys(".arch-card.open", "data-k");
  out.sends = keys("path.link.out", "data-b");
  out.hashComp = location.hash;
  q('button[data-set-variant="now"]').click();
  out.staffGoneNow = q('.comp[data-k="staff"]').classList.contains("gone");
  out.sendsNow = keys("path.link.out", "data-b");
  q(".arch-trust").click();
  out.risk = keys(".comp.risk", "data-k");
  out.hashTrust = location.hash;
  q('button[data-set-flow="ask"]').click();
  document.dispatchEvent(new KeyboardEvent("keydown", {key: "ArrowRight"}));
  out.count = q(".stepper .count").textContent;
  out.hot = Array.prototype.map.call(document.querySelectorAll("path.link.hot"), function (e) {
    return e.getAttribute("data-a") + ">" + e.getAttribute("data-b"); });
  document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape"}));
  out.cleared = !q(".arch").classList.contains("focus") && !q(".arch-flow.open");
  var pre = document.createElement("pre");
  pre.id = "result";
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
})();
</script>
"""


@pytest.mark.skipif(CHROME is None, reason="needs Chrome or Chromium")
def test_architecture_panel_flow_variant_and_trust_in_a_browser(tmp_path: Path) -> None:
    from test_render_page import arch_block

    data = {"skill": "ai-architecture", "title": "T", "sections": [{"title": "S", "blocks": [arch_block()]}]}
    html = render.render(data).replace("</body>", ARCH_HARNESS + "</body>")
    target = tmp_path / "page.html"
    target.write_text(html, encoding="utf-8")
    assert CHROME is not None
    done = subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--user-data-dir={tmp_path / 'profile'}",
            "--virtual-time-budget=2000",
            "--dump-dom",
            target.as_uri() + "#variant=fixed&flow=ask&step=2",
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    match = re.search(r'<pre id="result">(.*?)</pre>', done.stdout, re.S)
    assert match, done.stderr[-2000:]
    out = json.loads(match.group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&gt;", ">"))
    assert out["js"] is True
    # The link opened the reviewed variant at step 2 of the flow.
    assert out["deep"] == {
        "pressed": "true",
        "now": "fetch",
        "caption": "2. Agent loop → fetch_url · Fetches a page.",
        "staffGone": False,
    }
    assert out["cards"] == ["agent"] and out["sends"] == ["fetch", "staff"]
    assert out["hashComp"] == "#variant=fixed&component=agent"
    assert out["staffGoneNow"] is True and out["sendsNow"] == ["fetch", "mail"]
    assert out["risk"] == ["mail"] and out["hashTrust"] == "#component=agent&trust=1"
    assert out["count"] == "2 / 2" and out["hot"] == ["agent>fetch"]
    assert out["cleared"] is True


MODEL_HARNESS = """
<script>
(function () {
  function q(sel) { return document.querySelector(sel); }
  function keys(sel, attr) {
    return Array.prototype.map.call(document.querySelectorAll(sel), function (e) { return e.getAttribute(attr); });
  }
  var out = {};
  out.deepCards = keys(".model-card.open", "data-k");
  out.deepArea = q('button[data-set-area="stock"]').getAttribute("aria-pressed");
  q('button[data-set-area="stock"]').click();
  out.hashNoArea = location.hash;
  q('.tbl[data-k="cust"]').dispatchEvent(new MouseEvent("click", {bubbles: true}));
  out.cards = keys(".model-card.open", "data-k");
  out.near = keys(".tbl.near", "data-k");
  out.on = keys("path.rel.on", "data-a");
  out.hashTable = location.hash;
  document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape"}));
  out.cleared = keys(".model-card.open", "data-k").length === 0 && !q(".model").classList.contains("focus");
  q('button[data-set-area="stock"]').click();
  out.outside = keys(".tbl.out", "data-k");
  var pre = document.createElement("pre");
  pre.id = "result";
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
})();
</script>
"""

REACH_HARNESS = """
<script>
(function () {
  function q(sel) { return document.querySelector(sel); }
  function keys(sel, attr) {
    return Array.prototype.map.call(document.querySelectorAll(sel), function (e) { return e.getAttribute(attr); });
  }
  var out = {};
  out.deep = q(".arch").classList.contains("reach");
  out.hit = keys(".comp.rhit", "data-k").filter(function (k, i, a) { return a.indexOf(k) === i; }).sort();
  out.path = keys("path.link.rpath", "data-b");
  q(".arch-trust").click();
  out.reachOff = !q(".arch").classList.contains("reach") && q(".arch").classList.contains("trust");
  q(".arch-reach").click();
  out.trustOff = !q(".arch").classList.contains("trust") && q(".arch").classList.contains("reach");
  out.hash = location.hash;
  var pre = document.createElement("pre");
  pre.id = "result";
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
})();
</script>
"""


def browser(tmp_path: Path, html: str, fragment: str) -> dict[str, Any]:
    target = tmp_path / "page.html"
    target.write_text(html, encoding="utf-8")
    assert CHROME is not None
    done = subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--user-data-dir={tmp_path / 'profile'}",
            "--virtual-time-budget=2000",
            "--dump-dom",
            target.as_uri() + fragment,
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    match = re.search(r'<pre id="result">(.*?)</pre>', done.stdout, re.S)
    assert match, done.stderr[-2000:]
    result: dict[str, Any] = json.loads(
        match.group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&gt;", ">")
    )
    return result


@pytest.mark.skipif(CHROME is None, reason="needs Chrome or Chromium")
def test_model_card_neighbours_and_area_filter_in_a_browser(tmp_path: Path) -> None:
    from test_render_page import model_block

    data = {"skill": "data-model", "title": "T", "sections": [{"title": "S", "blocks": [model_block()]}]}
    html = render.render(data).replace("</body>", MODEL_HARNESS + "</body>")
    out = browser(tmp_path, html, "#area=stock&table=fct")
    assert out["deepCards"] == ["fct"] and out["deepArea"] == "true"
    assert out["hashNoArea"] == "#table=fct"
    assert out["cards"] == ["cust"] and out["near"] == ["fct"] and out["on"] == ["fct"]
    assert out["hashTable"] == "#table=cust"
    assert out["cleared"] is True
    assert out["outside"] == ["fct", "cust"] or sorted(out["outside"]) == ["cust", "fct"]


@pytest.mark.skipif(CHROME is None, reason="needs Chrome or Chromium")
def test_reach_view_in_a_browser(tmp_path: Path) -> None:
    from test_render_page import reach_block

    data = {"skill": "data-map", "title": "T", "sections": [{"title": "S", "blocks": [reach_block()]}]}
    html = render.render(data).replace("</body>", REACH_HARNESS + "</body>")
    out = browser(tmp_path, html, "#reach=1")
    assert out["deep"] is True
    assert out["hit"] == ["fetch", "mail"]
    assert sorted(out["path"]) == ["agent", "fetch", "mail"] or "mail" in out["path"]
    assert out["reachOff"] is True and out["trustOff"] is True
    assert out["hash"] == "#reach=1"


NESTED_HARNESS = """
<script>
(function () {
  function q(sel) { return document.querySelector(sel); }
  var out = {};
  out.deep = q("svg.arch-svg.on").getAttribute("data-variant");
  q('button[data-set-variant="inside"]').click();
  out.level = q("svg.arch-svg.on").getAttribute("data-variant");
  q('svg.arch-svg.on .comp[data-k="ctrl"]').dispatchEvent(new MouseEvent("click", {bubbles: true}));
  out.card = q(".arch-card.open").getAttribute("data-k");
  out.hash = location.hash;
  q('button[data-set-variant="containers"]').click();
  q('button[data-set-flow="book"]').click();
  out.count = q(".stepper .count").textContent;
  var pre = document.createElement("pre");
  pre.id = "result";
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
})();
</script>
"""


@pytest.mark.skipif(CHROME is None, reason="needs Chrome or Chromium")
def test_nested_levels_cards_and_flows_in_a_browser(tmp_path: Path) -> None:
    from test_render_page import nested_block

    data = {"skill": "arch-c4", "title": "T", "sections": [{"title": "S", "blocks": [nested_block()]}]}
    html = render.render(data).replace("</body>", NESTED_HARNESS + "</body>")
    out = browser(tmp_path, html, "#variant=containers")
    assert out["deep"] == "containers" and out["level"] == "inside"
    assert out["card"] == "ctrl" and out["hash"] == "#variant=inside&component=ctrl"
    assert out["count"] == "1 / 2"
