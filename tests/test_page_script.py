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
