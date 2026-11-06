#!/usr/bin/env python3
"""Render a skill's page JSON into one self-contained HTML file.

The skill decides the content and writes it as JSON (the format is in references/page-format.md).
This script only draws it, so every page of every skill has the same layout, every value is
escaped, and nothing in the page is fetched from the network. Standard library only.

Usage:
    python3 render_page.py PAGE.json -o PAGE.html   # write the page
    python3 render_page.py PAGE.json --check        # validate only

The fonts (Bricolage Grotesque, JetBrains Mono, SIL OFL 1.1) are read from ../assets/fonts and
inlined, so the page is one file; without them it falls back to system fonts.

Single source: shared/render_page.py in claude-role-skills. The copies under each skill's
scripts/ and assets/ are written by tools/sync_shared.py; edit the shared files, never a copy.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

# JSON input is untyped by nature; validate() checks every shape before anything is rendered.
Json = Any

SEVERITIES = ("high", "medium", "low", "info")
TONES = ("ok", "warn", "bad", "info")
STATUSES = ("open", "accepted", "declined", "fixed")
GROUPS = {
    "entry": "entry point",
    "module": "module",
    "boundary": "public surface",
    "data": "data store",
    "external": "outside the repo",
    "test": "test",
    "changed": "the change",
    "affected": "needs a change",
    "safe": "safe",
    "unknown": "not checked",
}
BLOCK_TYPES = ("text", "list", "table", "findings", "code", "graph", "steps", "kv", "callout")
CONFIDENCE = ("high", "med", "guess")


# ---------------------------------------------------------------------------- validation


def _str(obj: Json, key: str, path: str, errs: list[str], *, required: bool = True) -> None:
    if key not in obj:
        if required:
            errs.append(f"{path}.{key}: missing")
    elif not isinstance(obj[key], str):
        errs.append(f"{path}.{key}: must be a string")


def _list(obj: Json, key: str, path: str, errs: list[str], *, required: bool = True) -> list[Json]:
    if key not in obj:
        if required:
            errs.append(f"{path}.{key}: missing")
        return []
    value = obj[key]
    if not isinstance(value, list):
        errs.append(f"{path}.{key}: must be a list")
        return []
    return value


def _cell_ok(value: Json) -> bool:
    return value is None or (isinstance(value, (str, int, float)) and not isinstance(value, bool))


def _validate_block(block: Json, path: str, errs: list[str], node_ids: set[str]) -> None:
    if not isinstance(block, dict):
        errs.append(f"{path}: must be an object")
        return
    kind = block.get("type")
    if kind not in BLOCK_TYPES:
        errs.append(f"{path}.type: must be one of {', '.join(BLOCK_TYPES)}")
        return
    if kind in ("text", "callout"):
        _str(block, "text", path, errs)
        if kind == "callout" and block.get("tone", "info") not in TONES:
            errs.append(f"{path}.tone: must be one of {', '.join(TONES)}")
    elif kind == "list":
        for i, item in enumerate(_list(block, "items", path, errs)):
            if not isinstance(item, str):
                errs.append(f"{path}.items[{i}]: must be a string")
    elif kind == "table":
        columns = _list(block, "columns", path, errs)
        if not all(isinstance(c, str) for c in columns):
            errs.append(f"{path}.columns: must be strings")
        for i, row in enumerate(_list(block, "rows", path, errs)):
            if not isinstance(row, list) or len(row) != len(columns):
                errs.append(f"{path}.rows[{i}]: must be a list of {len(columns)} cells")
            elif not all(_cell_ok(c) for c in row):
                errs.append(f"{path}.rows[{i}]: cells must be strings, numbers or null")
        align = block.get("align")
        if align is not None and (
            not isinstance(align, list)
            or len(align) != len(columns)
            or any(a not in ("left", "right", "center") for a in align)
        ):
            errs.append(f"{path}.align: must list left/right/center once per column")
    elif kind == "findings":
        for i, item in enumerate(_list(block, "items", path, errs)):
            ipath = f"{path}.items[{i}]"
            if not isinstance(item, dict):
                errs.append(f"{ipath}: must be an object")
                continue
            _str(item, "title", ipath, errs)
            if item.get("severity") not in SEVERITIES:
                errs.append(f"{ipath}.severity: must be one of {', '.join(SEVERITIES)}")
            if item.get("status", "open") not in STATUSES:
                errs.append(f"{ipath}.status: must be one of {', '.join(STATUSES)}")
            for key in ("where", "evidence", "fix", "reason"):
                _str(item, key, ipath, errs, required=False)
            if item.get("status") == "declined" and not item.get("reason"):
                errs.append(f"{ipath}.reason: a declined finding keeps the reason it was declined")
    elif kind == "code":
        _str(block, "code", path, errs)
        _str(block, "where", path, errs, required=False)
        start = block.get("start", 1)
        if not isinstance(start, int) or isinstance(start, bool) or start < 1:
            errs.append(f"{path}.start: must be a positive integer")
        marks = block.get("highlight", [])
        if not isinstance(marks, list) or not all(isinstance(m, int) and not isinstance(m, bool) for m in marks):
            errs.append(f"{path}.highlight: must be a list of line numbers")
    elif kind == "graph":
        ids: set[str] = set()
        for i, node in enumerate(_list(block, "nodes", path, errs)):
            npath = f"{path}.nodes[{i}]"
            if not isinstance(node, dict):
                errs.append(f"{npath}: must be an object")
                continue
            _str(node, "id", npath, errs)
            _str(node, "label", npath, errs)
            _str(node, "note", npath, errs, required=False)
            if node.get("group", "module") not in GROUPS:
                errs.append(f"{npath}.group: must be one of {', '.join(GROUPS)}")
            if isinstance(node.get("id"), str):
                if node["id"] in ids:
                    errs.append(f"{npath}.id: duplicate id {node['id']!r}")
                ids.add(node["id"])
        for i, edge in enumerate(_list(block, "edges", path, errs)):
            epath = f"{path}.edges[{i}]"
            if not isinstance(edge, dict):
                errs.append(f"{epath}: must be an object")
                continue
            for key in ("from", "to"):
                if edge.get(key) not in ids:
                    errs.append(f"{epath}.{key}: unknown node id {edge.get(key)!r}")
            _str(edge, "label", epath, errs, required=False)
        node_ids.update(ids)
    elif kind == "steps":
        for i, item in enumerate(_list(block, "items", path, errs)):
            ipath = f"{path}.items[{i}]"
            if not isinstance(item, dict):
                errs.append(f"{ipath}: must be an object")
                continue
            _str(item, "title", ipath, errs)
            _str(item, "text", ipath, errs, required=False)
            _str(item, "where", ipath, errs, required=False)
    elif kind == "kv":
        for i, item in enumerate(_list(block, "items", path, errs)):
            if not isinstance(item, list) or len(item) != 2 or not all(_cell_ok(c) for c in item):
                errs.append(f"{path}.items[{i}]: must be a [label, value] pair")
    _str(block, "title", path, errs, required=False)


def validate(page: Json) -> list[str]:
    """Return every problem with the page JSON; an empty list means it can be rendered."""
    errs: list[str] = []
    if not isinstance(page, dict):
        return ["page: must be a JSON object"]
    _str(page, "skill", "page", errs)
    _str(page, "title", "page", errs)
    _str(page, "subtitle", "page", errs, required=False)
    meta = page.get("meta", {})
    if not isinstance(meta, dict) or not all(isinstance(k, str) and _cell_ok(v) for k, v in meta.items()):
        errs.append("page.meta: must be an object of label: value")
    verdict = page.get("verdict")
    if verdict is not None:
        if not isinstance(verdict, dict):
            errs.append("page.verdict: must be an object")
        else:
            _str(verdict, "text", "page.verdict", errs)
            if verdict.get("tone", "info") not in TONES:
                errs.append(f"page.verdict.tone: must be one of {', '.join(TONES)}")
    for i, stat in enumerate(_list(page, "stats", "page", errs, required=False)):
        spath = f"page.stats[{i}]"
        if not isinstance(stat, dict):
            errs.append(f"{spath}: must be an object")
            continue
        _str(stat, "label", spath, errs)
        if not _cell_ok(stat.get("value")) or stat.get("value") is None:
            errs.append(f"{spath}.value: must be a string or a number")
        _str(stat, "note", spath, errs, required=False)
        if stat.get("tone", "info") not in TONES:
            errs.append(f"{spath}.tone: must be one of {', '.join(TONES)}")
    sections = _list(page, "sections", "page", errs)
    if not sections:
        errs.append("page.sections: at least one section")
    seen: set[str] = set()
    node_ids: set[str] = set()
    for i, section in enumerate(sections):
        spath = f"page.sections[{i}]"
        if not isinstance(section, dict):
            errs.append(f"{spath}: must be an object")
            continue
        _str(section, "title", spath, errs)
        _str(section, "intro", spath, errs, required=False)
        sid = section.get("id") or _slug(str(section.get("title", "")))
        if sid in seen:
            errs.append(f"{spath}.id: duplicate section id {sid!r}")
        seen.add(sid)
        for j, block in enumerate(_list(section, "blocks", spath, errs)):
            _validate_block(block, f"{spath}.blocks[{j}]", errs, node_ids)
    return errs


# ---------------------------------------------------------------------------- inline text


def _esc(value: Json) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


_INLINE = re.compile(
    r"`(?P<code>[^`]+)`"
    r"|\*\*(?P<bold>[^*]+)\*\*"
    r"|\[(?P<tag>high|med|guess)\]"
    r"|\[(?P<label>[^\]]+)\]\((?P<url>[^)\s]+)\)"
)
_SAFE_URL = re.compile(r"^(https?://|#|\./|\.\./|/)|^[\w.~-]+(/[\w.~%-]*)*(#[\w-]*)?$")


def _inline(text: str) -> str:
    """Escape text, then allow `code`, **bold**, [high]/[med]/[guess] tags and [label](url) links."""
    out: list[str] = []
    pos = 0
    for m in _INLINE.finditer(text):
        out.append(_esc(text[pos : m.start()]))
        if m.group("code") is not None:
            out.append(f"<code>{_esc(m.group('code'))}</code>")
        elif m.group("bold") is not None:
            out.append(f"<strong>{_esc(m.group('bold'))}</strong>")
        elif m.group("tag") is not None:
            tag = m.group("tag")
            out.append(f'<span class="tag tag-{tag}" title="confidence: {tag}">{tag}</span>')
        else:
            url = m.group("url")
            if _SAFE_URL.match(url) and not url.lower().startswith("javascript"):
                out.append(f'<a href="{_esc(url)}">{_esc(m.group("label"))}</a>')
            else:
                out.append(_esc(m.group(0)))
        pos = m.end()
    out.append(_esc(text[pos:]))
    return "".join(out)


def _paragraphs(text: str) -> str:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "".join(f"<p>{_inline(p).replace(chr(10), '<br>')}</p>" for p in parts)


# ---------------------------------------------------------------------------- graph layout

NODE_H = 40
NOTE_H = 17
CHAR_W = 8.45  # JetBrains Mono at 14px
NOTE_CHAR_W = 7.25  # JetBrains Mono at 12px
COL_GAP = 84
ROW_GAP = 16
PAD = 24
MAX_LABEL = 38

# Where each node group sits in the palette: the focal change in purple, what it reaches in orange.


def _clip(text: str, limit: int = MAX_LABEL) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _node_box(node: Json) -> tuple[float, float]:
    label = _clip(node["label"])
    note = _clip(node.get("note", ""), 44)
    width = max(120.0, min(380.0, 34 + max(CHAR_W * len(label), NOTE_CHAR_W * len(note))))
    return width, NODE_H + (NOTE_H if note else 0)


def _layers(ids: list[str], edges: list[Json]) -> tuple[dict[str, int], set[int]]:
    """Longest-path layering. Edges that close a cycle are returned as back edges."""
    succ: dict[str, list[tuple[str, int]]] = {i: [] for i in ids}
    for k, edge in enumerate(edges):
        succ[edge["from"]].append((edge["to"], k))
    colour = dict.fromkeys(ids, 0)
    back: set[int] = set()
    for root in ids:
        if colour[root]:
            continue
        colour[root] = 1
        stack = [(root, iter(succ[root]))]
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                colour[node] = 2
                stack.pop()
                continue
            target, k = nxt
            if target == node or colour[target] == 1:
                back.add(k)
            elif colour[target] == 0:
                colour[target] = 1
                stack.append((target, iter(succ[target])))
    indeg = dict.fromkeys(ids, 0)
    forward: dict[str, list[str]] = {i: [] for i in ids}
    for k, edge in enumerate(edges):
        if k not in back:
            forward[edge["from"]].append(edge["to"])
            indeg[edge["to"]] += 1
    layer = dict.fromkeys(ids, 0)
    queue = [i for i in ids if indeg[i] == 0]
    while queue:
        node = queue.pop(0)
        for target in forward[node]:
            layer[target] = max(layer[target], layer[node] + 1)
            indeg[target] -= 1
            if indeg[target] == 0:
                queue.append(target)
    return layer, back


def _order(columns: list[list[str]], edges: list[Json], back: set[int]) -> None:
    """Barycentre sweeps, in place, so edges cross less."""
    preds: dict[str, list[str]] = {}
    succs: dict[str, list[str]] = {}
    for k, edge in enumerate(edges):
        if k not in back:
            preds.setdefault(edge["to"], []).append(edge["from"])
            succs.setdefault(edge["from"], []).append(edge["to"])
    for _ in range(4):
        for neighbours, sweep in ((preds, range(1, len(columns))), (succs, range(len(columns) - 2, -1, -1))):
            position = {n: i for col in columns for i, n in enumerate(col)}
            for c in sweep:
                col = columns[c]

                def key(node: str, nb: dict[str, list[str]] = neighbours, pos: dict[str, int] = position) -> float:
                    linked = [pos[x] for x in nb.get(node, []) if x in pos]
                    return sum(linked) / len(linked) if linked else float(pos[node])

                col.sort(key=key)


def _edge_class(edge: Json, groups: dict[str, str]) -> str:
    """Into the change and out of an entry point in purple, straight out of the change in orange,
    the next hops in a softer orange, everything else dimmed: the eye follows the change."""
    source, target = groups[edge["from"]], groups[edge["to"]]
    if target == "changed" or source == "entry":
        return "up"
    if source == "changed":
        return "down"
    if source == "affected":
        return "warm"
    return "dim"


def _graph_svg(block: Json, title: str) -> str:
    nodes = {n["id"]: n for n in block["nodes"]}
    ids = list(nodes)
    groups = {i: nodes[i].get("group", "module") for i in ids}
    edges = [e for e in block.get("edges", []) if e["from"] in nodes and e["to"] in nodes]
    if not ids:
        return '<p class="muted">The graph is empty.</p>'
    layer, back = _layers(ids, edges)
    columns: list[list[str]] = [[] for _ in range(max(layer.values()) + 1)]
    for node_id in ids:
        columns[layer[node_id]].append(node_id)
    _order(columns, edges, back)

    size = {i: _node_box(nodes[i]) for i in ids}
    col_heights = [sum(size[n][1] for n in col) + ROW_GAP * (len(col) - 1) for col in columns]
    height = max(col_heights)
    pos: dict[str, tuple[float, float]] = {}
    x = float(PAD)
    for col, col_h in zip(columns, col_heights, strict=True):
        y = PAD + (height - col_h) / 2
        col_w = max(size[n][0] for n in col)
        for node_id in col:
            w, h = size[node_id]
            pos[node_id] = (x, y)
            size[node_id] = (col_w, h)  # one width per column, like a lane
            y += h + ROW_GAP
        x += col_w + COL_GAP
    width = x - COL_GAP + PAD
    loop_room = 52 if any(k in back for k in range(len(edges))) else 0
    total_h = height + 2 * PAD + loop_room

    parts = [
        # Shrinks to fit the page down to ~70% of its drawn size, then scrolls in its own box.
        f'<svg class="graph" role="img" aria-label="{_esc(title)}" viewBox="0 0 {width:.0f} {total_h:.0f}" '
        f'style="width:100%;max-width:{width:.0f}px;min-width:{width * 0.7:.0f}px" '
        f'xmlns="http://www.w3.org/2000/svg"><defs>',
    ]
    for kind in ("dim", "up", "down", "warm"):
        parts.append(
            f'<marker id="arrow-{kind}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="head-{kind}"/></marker>'
        )
    parts.append("</defs>")
    labels: list[str] = []
    # Dim edges first, so the coloured ones are drawn on top of them.
    order = sorted(range(len(edges)), key=lambda k: _edge_class(edges[k], groups) != "dim")
    for k in order:
        edge = edges[k]
        kind = _edge_class(edge, groups)
        (sx, sy), (sw, sh) = pos[edge["from"]], size[edge["from"]]
        (tx, ty), (tw, th) = pos[edge["to"]], size[edge["to"]]
        if k in back:
            x1, y1, x2, y2 = sx + sw / 2, sy + sh, tx + tw / 2, ty + th
            dip = max(y1, y2) + 44
            c1, c2 = (x1, dip), (x2, dip)
            cls = f"edge {kind} back"
        else:
            x1, y1, x2, y2 = sx + sw, sy + sh / 2, tx, ty + th / 2
            dx = max(32.0, (x2 - x1) / 2)
            c1, c2 = (x1 + dx, y1), (x2 - dx, y2)
            cls = f"edge {kind}"
        parts.append(
            f'<path class="{cls}" d="M{x1:.1f},{y1:.1f} C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} '
            f'{x2:.1f},{y2:.1f}" marker-end="url(#arrow-{kind})"/>'
        )
        if edge.get("label"):
            mx = (x1 + 3 * c1[0] + 3 * c2[0] + x2) / 8
            my = (y1 + 3 * c1[1] + 3 * c2[1] + y2) / 8
            labels.append(
                f'<text class="edge-label {kind}" x="{mx:.1f}" y="{my - 5:.1f}" text-anchor="middle">'
                f"{_esc(_clip(edge['label'], 28))}</text>"
            )
    for node_id in ids:
        node = nodes[node_id]
        (x0, y0), (w, h) = pos[node_id], size[node_id]
        label = _clip(node["label"])
        note = _clip(node.get("note", ""), 44)
        parts.append(f'<g class="node g-{groups[node_id]}"><title>{_esc(node["label"])}</title>')
        parts.append(f'<rect class="plate" x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" rx="7"/>')
        parts.append(
            f'<rect class="bar" x="{x0 + 1:.1f}" y="{y0 + 6:.1f}" width="3.5" height="{h - 12:.1f}" rx="1.5"/>'
        )
        label_y = y0 + (24 if note else h / 2 + 5)
        parts.append(f'<text class="node-label" x="{x0 + 18:.1f}" y="{label_y:.1f}">{_esc(label)}</text>')
        if note:
            parts.append(f'<text class="node-note" x="{x0 + 18:.1f}" y="{y0 + 43:.1f}">{_esc(note)}</text>')
        parts.append("</g>")
    parts.extend(labels)
    parts.append("</svg>")
    return "".join(parts)


def _graph(block: Json) -> str:
    title = block.get("title", "Graph")
    groups = [g for g in GROUPS if any(n.get("group", "module") == g for n in block["nodes"])]
    legend = "".join(f'<span class="legend-item"><i class="swatch g-{g}"></i>{_esc(GROUPS[g])}</span>' for g in groups)
    names = {n["id"]: n["label"] for n in block["nodes"]}
    rows = "".join(
        f"<tr><td><code>{_esc(names[e['from']])}</code></td><td><code>{_esc(names[e['to']])}</code></td>"
        f"<td>{_inline(e.get('label', ''))}</td></tr>"
        for e in block.get("edges", [])
    )
    listing = (
        f'<details class="graph-list"><summary>The graph as a list · {len(block.get("edges", []))} links</summary>'
        f'<div class="table-wrap"><table><thead><tr><th>From</th><th>To</th><th>How</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div></details>"
        if rows
        else ""
    )
    return f'<div class="graph-wrap">{_graph_svg(block, title)}</div><div class="legend">{legend}</div>{listing}'


# ---------------------------------------------------------------------------- blocks

TONE_LABEL = {"ok": "ok", "warn": "watch", "bad": "risk", "info": "note"}


def _cell(value: Json) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return _inline(value) if isinstance(value, str) else ""


def _table(block: Json) -> str:
    columns = block["columns"]
    rows = block["rows"]
    align = block.get("align") or [
        "right" if rows and all(isinstance(r[i], (int, float)) or r[i] is None for r in rows) else "left"
        for i in range(len(columns))
    ]
    head = "".join(f'<th class="a-{a}">{_esc(c)}</th>' for c, a in zip(columns, align, strict=True))
    body = "".join(
        "<tr>" + "".join(f'<td class="a-{a}">{_cell(v)}</td>' for v, a in zip(row, align, strict=True)) + "</tr>"
        for row in rows
    )
    empty = "" if rows else f'<tr><td colspan="{len(columns)}" class="muted">Nothing to list.</td></tr>'
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}{empty}</tbody></table></div>'


def _findings(block: Json) -> str:
    order = {s: i for i, s in enumerate(SEVERITIES)}
    items = sorted(block["items"], key=lambda f: order[f["severity"]])
    if not items:
        return '<p class="muted">No findings.</p>'
    cards = []
    for item in items:
        status = item.get("status", "open")
        chips = f'<span class="chip sev-{item["severity"]}">{item["severity"]}</span>'
        if status != "open":
            chips += f'<span class="chip status">{status}</span>'
        body = []
        if item.get("where"):
            body.append(f'<div class="where">{_esc(item["where"])}</div>')
        if item.get("evidence"):
            body.append(f'<div class="evidence">{_paragraphs(item["evidence"])}</div>')
        if item.get("fix"):
            body.append(f'<div class="fix"><span class="fix-label">Fix</span>{_paragraphs(item["fix"])}</div>')
        if item.get("reason"):
            reason = _paragraphs(item["reason"])
            body.append(f'<div class="fix reason"><span class="fix-label">Declined because</span>{reason}</div>')
        cards.append(
            f'<article class="finding f-{item["severity"]} s-{status}"><header>{chips}</header>'
            f"<h4>{_inline(item['title'])}</h4>{''.join(body)}</article>"
        )
    return f'<div class="findings">{"".join(cards)}</div>'


def _code(block: Json) -> str:
    start = block.get("start", 1)
    marks = set(block.get("highlight", []))
    lines = block["code"].rstrip("\n").split("\n")
    rows = "".join(
        f'<span class="ln{" hl" if start + i in marks else ""}">'
        f'<span class="no">{start + i}</span>{_esc(line) or " "}</span>'
        for i, line in enumerate(lines)
    )
    where = f'<span class="label">{_esc(block["where"])}</span>' if block.get("where") else ""
    return f'<figure class="code plate{" labelled" if where else ""}">{where}<pre><code>{rows}</code></pre></figure>'


def _steps(block: Json) -> str:
    items = []
    for item in block["items"]:
        where = f'<div class="where">{_esc(item["where"])}</div>' if item.get("where") else ""
        text = _paragraphs(item["text"]) if item.get("text") else ""
        items.append(f"<li><h4>{_inline(item['title'])}</h4>{where}{text}</li>")
    return f'<ol class="steps">{"".join(items)}</ol>'


def _block(block: Json) -> str:
    kind = block["type"]
    title = f"<h3>{_inline(block['title'])}</h3>" if block.get("title") else ""
    if kind == "text":
        body = _paragraphs(block["text"])
    elif kind == "callout":
        tone = block.get("tone", "info")
        body = (
            f'<div class="callout plate labelled c-{tone}"><span class="label">{TONE_LABEL[tone]}</span>'
            f"{_paragraphs(block['text'])}</div>"
        )
    elif kind == "list":
        tag = "ol" if block.get("ordered") else "ul"
        body = f'<{tag} class="bul">{"".join(f"<li>{_inline(i)}</li>" for i in block["items"])}</{tag}>'
    elif kind == "table":
        body = _table(block)
    elif kind == "findings":
        body = _findings(block)
    elif kind == "code":
        body = _code(block)
    elif kind == "graph":
        body = _graph(block)
    elif kind == "steps":
        body = _steps(block)
    else:  # kv
        rows = "".join(f"<dt>{_cell(k)}</dt><dd>{_cell(v)}</dd>" for k, v in block["items"])
        body = f'<dl class="kv">{rows}</dl>'
    return f'<div class="block b-{kind}">{title}{body}</div>'


# ---------------------------------------------------------------------------- page

# The design follows the pages of Data With Baraa's claude-code-data-engineering-skills (MIT): a violet
# ground with a radial glow and a faint grid, plates with a purple edge, Bricolage Grotesque for text and
# JetBrains Mono for labels, purple for what leads to the change and orange for what it reaches. Dark only.

LATIN = (
    "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, "
    "U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD"
)
LATIN_EXT = (
    "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, "
    "U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF"
)
FONTS = (
    ("Bricolage Grotesque", "200 800", "bricolage-grotesque-latin.woff2", LATIN),
    ("Bricolage Grotesque", "200 800", "bricolage-grotesque-latin-ext.woff2", LATIN_EXT),
    ("JetBrains Mono", "400 800", "jetbrains-mono-latin.woff2", LATIN),
    ("JetBrains Mono", "400 800", "jetbrains-mono-latin-ext.woff2", LATIN_EXT),
)


def _font_dir() -> Path | None:
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / "assets" / "fonts", here / "fonts"):
        if candidate.is_dir():
            return candidate
    return None


def font_css() -> str:
    """@font-face rules with the fonts inlined, so the page stays one file. Missing fonts fall back to system fonts."""
    folder = _font_dir()
    rules = []
    for family, weight, name, unicode_range in FONTS:
        path = folder / name if folder else None
        if path is None or not path.is_file():
            continue
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};font-display:block;"
            f"src:url(data:font/woff2;base64,{data}) format('woff2');unicode-range:{unicode_range}}}"
        )
    return "\n".join(rules)


CSS = """
:root{--ground:#080513;--bg:#0f0a1e;--ink:#ece7f8;--ink-2:rgba(236,231,248,.66);--ink-3:rgba(236,231,248,.48);
--line:rgba(236,231,248,.14);--line-2:rgba(236,231,248,.08);--purple:#8a63f2;--purple-soft:#c9b8ff;--gold:#ffd23f;
--orange:#ffa657;--red:#ff8a73;--green:#7ee0a8;--plate:linear-gradient(160deg,#1b1436 0%,#110c24 100%);
--plate-border:rgba(138,99,242,.28);--sans:'Bricolage Grotesque',ui-sans-serif,system-ui,-apple-system,sans-serif;
--mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color-scheme:dark}
*{margin:0;padding:0;box-sizing:border-box}
html{background:var(--ground)}
body{position:relative;min-height:100%;background:var(--ground);color:var(--ink);font:400 20px/1.5 var(--sans);
-webkit-font-smoothing:antialiased}
body::before{content:'';position:absolute;left:0;right:0;top:0;height:min(1600px,100%);z-index:0;pointer-events:none;
background:radial-gradient(1500px 900px at 50% 420px,#161033 0%,#0e0a1d 55%,rgba(8,5,19,0) 100%)}
body::after{content:'';position:fixed;inset:0;z-index:0;pointer-events:none;background-size:46px 46px;
background-image:linear-gradient(rgba(173,150,255,.05) 1.2px,transparent 1.2px),
linear-gradient(90deg,rgba(173,150,255,.05) 1.2px,transparent 1.2px)}
main{position:relative;z-index:1;max-width:1360px;margin:0 auto;padding:64px 48px 96px}
a{color:var(--purple-soft);text-underline-offset:3px}
code,pre{font-family:var(--mono);font-variant-ligatures:none}
code{font-size:.88em;color:var(--purple-soft)}
strong{font-weight:700;color:var(--ink)}
p{max-width:1120px;text-wrap:pretty}
.muted{color:var(--ink-3)}
.status{display:flex;flex-wrap:wrap;align-items:center;gap:8px 22px;font:600 15px/1.4 var(--mono);letter-spacing:.14em;
text-transform:uppercase;color:var(--ink-3)}
.status .skill{display:inline-flex;align-items:center;gap:12px;color:var(--purple-soft)}
.status .skill i{width:9px;height:9px;border-radius:50%;background:var(--purple);box-shadow:0 0 14px var(--purple)}
.status b{font-weight:600;color:var(--ink-2);text-transform:none;letter-spacing:.04em}
h1{margin-top:18px;font-size:clamp(34px,5vw,62px);font-weight:800;letter-spacing:-.022em;line-height:1.04;
text-wrap:balance;max-width:1200px}
h1 code{font-size:.82em;font-weight:600}
.lead{margin-top:18px;font-size:clamp(19px,2vw,25px);line-height:1.4;color:var(--ink-2);max-width:1120px}
.plate{position:relative;background:var(--plate);border:1px solid var(--plate-border);border-radius:14px}
.label{position:absolute;left:28px;top:-15px;background:var(--bg);border:1px solid var(--line);border-radius:8px;
padding:4px 12px;font:600 13px/1.35 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-2);
white-space:nowrap;max-width:calc(100% - 56px);overflow:hidden;text-overflow:ellipsis}
.verdict{margin-top:44px;padding:30px 34px 26px;font-size:clamp(18px,1.8vw,23px);line-height:1.45}
.verdict p+p{margin-top:10px}
.v-bad .label,.c-bad .label{color:var(--red);border-color:rgba(255,138,115,.5)}
.v-warn .label,.c-warn .label{color:var(--gold);border-color:rgba(255,210,63,.45)}
.v-ok .label,.c-ok .label{color:var(--green);border-color:rgba(126,224,168,.45)}
.v-info .label,.c-info .label{color:var(--purple-soft);border-color:var(--plate-border)}
.facts{display:grid;grid-template-columns:repeat(var(--cols),minmax(0,1fr));margin-top:40px;
border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.fact{padding:22px 26px 22px 0;border-bottom:1px solid var(--line)}
.fact.mid{border-left:1px solid var(--line);padding-left:26px}.fact.last{border-bottom:0}
.fact .l{font:600 14px/1.35 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3)}
.fact .v{margin-top:8px;font-size:clamp(26px,3vw,36px);font-weight:800;letter-spacing:-.015em;line-height:1.1;
font-variant-numeric:tabular-nums;text-wrap:balance}
.fact .n{margin-top:6px;font-size:16px;line-height:1.4;color:var(--ink-2)}
.t-bad .v{color:var(--red)}.t-warn .v{color:var(--gold)}.t-ok .v{color:var(--green)}
nav.toc{display:flex;flex-wrap:wrap;gap:8px 26px;margin-top:30px}
nav.toc a{font:600 13px/1.4 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);
text-decoration:none}
nav.toc a span{color:var(--purple-soft);margin-right:8px}nav.toc a:hover{color:var(--ink)}
section{margin-top:76px;scroll-margin-top:24px}
section>header{display:flex;align-items:baseline;gap:20px;padding-bottom:14px;border-bottom:1px solid var(--line);
margin-bottom:24px}
section>header .n{font:600 18px var(--mono);letter-spacing:.1em;color:var(--purple-soft)}
section>header h2{font-size:clamp(26px,3vw,38px);font-weight:700;letter-spacing:-.015em;line-height:1.1;
text-wrap:balance}
.intro{color:var(--ink-2)}.intro+.block{margin-top:24px}
.block{margin-top:28px}.block:first-of-type{margin-top:0}
.block>h3{font:600 14px/1.4 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);
margin-bottom:16px}
.block p+p{margin-top:12px}
.block>h3+.plate.labelled{margin-top:30px}
.tag{display:inline-block;font:600 11.5px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;
padding:4px 7px 3px;border:1px solid;border-radius:6px;vertical-align:3px;margin-left:3px}
.tag-high{color:var(--green);border-color:rgba(126,224,168,.45)}
.tag-med{color:var(--gold);border-color:rgba(255,210,63,.45)}
.tag-guess{color:var(--red);border-color:rgba(255,138,115,.5)}
ul.bul,ol.bul{list-style:none;display:grid;gap:10px;max-width:1120px}
ul.bul li,ol.bul li{position:relative;padding-left:28px}
ul.bul li::before{content:'';position:absolute;left:4px;top:.62em;width:7px;height:7px;border-radius:2px;
background:var(--purple)}
ol.bul{counter-reset:b}ol.bul li{counter-increment:b}
ol.bul li::before{content:counter(b);position:absolute;left:0;font:600 .8em/1.9 var(--mono);color:var(--purple-soft)}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th{font:600 13px/1.4 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);text-align:left;
padding:0 24px 12px 0;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:bottom}
td{padding:13px 24px 13px 0;border-bottom:1px solid var(--line-2);vertical-align:baseline;font-size:17.5px;
line-height:1.45}
tr:last-child td{border-bottom:0}
td.a-right,th.a-right{text-align:right}td.a-right{font-family:var(--mono);font-variant-numeric:tabular-nums}
td.a-center,th.a-center{text-align:center}
td:first-child{color:var(--ink)}td{color:var(--ink-2)}
.findings{display:grid;gap:16px}
.finding{position:relative;padding:22px 28px 20px;background:var(--plate);border:1px solid var(--plate-border);
border-radius:14px;box-shadow:inset 4px 0 0 var(--purple-soft)}
.finding.f-high{box-shadow:inset 4px 0 0 var(--red)}.finding.f-medium{box-shadow:inset 4px 0 0 var(--orange)}
.finding.f-low{box-shadow:inset 4px 0 0 var(--green)}
.finding header{display:flex;gap:8px;margin-bottom:10px}
.finding h4{font-size:22px;font-weight:700;line-height:1.3;letter-spacing:-.005em}
.finding.s-declined h4,.finding.s-fixed h4{color:var(--ink-2)}
.chip{font:600 11.5px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;padding:5px 8px 4px;
border:1px solid var(--line);border-radius:6px;color:var(--ink-2)}
.chip.sev-high{color:var(--red);border-color:rgba(255,138,115,.5)}
.chip.sev-medium{color:var(--orange);border-color:rgba(255,166,87,.5)}
.chip.sev-low{color:var(--green);border-color:rgba(126,224,168,.45)}
.chip.sev-info{color:var(--purple-soft);border-color:var(--plate-border)}
.where{font:500 15px/1.5 var(--mono);color:var(--purple-soft);margin-top:6px;word-break:break-word}
.evidence{margin-top:10px;color:var(--ink-2);font-size:18px}
.fix{margin-top:14px;padding:14px 18px;border-radius:10px;background:rgba(8,5,19,.5);border:1px solid var(--line-2);
font-size:18px}
.fix-label{display:block;font:600 12px/1.6 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3)}
figure.code{padding:22px 0 20px}figure.code.labelled{margin-top:14px;padding-top:30px}
figure.code pre{overflow-x:auto;font-size:15.5px;line-height:1.6}
.ln{display:block;padding:0 28px 0 0;white-space:pre;color:var(--ink)}
.ln .no{display:inline-block;width:3.8em;padding-right:1.3em;text-align:right;color:var(--ink-3);user-select:none}
.ln.hl{background:rgba(255,166,87,.11);box-shadow:inset 3px 0 0 var(--orange)}
.callout{margin-top:14px;padding:28px 30px 22px}.callout:not(.labelled){padding-top:22px}
ol.steps{list-style:none;counter-reset:s;max-width:1120px}
ol.steps li{position:relative;counter-increment:s;padding:0 0 26px 66px}
ol.steps li::before{content:counter(s,decimal-leading-zero);position:absolute;left:0;top:3px;
font:600 17px var(--mono);letter-spacing:.06em;color:var(--purple-soft)}
ol.steps li::after{content:'';position:absolute;left:12px;top:34px;bottom:8px;width:1px;background:var(--line)}
ol.steps li:last-child{padding-bottom:0}ol.steps li:last-child::after{display:none}
ol.steps h4{font-size:21px;font-weight:700;line-height:1.3}
ol.steps p{color:var(--ink-2);margin-top:6px;font-size:18px}
dl.kv{display:grid;grid-template-columns:minmax(150px,260px) 1fr;max-width:1120px}
dl.kv dt,dl.kv dd{padding:13px 0;border-bottom:1px solid var(--line-2)}
dl.kv dt{font:600 13px/1.6 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);
padding-right:20px}
dl.kv dd{font-size:18px;color:var(--ink)}
.graph-wrap{overflow-x:auto;border:1px solid var(--plate-border);border-radius:14px;
background:linear-gradient(160deg,rgba(27,20,54,.7) 0%,rgba(17,12,36,.7) 100%)}
svg.graph{display:block;height:auto;font-family:var(--mono)}
.node .plate{fill:rgba(236,231,248,.035);stroke:rgba(173,150,255,.26);stroke-width:1.2}
.node .bar{fill:rgba(173,150,255,.35)}
.node-label{font-size:14px;font-weight:500;fill:var(--ink)}.node-note{font-size:12px;fill:var(--ink-3)}
.g-entry .plate{stroke:var(--purple);stroke-width:1.6}.g-entry .bar{fill:var(--purple)}
.g-boundary .plate{fill:rgba(138,99,242,.16);stroke:var(--purple)}.g-boundary .bar{fill:var(--purple-soft)}
.g-changed .plate{fill:rgba(138,99,242,.34);stroke:var(--purple-soft);stroke-width:2}
.g-changed .bar{fill:var(--purple-soft)}.g-changed .node-label{font-weight:700}
.g-affected .plate{fill:rgba(255,166,87,.11);stroke:var(--orange);stroke-width:1.8}.g-affected .bar{fill:var(--orange)}
.g-data .plate{fill:rgba(255,210,63,.06);stroke:rgba(255,210,63,.55)}.g-data .bar{fill:var(--gold)}
.g-external .plate{fill:none;stroke:rgba(236,231,248,.4);stroke-dasharray:5 4}.g-external .bar{fill:var(--ink-3)}
.g-test .plate{fill:none;stroke:var(--line)}.g-test .node-label{fill:var(--ink-2)}.g-test .bar{fill:var(--line)}
.g-safe .plate{fill:rgba(126,224,168,.06);stroke:rgba(126,224,168,.5)}.g-safe .bar{fill:var(--green)}
.g-unknown{opacity:.55}.g-unknown .plate{fill:none;stroke-dasharray:2 4}
.edge{fill:none;stroke-width:1.4}.edge.dim{stroke:rgba(201,184,255,.3)}
.edge.up{stroke:var(--purple);stroke-width:2}.edge.down{stroke:var(--orange);stroke-width:2}
.edge.warm{stroke:rgba(255,166,87,.42)}.edge.back{stroke-dasharray:6 5}
.head-dim{fill:rgba(201,184,255,.45)}.head-up{fill:var(--purple)}.head-down{fill:var(--orange)}
.head-warm{fill:rgba(255,166,87,.6)}
.edge-label{font-size:11.5px;fill:var(--ink-2);paint-order:stroke;stroke:#0f0a1e;stroke-width:5px;stroke-linejoin:round}
.edge-label.up{fill:var(--purple-soft)}.edge-label.down,.edge-label.warm{fill:var(--orange)}
.legend{display:flex;flex-wrap:wrap;gap:8px 22px;margin-top:14px;font:600 12px/1.4 var(--mono);letter-spacing:.1em;
text-transform:uppercase;color:var(--ink-3)}
.legend-item{display:inline-flex;align-items:center;gap:8px}
.swatch{display:inline-block;width:16px;height:11px;border-radius:3px;border:1.5px solid rgba(173,150,255,.4);
background:rgba(236,231,248,.04)}
.swatch.g-entry{border-color:var(--purple)}.swatch.g-boundary{background:rgba(138,99,242,.2);border-color:var(--purple)}
.swatch.g-changed{background:rgba(138,99,242,.4);border-color:var(--purple-soft)}
.swatch.g-affected{background:rgba(255,166,87,.15);border-color:var(--orange)}
.swatch.g-data{background:rgba(255,210,63,.08);border-color:rgba(255,210,63,.6)}
.swatch.g-external{border-style:dashed;border-color:rgba(236,231,248,.4);background:none}
.swatch.g-test{background:none;border-color:var(--line)}
.swatch.g-safe{background:rgba(126,224,168,.08);border-color:rgba(126,224,168,.55)}
.swatch.g-unknown{border-style:dotted;opacity:.6}
details.graph-list{margin-top:16px}
details.graph-list summary{cursor:pointer;font:600 12px/1.4 var(--mono);letter-spacing:.12em;text-transform:uppercase;
color:var(--ink-3)}
details.graph-list .table-wrap{margin-top:14px}
footer{margin-top:88px;padding-top:18px;border-top:1px solid var(--line);font:600 12px/1.7 var(--mono);
letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3)}
@media (max-width:760px){main{padding:36px 16px 64px}body{font-size:17px}
.facts{grid-template-columns:1fr 1fr}.fact,.fact.mid{border-left:0;padding:16px 12px 16px 0}
.fact.last{border-bottom:1px solid var(--line)}
section{margin-top:56px}td{font-size:15.5px}dl.kv{grid-template-columns:1fr}dl.kv dt{border-bottom:0;padding-bottom:0}
.verdict{padding:26px 20px 20px}.finding{padding:18px 18px 16px}.label{left:16px}ol.steps li{padding-left:48px}}
"""


def _facts(stats: list[Json]) -> str:
    """The numbers on top, as a grid that reads like a table: hairlines between, none on the outside."""
    if not stats:
        return ""
    n = len(stats)
    cols = n if n <= 4 else (4 if n % 4 == 0 else 3)
    last_row = n - (n % cols or cols)
    cells = []
    for i, stat in enumerate(stats):
        classes = ["fact", f"t-{stat.get('tone', 'info')}"]
        if i % cols:
            classes.append("mid")
        if i >= last_row:
            classes.append("last")
        note = f'<div class="n">{_inline(stat["note"])}</div>' if stat.get("note") else ""
        cells.append(
            f'<div class="{" ".join(classes)}"><div class="l">{_inline(stat["label"])}</div>'
            f'<div class="v">{_cell(stat["value"])}</div>{note}</div>'
        )
    return f'<div class="facts" style="--cols:{cols}">{"".join(cells)}</div>'


def render(page: Json) -> str:
    """Return the HTML of a page that validate() accepted."""
    skill = page["skill"]
    meta = page.get("meta", {})
    status = f'<span class="skill"><i></i>{_esc(skill)}</span>' + "".join(
        f"<span>{_esc(k)} <b>{_cell(v)}</b></span>" for k, v in meta.items()
    )
    verdict = page.get("verdict")
    verdict_html = (
        f'<div class="verdict plate v-{verdict.get("tone", "info")}"><span class="label">Verdict</span>'
        f"{_paragraphs(verdict['text'])}</div>"
        if verdict
        else ""
    )
    sections = []
    toc = []
    for number, section in enumerate(page["sections"], 1):
        sid = section.get("id") or _slug(section["title"])
        toc.append(f'<a href="#{_esc(sid)}"><span>{number:02d}</span>{_esc(section["title"])}</a>')
        intro = f'<p class="intro">{_inline(section["intro"])}</p>' if section.get("intro") else ""
        blocks = "".join(_block(b) for b in section.get("blocks", []))
        sections.append(
            f'<section id="{_esc(sid)}"><header><span class="n">{number:02d}</span>'
            f"<h2>{_inline(section['title'])}</h2></header>{intro}{blocks}</section>"
        )
    toc_html = f'<nav class="toc">{"".join(toc)}</nav>' if len(toc) >= 3 else ""
    date = f" · {_esc(meta['date'])}" if isinstance(meta.get("date"), str) else ""
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark">'
        f'<meta name="generator" content="claude-role-skills/{_esc(skill)}">'
        f"<title>{_esc(page['title'])}</title><style>{font_css()}{CSS}</style></head><body><main>"
        f'<div class="status">{status}</div><h1>{_inline(page["title"])}</h1>'
        + (f'<p class="lead">{_inline(page["subtitle"])}</p>' if page.get("subtitle") else "")
        + verdict_html
        + _facts(page.get("stats", []))
        + toc_html
        + "".join(sections)
        + f"<footer>Written by the {_esc(skill)} skill{date} · numbers from the skill's scripts · "
        "claims tagged high (checked), med (likely), guess (not checked)</footer>"
        "</main></body></html>\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a skill page from its JSON.")
    parser.add_argument("page", type=Path, help="the page JSON")
    parser.add_argument("-o", "--output", type=Path, help="where to write the HTML")
    parser.add_argument("--check", action="store_true", help="validate only, write nothing")
    args = parser.parse_args(argv)
    try:
        page = json.loads(args.page.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {args.page}: {exc}", file=sys.stderr)
        return 2
    errors = validate(page)
    if errors:
        print(f"{args.page}: {len(errors)} problem(s)", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    if args.check:
        print(f"{args.page}: valid")
        return 0
    output = args.output or args.page.with_suffix(".html")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(page), encoding="utf-8")
    print(output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
