#!/usr/bin/env python3
"""Render a skill's page JSON into one self-contained HTML file.

The skill decides the content and writes it as JSON (the format is in references/page-format.md).
This script only draws it, so every page of every skill has the same layout, every value is
escaped, and nothing in the page is fetched from the network. A small inline script makes the graphs
clickable and adds table filters and copy buttons; the page reads the same without it. Standard
library only.

Usage:
    python3 render_page.py PAGE.json -o PAGE.html   # write the page
    python3 render_page.py PAGE.json --check        # validate only
    python3 render_page.py --site SITE.json         # write every page of a set, with a header linking them

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
import os
import re
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any
from urllib.parse import quote

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
BLOCK_TYPES = (
    "text",
    "list",
    "table",
    "findings",
    "code",
    "graph",
    "steps",
    "kv",
    "callout",
    "decision",
    "architecture",
    "model",
    "nested",
)
CONFIDENCE = ("high", "med", "guess")
RATINGS = ("pass", "weak", "fail")
OPTION_STATUSES = ("chosen", "viable", "eliminated")
KINDS = {
    "user": "user",
    "channel": "channel",
    "service": "service",
    "model": "model",
    "retrieval": "retrieval",
    "store": "data store",
    "tool": "tool",
    "system": "outside system",
    "human": "human step",
    "guard": "guardrail",
    "ops": "operations",
}
TRUST = ("trusted", "untrusted")
FLAGS = ("warn", "bad")
TABLE_KINDS = ("fact", "dimension", "bridge", "hub", "link", "satellite", "staging", "table")
COLUMN_KEYS = ("pk", "fk", "bk")
CARDINALITIES = ("1:1", "1:n", "n:1", "n:n")


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


def _pairs_ok(value: Json) -> bool:
    return isinstance(value, list) and all(
        isinstance(p, list) and len(p) == 2 and all(_cell_ok(c) for c in p) for p in value
    )


def _validate_decision(block: Json, path: str, errs: list[str]) -> None:
    factors = _list(block, "factors", path, errs)
    if not factors or not all(isinstance(f, str) for f in factors):
        errs.append(f"{path}.factors: must be a non-empty list of strings")
    chosen = 0
    options = _list(block, "options", path, errs)
    if not options:
        errs.append(f"{path}.options: at least one option")
    for i, opt in enumerate(options):
        opath = f"{path}.options[{i}]"
        if not isinstance(opt, dict):
            errs.append(f"{opath}: must be an object")
            continue
        _str(opt, "label", opath, errs)
        for key in ("id", "why", "eliminated_by"):
            _str(opt, key, opath, errs, required=False)
        status = opt.get("status", "viable")
        if status not in OPTION_STATUSES:
            errs.append(f"{opath}.status: must be one of {', '.join(OPTION_STATUSES)}")
        chosen += status == "chosen"
        if status == "eliminated":
            for key in ("eliminated_by", "why"):
                if not opt.get(key):
                    errs.append(f"{opath}.{key}: an eliminated option keeps what eliminated it and why")
        cells = _list(opt, "cells", opath, errs)
        if len(cells) != len(factors):
            errs.append(f"{opath}.cells: must hold one cell per factor ({len(factors)})")
        for j, cell in enumerate(cells):
            cpath = f"{opath}.cells[{j}]"
            if not isinstance(cell, dict):
                errs.append(f"{cpath}: must be an object")
                continue
            if cell.get("rating") not in RATINGS:
                errs.append(f"{cpath}.rating: must be one of {', '.join(RATINGS)}")
            _str(cell, "text", cpath, errs, required=False)
    if chosen > 1:
        errs.append(f"{path}.options: at most one option is chosen")


def _validate_architecture(block: Json, path: str, errs: list[str]) -> None:
    variant_ids: list[str] = []
    for i, var in enumerate(_list(block, "variants", path, errs, required=False)):
        vpath = f"{path}.variants[{i}]"
        if not isinstance(var, dict):
            errs.append(f"{vpath}: must be an object")
            continue
        _str(var, "id", vpath, errs)
        _str(var, "label", vpath, errs)
        _str(var, "note", vpath, errs, required=False)
        if isinstance(var.get("id"), str):
            if var["id"] in variant_ids:
                errs.append(f"{vpath}.id: duplicate id {var['id']!r}")
            variant_ids.append(var["id"])
    every = set(variant_ids) or {"_"}

    def shown(obj: Json, opath: str) -> set[str]:
        if "variants" not in obj:
            return set(every)
        names = obj["variants"]
        if not isinstance(names, list) or not names or not all(isinstance(v, str) for v in names):
            errs.append(f"{opath}.variants: must be a non-empty list of variant ids")
            return set(every)
        for name in names:
            if name not in variant_ids:
                errs.append(f"{opath}.variants: unknown variant id {name!r}")
        return {v for v in names if v in variant_ids}

    zone_ids: set[str] = set()
    zones = _list(block, "zones", path, errs)
    if not zones:
        errs.append(f"{path}.zones: at least one zone")
    for i, zone in enumerate(zones):
        zpath = f"{path}.zones[{i}]"
        if not isinstance(zone, dict):
            errs.append(f"{zpath}: must be an object")
            continue
        _str(zone, "id", zpath, errs)
        _str(zone, "label", zpath, errs)
        if isinstance(zone.get("id"), str):
            if zone["id"] in zone_ids:
                errs.append(f"{zpath}.id: duplicate id {zone['id']!r}")
            zone_ids.add(zone["id"])

    comps: dict[str, set[str]] = {}
    components = _list(block, "components", path, errs)
    if not components:
        errs.append(f"{path}.components: at least one component")
    for i, comp in enumerate(components):
        cpath = f"{path}.components[{i}]"
        if not isinstance(comp, dict):
            errs.append(f"{cpath}: must be an object")
            continue
        for key in ("id", "label", "zone"):
            _str(comp, key, cpath, errs)
        for key in ("tech", "note"):
            _str(comp, key, cpath, errs, required=False)
        if isinstance(comp.get("zone"), str) and comp["zone"] not in zone_ids:
            errs.append(f"{cpath}.zone: unknown zone id {comp['zone']!r}")
        if comp.get("kind", "service") not in KINDS:
            errs.append(f"{cpath}.kind: must be one of {', '.join(KINDS)}")
        if "flag" in comp and comp["flag"] not in FLAGS:
            errs.append(f"{cpath}.flag: must be one of {', '.join(FLAGS)}")
        if "side_effect" in comp and not isinstance(comp["side_effect"], bool):
            errs.append(f"{cpath}.side_effect: must be true or false")
        if "details" in comp and not _pairs_ok(comp["details"]):
            errs.append(f"{cpath}.details: must be a list of [label, value] pairs")
        if isinstance(comp.get("id"), str):
            if comp["id"] in comps:
                errs.append(f"{cpath}.id: duplicate id {comp['id']!r}")
            comps[comp["id"]] = shown(comp, cpath)

    def ends(obj: Json, opath: str, where: set[str]) -> None:
        for key in ("from", "to"):
            if obj.get(key) not in comps:
                errs.append(f"{opath}.{key}: unknown component id {obj.get(key)!r}")
                continue
            missing = where - comps[obj[key]]
            if missing:
                errs.append(f"{opath}.{key}: {obj[key]!r} is not shown in variant {', '.join(sorted(missing))}")

    for i, link in enumerate(_list(block, "links", path, errs, required=False)):
        lpath = f"{path}.links[{i}]"
        if not isinstance(link, dict):
            errs.append(f"{lpath}: must be an object")
            continue
        _str(link, "label", lpath, errs, required=False)
        if link.get("trust", "trusted") not in TRUST:
            errs.append(f"{lpath}.trust: must be one of {', '.join(TRUST)}")
        if "flag" in link and link["flag"] not in FLAGS:
            errs.append(f"{lpath}.flag: must be one of {', '.join(FLAGS)}")
        ends(link, lpath, shown(link, lpath))

    flow_ids: set[str] = set()
    for i, flow in enumerate(_list(block, "flows", path, errs, required=False)):
        fpath = f"{path}.flows[{i}]"
        if not isinstance(flow, dict):
            errs.append(f"{fpath}: must be an object")
            continue
        _str(flow, "id", fpath, errs)
        _str(flow, "title", fpath, errs)
        if isinstance(flow.get("id"), str):
            if flow["id"] in flow_ids:
                errs.append(f"{fpath}.id: duplicate id {flow['id']!r}")
            flow_ids.add(flow["id"])
        where = shown(flow, fpath)
        steps = _list(flow, "steps", fpath, errs)
        if not steps:
            errs.append(f"{fpath}.steps: at least one step")
        for j, step in enumerate(steps):
            spath = f"{fpath}.steps[{j}]"
            if not isinstance(step, dict):
                errs.append(f"{spath}: must be an object")
                continue
            _str(step, "text", spath, errs)
            ends(step, spath, where)

    if "reach" in block:
        _validate_reach(block["reach"], f"{path}.reach", set(comps), errs)


def _validate_reach(spec: Json, path: str, comps: set[str], errs: list[str]) -> None:
    if not isinstance(spec, dict):
        errs.append(f"{path}: must be an object")
        return
    _str(spec, "label", path, errs)
    for key, required in (("from", True), ("targets", True), ("stops", False)):
        ids = _list(spec, key, path, errs, required=required)
        if required and not ids:
            errs.append(f"{path}.{key}: at least one component id")
        for i, name in enumerate(ids):
            if name not in comps:
                errs.append(f"{path}.{key}[{i}]: unknown component id {name!r}")


def _validate_model(block: Json, path: str, errs: list[str]) -> None:
    area_ids: set[str] = set()
    for i, area in enumerate(_list(block, "areas", path, errs, required=False)):
        apath = f"{path}.areas[{i}]"
        if not isinstance(area, dict):
            errs.append(f"{apath}: must be an object")
            continue
        _str(area, "id", apath, errs)
        _str(area, "label", apath, errs)
        if isinstance(area.get("id"), str):
            if area["id"] in area_ids:
                errs.append(f"{apath}.id: duplicate id {area['id']!r}")
            area_ids.add(area["id"])
    columns_of: dict[str, set[str]] = {}
    tables = _list(block, "tables", path, errs)
    if not tables:
        errs.append(f"{path}.tables: at least one table")
    for i, table in enumerate(tables):
        tpath = f"{path}.tables[{i}]"
        if not isinstance(table, dict):
            errs.append(f"{tpath}: must be an object")
            continue
        _str(table, "id", tpath, errs)
        _str(table, "label", tpath, errs)
        for key in ("grain", "note", "history"):
            _str(table, key, tpath, errs, required=False)
        if table.get("kind", "table") not in TABLE_KINDS:
            errs.append(f"{tpath}.kind: must be one of {', '.join(TABLE_KINDS)}")
        if "area" in table and table["area"] not in area_ids:
            errs.append(f"{tpath}.area: unknown area id {table['area']!r}")
        if "flag" in table and table["flag"] not in FLAGS:
            errs.append(f"{tpath}.flag: must be one of {', '.join(FLAGS)}")
        names: set[str] = set()
        for j, column in enumerate(_list(table, "columns", tpath, errs)):
            cpath = f"{tpath}.columns[{j}]"
            if not isinstance(column, dict):
                errs.append(f"{cpath}: must be an object")
                continue
            _str(column, "name", cpath, errs)
            for key in ("type", "note", "mask", "history"):
                _str(column, key, cpath, errs, required=False)
            if "key" in column and column["key"] not in COLUMN_KEYS:
                errs.append(f"{cpath}.key: must be one of {', '.join(COLUMN_KEYS)}")
            if "personal" in column and not isinstance(column["personal"], bool):
                errs.append(f"{cpath}.personal: must be true or false")
            if isinstance(column.get("name"), str):
                if column["name"] in names:
                    errs.append(f"{cpath}.name: duplicate column {column['name']!r}")
                names.add(column["name"])
        if isinstance(table.get("id"), str):
            if table["id"] in columns_of:
                errs.append(f"{tpath}.id: duplicate id {table['id']!r}")
            columns_of[table["id"]] = names
    for i, rel in enumerate(_list(block, "relations", path, errs, required=False)):
        rpath = f"{path}.relations[{i}]"
        if not isinstance(rel, dict):
            errs.append(f"{rpath}: must be an object")
            continue
        for key in ("on", "label"):
            _str(rel, key, rpath, errs, required=False)
        if rel.get("cardinality", "n:1") not in CARDINALITIES:
            errs.append(f"{rpath}.cardinality: must be one of {', '.join(CARDINALITIES)}")
        known = True
        for key in ("from", "to"):
            if rel.get(key) not in columns_of:
                errs.append(f"{rpath}.{key}: unknown table id {rel.get(key)!r}")
                known = False
        if known and isinstance(rel.get("on"), str):
            for pair in rel["on"].split(","):
                left, _, right = pair.strip().partition("=")
                left, right = left.strip(), (right.strip() or left.strip())
                if left not in columns_of[rel["from"]]:
                    errs.append(f"{rpath}.on: {rel['from']!r} has no column {left!r}")
                if right not in columns_of[rel["to"]]:
                    errs.append(f"{rpath}.on: {rel['to']!r} has no column {right!r}")


def _validate_nested(block: Json, path: str, errs: list[str]) -> None:
    boxes: dict[str, Json] = {}
    items = _list(block, "boxes", path, errs)
    if not items:
        errs.append(f"{path}.boxes: at least one box")
    for i, box in enumerate(items):
        bpath = f"{path}.boxes[{i}]"
        if not isinstance(box, dict):
            errs.append(f"{bpath}: must be an object")
            continue
        _str(box, "id", bpath, errs)
        _str(box, "label", bpath, errs)
        for key in ("tech", "note", "parent"):
            _str(box, key, bpath, errs, required=False)
        if box.get("kind", "service") not in KINDS:
            errs.append(f"{bpath}.kind: must be one of {', '.join(KINDS)}")
        if "flag" in box and box["flag"] not in FLAGS:
            errs.append(f"{bpath}.flag: must be one of {', '.join(FLAGS)}")
        if "side_effect" in box and not isinstance(box["side_effect"], bool):
            errs.append(f"{bpath}.side_effect: must be true or false")
        if "details" in box and not _pairs_ok(box["details"]):
            errs.append(f"{bpath}.details: must be a list of [label, value] pairs")
        if isinstance(box.get("id"), str):
            if box["id"] in boxes:
                errs.append(f"{bpath}.id: duplicate id {box['id']!r}")
            boxes[box["id"]] = box
    for i, box in enumerate(items):
        if not isinstance(box, dict) or "parent" not in box:
            continue
        seen = {box.get("id")}
        at = box["parent"]
        while at is not None:
            if at not in boxes:
                errs.append(f"{path}.boxes[{i}].parent: unknown box id {at!r}")
                break
            if at in seen:
                errs.append(f"{path}.boxes[{i}].parent: boxes contain each other")
                break
            seen.add(at)
            at = boxes[at].get("parent")
    level_ids: list[str] = []
    for i, level in enumerate(_list(block, "levels", path, errs, required=False)):
        lpath = f"{path}.levels[{i}]"
        if not isinstance(level, dict):
            errs.append(f"{lpath}: must be an object")
            continue
        _str(level, "id", lpath, errs)
        _str(level, "label", lpath, errs)
        _str(level, "note", lpath, errs, required=False)
        for j, name in enumerate(_list(level, "open", lpath, errs)):
            if name not in boxes:
                errs.append(f"{lpath}.open[{j}]: unknown box id {name!r}")
        if isinstance(level.get("id"), str):
            if level["id"] in level_ids:
                errs.append(f"{lpath}.id: duplicate id {level['id']!r}")
            level_ids.append(level["id"])
    for i, link in enumerate(_list(block, "links", path, errs, required=False)):
        lpath = f"{path}.links[{i}]"
        if not isinstance(link, dict):
            errs.append(f"{lpath}: must be an object")
            continue
        _str(link, "label", lpath, errs, required=False)
        if link.get("trust", "trusted") not in TRUST:
            errs.append(f"{lpath}.trust: must be one of {', '.join(TRUST)}")
        if "flag" in link and link["flag"] not in FLAGS:
            errs.append(f"{lpath}.flag: must be one of {', '.join(FLAGS)}")
        for key in ("from", "to"):
            if link.get(key) not in boxes:
                errs.append(f"{lpath}.{key}: unknown box id {link.get(key)!r}")
    if errs and any(e.startswith(path) for e in errs):
        return  # the rest needs a sound tree
    views = _nest_views(block)
    flow_ids: set[str] = set()
    for i, flow in enumerate(_list(block, "flows", path, errs, required=False)):
        fpath = f"{path}.flows[{i}]"
        if not isinstance(flow, dict):
            errs.append(f"{fpath}: must be an object")
            continue
        _str(flow, "id", fpath, errs)
        _str(flow, "title", fpath, errs)
        if isinstance(flow.get("id"), str):
            if flow["id"] in flow_ids:
                errs.append(f"{fpath}.id: duplicate id {flow['id']!r}")
            flow_ids.add(flow["id"])
        where = flow.get("variants", [v for v, _ in views])
        if not isinstance(where, list) or not where:
            errs.append(f"{fpath}.variants: must be a non-empty list of level ids")
            continue
        for name in where:
            if name not in dict(views):
                errs.append(f"{fpath}.variants: unknown level id {name!r}")
        steps = _list(flow, "steps", fpath, errs)
        if not steps:
            errs.append(f"{fpath}.steps: at least one step")
        for j, step in enumerate(steps):
            spath = f"{fpath}.steps[{j}]"
            if not isinstance(step, dict):
                errs.append(f"{spath}: must be an object")
                continue
            _str(step, "text", spath, errs)
            for key in ("from", "to"):
                if step.get(key) not in boxes:
                    errs.append(f"{spath}.{key}: unknown box id {step.get(key)!r}")
                    continue
                hidden = [
                    v for v in where if v in dict(views) and step[key] not in _nest_visible(block, dict(views)[v])
                ]
                if hidden:
                    errs.append(f"{spath}.{key}: {step[key]!r} is not visible at level {', '.join(hidden)}")
    if "reach" in block:
        _validate_reach(block["reach"], f"{path}.reach", set(boxes), errs)


def _validate_facts(facts: Json, errs: list[str]) -> None:
    """The part of a page that other skills read: not drawn, but its shape is checked."""
    path = "page.facts"
    if not isinstance(facts, dict):
        errs.append(f"{path}: must be an object")
        return
    if facts.get("version") != 1:
        errs.append(f"{path}.version: must be 1")
    _str(facts, "scope", path, errs, required=False)
    required: dict[str, tuple[str, ...]] = {
        "regions": ("name",),
        "data": ("name", "class"),
        "components": ("id", "label"),
        "costs": ("item", "currency", "as_of", "source"),
        "decisions": ("title", "chosen"),
    }
    for key, fields in required.items():
        for i, item in enumerate(_list(facts, key, path, errs, required=False)):
            ipath = f"{path}.{key}[{i}]"
            if not isinstance(item, dict):
                errs.append(f"{ipath}: must be an object")
                continue
            for field in fields:
                _str(item, field, ipath, errs)
            if key == "costs":
                if not isinstance(item.get("monthly"), int | float) or isinstance(item.get("monthly"), bool):
                    errs.append(f"{ipath}.monthly: must be a number")
                if isinstance(item.get("as_of"), str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["as_of"]):
                    errs.append(f"{ipath}.as_of: must be a date, YYYY-MM-DD")
    for key in ("assumptions", "open"):
        for i, item in enumerate(_list(facts, key, path, errs, required=False)):
            if not isinstance(item, str):
                errs.append(f"{path}.{key}[{i}]: must be a string")


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
    elif kind == "decision":
        _validate_decision(block, path, errs)
    elif kind == "architecture":
        _validate_architecture(block, path, errs)
    elif kind == "model":
        _validate_model(block, path, errs)
    elif kind == "nested":
        _validate_nested(block, path, errs)
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
    if "facts" in page:
        _validate_facts(page["facts"], errs)
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


def validate_site(site: Json) -> list[str]:
    """Return every problem with a site file; each page it lists is checked by validate()."""
    errs: list[str] = []
    if not isinstance(site, dict):
        return ["site: must be a JSON object"]
    _str(site, "title", "site", errs)
    entries = _list(site, "pages", "site", errs)
    if not entries:
        errs.append("site.pages: at least one page")
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        path = f"site.pages[{i}]"
        if not isinstance(entry, dict):
            errs.append(f"{path}: must be an object")
            continue
        _str(entry, "label", path, errs)
        _str(entry, "page", path, errs)
        _str(entry, "group", path, errs, required=False)
        name = entry.get("page")
        if isinstance(name, str):
            if not name.endswith(".json"):
                errs.append(f"{path}.page: must be a page JSON, got {name!r}")
            if name in seen:
                errs.append(f"{path}.page: listed twice: {name!r}")
            seen.add(name)
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
            f'{x2:.1f},{y2:.1f}" marker-end="url(#arrow-{kind})" '
            f'data-a="{_esc(edge["from"])}" data-b="{_esc(edge["to"])}"/>'
        )
        if edge.get("label"):
            mx = (x1 + 3 * c1[0] + 3 * c2[0] + x2) / 8
            my = (y1 + 3 * c1[1] + 3 * c2[1] + y2) / 8
            labels.append(
                f'<text class="edge-label {kind}" x="{mx:.1f}" y="{my - 5:.1f}" text-anchor="middle" '
                f'data-a="{_esc(edge["from"])}" data-b="{_esc(edge["to"])}">'
                f"{_esc(_clip(edge['label'], 28))}</text>"
            )
    for node_id in ids:
        node = nodes[node_id]
        (x0, y0), (w, h) = pos[node_id], size[node_id]
        label = _clip(node["label"])
        note = _clip(node.get("note", ""), 44)
        parts.append(
            f'<g class="node g-{groups[node_id]}" data-k="{_esc(node_id)}" data-label="{_esc(node["label"])}" '
            f'tabindex="0" role="button" aria-pressed="false"><title>{_esc(node["label"])}</title>'
        )
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


# ---------------------------------------------------------------------------- decision


def _decision(block: Json) -> str:
    """Options against factors: the chosen one stands out, an eliminated one keeps what eliminated it."""
    head = (
        '<th scope="col">Option</th>'
        + "".join(f'<th scope="col">{_esc(f)}</th>' for f in block["factors"])
        + '<th scope="col">Status</th>'
    )
    rows = []
    for opt in block["options"]:
        status = opt.get("status", "viable")
        why = f'<div class="why">{_inline(opt["why"])}</div>' if opt.get("why") else ""
        cells = "".join(
            f'<td class="r-{c["rating"]}"><span class="mark">{c["rating"]}</span>{_inline(c.get("text", ""))}</td>'
            for c in opt["cells"]
        )
        by = (
            f'<div class="by">by {_inline(opt["eliminated_by"])}</div>'
            if status == "eliminated" and opt.get("eliminated_by")
            else ""
        )
        rows.append(
            f'<tr class="o-{status}"><th scope="row"><span class="opt">{_inline(opt["label"])}</span>{why}</th>'
            f'{cells}<td class="st"><span class="chip st-{status}">{status}</span>{by}</td></tr>'
        )
    table = f'<table class="dec"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
    return f'<div class="dec-wrap">{table}</div>'


# ---------------------------------------------------------------------------- architecture

ARCH_W = 176  # a component's width
ARCH_ZPAD = 12  # zone padding around its components
ARCH_ZGAP = 58  # the gap between zones, where the links and their labels run
ARCH_HEAD = 46  # the zone label
ARCH_GAP = 18  # between components in a zone
ARCH_PAD = 18
ARCH_BULGE = 34  # a link inside one zone bows out to the right
STOPS = ("human", "user")  # people read text, they do not pass injected instructions on to a tool
RETURNS = ("service", "model", "retrieval", "store", "tool", "system", "guard")  # answer their caller


def _variant_ids(block: Json) -> list[str]:
    """Every variant of the block, the default first; "_" stands for the only one when none are named."""
    return [v["id"] for v in block.get("variants", [])] or ["_"]


def _shown_in(obj: Json, every: list[str]) -> list[str]:
    return [v for v in every if v in obj["variants"]] if "variants" in obj else list(every)


def taint(block: Json, variant: str) -> tuple[set[str], list[tuple[Json, str, list[str]]]]:
    """What untrusted text can reach in one variant: the components it touches, and the shortest path from
    where it enters to every side effect it reaches. Text follows a link the way the request goes, and back
    from a component that answers its caller (a service, model, retrieval, store, tool, outside system or
    guard: the caller reads what it returns). It stops at a person: a human step or a user."""
    every = _variant_ids(block)
    comps = {c["id"]: c for c in block["components"] if variant in _shown_in(c, every)}
    links = [
        link
        for link in block.get("links", [])
        if variant in _shown_in(link, every) and link["from"] in comps and link["to"] in comps
    ]
    near: dict[str, list[str]] = {k: [] for k in comps}
    for link in links:
        near[link["from"]].append(link["to"])
    for link in links:
        if comps[link["to"]].get("kind", "service") in RETURNS:
            near[link["to"]].append(link["from"])
    touched: set[str] = set()
    paths: list[tuple[Json, str, list[str]]] = []
    for entry in (link for link in links if link.get("trust") == "untrusted"):
        start = entry["to"]
        prev: dict[str, str | None] = {start: None}
        queue = [start]
        while queue:
            node = queue.pop(0)
            if comps[node].get("kind", "service") in STOPS:
                continue
            for other in near[node]:
                if other not in prev and other != entry["from"]:
                    prev[other] = node
                    queue.append(other)
        touched.update(prev)
        for node in prev:
            if comps[node].get("side_effect"):
                chain: list[str] = []
                step: str | None = node
                while step is not None:
                    chain.append(step)
                    step = prev[step]
                paths.append((entry, node, [entry["from"], *reversed(chain)]))
    return touched, paths


def reach(block: Json, variant: str) -> tuple[set[str], list[list[str]]]:
    """What the block's `reach` starts can get to in one variant: the components touched, and the shortest
    path to every listed target. Unlike untrusted text it only goes the way the links point, and a `stops`
    component receives it but passes nothing on (masking, a firewall)."""
    spec = block["reach"]
    every = _variant_ids(block)
    comps = {c["id"] for c in block["components"] if variant in _shown_in(c, every)}
    near: dict[str, list[str]] = {k: [] for k in comps}
    for link in block.get("links", []):
        if variant in _shown_in(link, every) and link["from"] in comps and link["to"] in comps:
            near[link["from"]].append(link["to"])
    stops = set(spec.get("stops", []))
    prev: dict[str, str | None] = {k: None for k in spec["from"] if k in comps}
    queue = list(prev)
    while queue:
        node = queue.pop(0)
        if node in stops:
            continue
        for other in near[node]:
            if other not in prev:
                prev[other] = node
                queue.append(other)
    paths: list[list[str]] = []
    for target in spec["targets"]:
        if target in prev:
            chain: list[str] = []
            step: str | None = target
            while step is not None:
                chain.append(step)
                step = prev[step]
            paths.append(list(reversed(chain)))
    return set(prev), paths


def _arch_svg(
    block: Json,
    variant: str,
    every: list[str],
    found: tuple[set[str], list[tuple[Json, str, list[str]]]],
    reached: tuple[set[str], list[list[str]]] | None = None,
) -> str:
    """One variant's diagram. Each variant is laid out on its own, so none leaves gaps for the others."""
    zones = block["zones"]
    comps = {c["id"]: c for c in block["components"] if variant in _shown_in(c, every)}
    links = [link for link in block.get("links", []) if variant in _shown_in(link, every)]
    zone_at = {z["id"]: i for i, z in enumerate(zones)}
    columns = [[k for k, c in comps.items() if c["zone"] == z["id"]] for z in zones]
    # Past six zones the boxes and gaps narrow, so the diagram still fits a laptop screen; labels clip sooner.
    wide = len(zones) > 6
    box_w, zpad, zgap = (156, 10, 42) if wide else (ARCH_W, ARCH_ZPAD, ARCH_ZGAP)
    fits = {"label": (box_w - 24) // 8, "line": (box_w - 24) // 7, "zone": (box_w + 2 * zpad - 20) // 9}
    _order(columns, links, set())

    def box_h(comp: Json) -> int:
        return 64 if comp.get("tech") or comp.get("note") else 48

    col_h = [sum(box_h(comps[k]) for k in col) + ARCH_GAP * max(0, len(col) - 1) for col in columns]
    inner = max([*col_h, 48])
    zone_w = box_w + 2 * zpad
    zone_h = ARCH_HEAD + inner + zpad
    pos: dict[str, tuple[float, float, float, float]] = {}
    for i, col in enumerate(columns):
        x = float(ARCH_PAD + i * (zone_w + zgap) + zpad)
        y = ARCH_PAD + ARCH_HEAD + (inner - col_h[i]) / 2
        for k in col:
            h = float(box_h(comps[k]))
            pos[k] = (x, y, box_w, h)
            y += h + ARCH_GAP
    width = 2 * ARCH_PAD + len(zones) * zone_w + (len(zones) - 1) * zgap
    height = 2 * ARCH_PAD + zone_h

    # Ports: the links on one side of a box are spread along it, ordered by where their other end sits.
    col_of = {k: zone_at[comps[k]["zone"]] for k in comps}
    sides: dict[tuple[str, str], list[tuple[float, int, str]]] = {}
    link_sides: list[tuple[str, str]] = []
    for idx, link in enumerate(links):
        a, b = link["from"], link["to"]
        sa, sb = ("R", "L") if col_of[a] < col_of[b] else ("L", "R") if col_of[a] > col_of[b] else ("R", "R")
        link_sides.append((sa, sb))
        sides.setdefault((a, sa), []).append((pos[b][1] + pos[b][3] / 2, idx, "from"))
        sides.setdefault((b, sb), []).append((pos[a][1] + pos[a][3] / 2, idx, "to"))
    port: dict[tuple[int, str], tuple[float, float]] = {}
    for (k, side), items in sides.items():
        x, y, w, h = pos[k]
        for n, (_, idx, end) in enumerate(sorted(items)):
            port[(idx, end)] = (x + w if side == "R" else x, y + h * (n + 1) / (len(items) + 1))
    if any(
        sa == sb and col_of[link["from"]] == len(zones) - 1 for link, (sa, sb) in zip(links, link_sides, strict=True)
    ):
        width += ARCH_BULGE

    touched, paths = found
    risk = {target for _, target, _ in paths}
    on_path = {pair for _, _, p in paths for pair in pairwise(p)}
    reach_hit = {p[-1] for p in reached[1]} if reached else set()
    reach_on = {pair for p in reached[1] for pair in pairwise(p)} if reached else set()
    v = _esc(variant)
    parts = [
        f'<svg class="arch-svg" data-variant="{v}" role="img" aria-label="{_esc(block.get("title", "Architecture"))}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" style="width:100%;max-width:{width:.0f}px;'
        f'min-width:{min(width, max(width * 0.72, 760)):.0f}px" xmlns="http://www.w3.org/2000/svg"><defs>'
    ]
    for kind in ("base", "red", "in", "out", "hot"):
        parts.append(
            f'<marker id="arch-arrow-{kind}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="ah-{kind}"/></marker>'
        )
    parts.append("</defs>")
    for i, zone in enumerate(zones):
        zx = ARCH_PAD + i * (zone_w + zgap)
        parts.append(
            f'<g class="zone"><rect class="zone-bg" x="{zx:.1f}" y="{ARCH_PAD:.1f}" width="{zone_w:.1f}" '
            f'height="{zone_h:.1f}" rx="12"/><text class="zone-label" x="{zx + 13:.1f}" y="{ARCH_PAD + 28:.1f}">'
            f"{_esc(_clip(zone['label'].upper(), fits['zone']))}</text></g>"
        )
    labels: list[str] = []
    labelled: set[tuple[str, str]] = set()  # ten sources "daily" into one box need the word once
    for idx, link in enumerate(links):
        a, b = link["from"], link["to"]
        (x1, y1), (x2, y2) = port[(idx, "from")], port[(idx, "to")]
        sa, sb = link_sides[idx]
        if sa == sb:
            c1, c2 = (x1 + ARCH_BULGE, y1), (x2 + ARCH_BULGE, y2)
        else:
            dx = max(28.0, abs(x2 - x1) / 2)
            c1 = (x1 + dx if sa == "R" else x1 - dx, y1)
            c2 = (x2 - dx if sb == "L" else x2 + dx, y2)
        classes = ["link"]
        if link.get("trust") == "untrusted":
            classes.append("untrusted")
        if link.get("flag"):
            classes.append(f"f-{link['flag']}")
        attrs = (
            f'data-a="{_esc(a)}" data-b="{_esc(b)}" data-v="{v}" '
            f'data-path="{v if (a, b) in on_path or (b, a) in on_path else ""}"'
        )
        if reached:
            attrs += f' data-rpath="{v if (a, b) in reach_on else ""}"'
        parts.append(
            f'<path class="{" ".join(classes)}" d="M{x1:.1f},{y1:.1f} C{c1[0]:.1f},{c1[1]:.1f} '
            f'{c2[0]:.1f},{c2[1]:.1f} {x2:.1f},{y2:.1f}" {attrs}/>'
        )
        if link.get("label") and (b, link["label"]) not in labelled:
            labelled.add((b, link["label"]))
            # Beside the arrowhead, in the gap before the box it points at: a long link would put a
            # midpoint label on top of the zones it crosses.
            if sa == sb:
                lx, ly, anchor = max(x1, x2) + ARCH_BULGE * 0.75 + 5, (y1 + y2) / 2 + 4, "start"
            elif sb == "L":
                lx, ly, anchor = x2 - 8, y2 - 6, "end"
            else:
                lx, ly, anchor = x2 + 8, y2 - 6, "start"
            labels.append(
                f'<text class="link-label{" untrusted" if "untrusted" in classes else ""}" x="{lx:.1f}" '
                f'y="{ly:.1f}" text-anchor="{anchor}" {attrs}>{_esc(_clip(link["label"], 14))}</text>'
            )
    for k, comp in comps.items():
        x, y, w, h = pos[k]
        kind = comp.get("kind", "service")
        classes = ["comp", f"k-{kind}"]
        if comp.get("side_effect"):
            classes.append("se")
        if comp.get("flag"):
            classes.append(f"f-{comp['flag']}")
        if "variants" in comp and len(every) > 1:
            classes.append("vonly")
        caption = KINDS[kind] + (" · acts" if comp.get("side_effect") else "")
        marks = (
            f' data-reach="{v if k in reached[0] else ""}" data-rhit="{v if k in reach_hit else ""}"' if reached else ""
        )
        parts.append(
            f'<g class="{" ".join(classes)}" data-k="{_esc(k)}" data-label="{_esc(comp["label"])}" '
            f'data-v="{v}" data-taint="{v if k in touched else ""}" data-risk="{v if k in risk else ""}"{marks} '
            f'tabindex="0" role="button" aria-pressed="false"><title>{_esc(comp["label"])}</title>'
            f'<rect class="plate" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8"/>'
            f'<rect class="bar" x="{x + 1:.1f}" y="{y + 7:.1f}" width="3.5" height="{h - 14:.1f}" rx="1.5"/>'
            f'<text class="ck" x="{x + 16:.1f}" y="{y + 17:.1f}">{_esc(_clip(caption.upper(), fits["line"]))}</text>'
            f'<text class="cl" x="{x + 16:.1f}" y="{y + 36:.1f}">{_esc(_clip(comp["label"], fits["label"]))}</text>'
        )
        line = comp.get("tech") or comp.get("note")
        if line:
            parts.append(f'<text class="ct" x="{x + 16:.1f}" y="{y + 53:.1f}">{_esc(_clip(line, fits["line"]))}</text>')
        if comp.get("flag"):
            parts.append(f'<circle class="flag" cx="{x + w - 13:.1f}" cy="{y + 13:.1f}" r="4.5"/>')
        parts.append("</g>")
    parts.extend(labels)
    parts.append("</svg>")
    return "".join(parts)


def _arch_card(comp: Json, block: Json, names: dict[str, str], every: list[str], labels: dict[str, str]) -> str:
    kind = comp.get("kind", "service")
    zone = next(z["label"] for z in block["zones"] if z["id"] == comp["zone"])
    chips = [f'<span class="chip">{_esc(zone)}</span>', f'<span class="chip">{_esc(KINDS[kind])}</span>']
    if comp.get("side_effect"):
        chips.append('<span class="chip se">side effect</span>')
    if comp.get("flag"):
        chips.append(
            f'<span class="chip sev-{"high" if comp["flag"] == "bad" else "medium"}">'
            f"{'risk' if comp['flag'] == 'bad' else 'watch'}</span>"
        )
    body = [f"<header>{''.join(chips)}</header><h4>{_inline(comp['label'])}</h4>"]
    if comp.get("tech"):
        body.append(f'<div class="where">{_esc(comp["tech"])}</div>')
    if comp.get("note"):
        body.append(f'<div class="evidence">{_paragraphs(comp["note"])}</div>')
    if comp.get("details"):
        rows = "".join(f"<dt>{_cell(k)}</dt><dd>{_cell(v)}</dd>" for k, v in comp["details"])
        body.append(f'<dl class="kv">{rows}</dl>')

    def listing(title: str, items: list[tuple[str, Json]]) -> str:
        if not items:
            return ""
        lis = "".join(
            f"<li>{_esc(names[other])}"
            + (f" · {_inline(link['label'])}" if link.get("label") else "")
            + (' <span class="chip untrusted">untrusted</span>' if link.get("trust") == "untrusted" else "")
            + (
                f' <span class="only">({_esc(", ".join(labels[v] for v in _shown_in(link, every)))})</span>'
                if "variants" in link and len(every) > 1
                else ""
            )
            + "</li>"
            for other, link in items
        )
        return f'<div><span class="fix-label">{title}</span><ul>{lis}</ul></div>'

    links = block.get("links", [])
    io = listing("Sends to", [(link["to"], link) for link in links if link["from"] == comp["id"]]) + listing(
        "Receives from", [(link["from"], link) for link in links if link["to"] == comp["id"]]
    )
    if io:
        body.append(f'<div class="io">{io}</div>')
    if "variants" in comp and len(every) > 1:
        only = ", ".join(labels[v] for v in _shown_in(comp, every))
        body.append(f'<p class="only">Only in: {_esc(only)}</p>')
    return f'<article class="arch-card plate" data-k="{_esc(comp["id"])}">{"".join(body)}</article>'


def _architecture(block: Json, draw: Any = None, cards_from: Json | None = None) -> str:
    """`draw` replaces the diagram and `cards_from` the block the cards are written from: the nested block
    shares everything else, because a level of it is a variant."""
    draw = draw or _arch_svg
    every = _variant_ids(block)
    labels = {v["id"]: v["label"] for v in block.get("variants", [])} or {"_": ""}
    names = {c["id"]: c["label"] for c in block["components"]}
    tainted = {v: taint(block, v) for v in every}
    spec = block.get("reach")
    reaches = {v: reach(block, v) for v in every} if spec else {}
    links = block.get("links", [])
    flows = block.get("flows", [])
    variants = block.get("variants", [])
    untrusted = any(link.get("trust") == "untrusted" for link in links)

    controls = []
    if len(variants) > 1:
        buttons = "".join(
            f'<button type="button" data-set-variant="{_esc(v["id"])}" aria-pressed="{"true" if i == 0 else "false"}"'
            f">{_esc(v['label'])}</button>"
            for i, v in enumerate(variants)
        )
        controls.append(f'<div class="seg" role="group" aria-label="Variant">{buttons}</div>')
    if untrusted:
        controls.append('<button type="button" class="arch-trust" aria-pressed="false">Trust boundaries</button>')
    if spec:
        controls.append(f'<button type="button" class="arch-reach" aria-pressed="false">{_esc(spec["label"])}</button>')
    if flows:
        buttons = "".join(
            f'<button type="button" data-set-flow="{_esc(f["id"])}" aria-pressed="false">{_esc(f["title"])}</button>'
            for f in flows
        )
        controls.append(f'<div class="seg" role="group" aria-label="Request flows">{buttons}</div>')
        controls.append(
            '<span class="stepper"><button type="button" class="prev" aria-label="Previous step">&#8249;</button>'
            '<button type="button" class="play">Play</button>'
            '<button type="button" class="next" aria-label="Next step">&#8250;</button>'
            '<span class="count"></span></span>'
        )
    controls_html = f'<div class="arch-controls">{"".join(controls)}</div>' if controls else ""

    kinds = [k for k in KINDS if any(c.get("kind", "service") == k for c in block["components"])]
    legend = [f'<span class="legend-item"><i class="swatch k-{k}"></i>{_esc(KINDS[k])}</span>' for k in kinds]
    if untrusted:
        legend.append('<span class="legend-item"><i class="swatch untrusted"></i>untrusted text</span>')
    if any(c.get("side_effect") for c in block["components"]):
        legend.append('<span class="legend-item"><i class="swatch se"></i>side effect</span>')
    if cards_from is None and len(every) > 1 and any("variants" in c for c in block["components"]):
        legend.append('<span class="legend-item"><i class="swatch vonly"></i>only in some variants</span>')

    notes = "".join(
        f'<p class="arch-vnote" data-variant="{_esc(v["id"])}"><strong>{_esc(v["label"])}:</strong> '
        f"{_inline(v['note'])}</p>"
        for v in variants
        if v.get("note")
    )
    flows_html = ""
    if flows:
        items = []
        for flow in flows:
            steps = "".join(
                f'<li data-a="{_esc(s["from"])}" data-b="{_esc(s["to"])}"><span class="who">'
                f'{_esc(names[s["from"]])} → {_esc(names[s["to"]])}</span><span class="what">{_inline(s["text"])}'
                "</span></li>"
                for s in flow["steps"]
            )
            only = (
                f' <span class="only">({_esc(", ".join(labels[v] for v in _shown_in(flow, every)))})</span>'
                if "variants" in flow and len(every) > 1
                else ""
            )
            items.append(
                f'<div class="arch-flow" data-flow="{_esc(flow["id"])}" '
                f'data-v="{_esc(" ".join(_shown_in(flow, every)))}"><h4>{_inline(flow["title"])}{only}</h4>'
                f'<ol class="flow-steps">{steps}</ol></div>'
            )
        flows_html = (
            '<div class="arch-flows"><p class="arch-hint flows-hint">Pick a flow above to walk a request '
            f"through it, step by step, with the buttons or the arrow keys</p>{''.join(items)}</div>"
        )
    source = cards_from or block
    cards = "".join(_arch_card(c, source, names, every, labels) for c in source["components"])
    cards_html = (
        '<div class="arch-cards"><p class="arch-hint comp-hint">Click a component: what it does, what it uses, '
        f"what happens when it fails</p>{cards}</div>"
    )

    trust_html = ""
    if untrusted:
        many = len(every) > 1
        rows = []
        for v in every:
            # One row per side effect: every way in that reaches it, and the shortest path.
            reached: dict[str, list[tuple[Json, list[str]]]] = {}
            for entry, target, path in tainted[v][1]:
                reached.setdefault(target, []).append((entry, path))
            for target, ways in reached.items():
                entries = list(dict.fromkeys(f"{names[e['from']]} → {names[e['to']]}" for e, _ in ways))
                shortest = min((path for _, path in ways), key=len)
                rows.append(
                    ([labels[v]] if many else [])
                    + [names[target], "; ".join(entries), " → ".join(names[p] for p in shortest)]
                )
        if rows:
            columns = (["Variant"] if many else []) + ["Side effect", "Untrusted text enters at", "Shortest path"]
            head = "".join(f"<th>{_esc(c)}</th>" for c in columns)
            body = "".join("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in rows)
            trust_body = (
                f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
            )
        else:
            trust_body = (
                '<div class="callout plate labelled c-ok"><span class="label">ok</span><p>No path from untrusted '
                "text to a side effect that does not pass a person first.</p></div>"
            )
        trust_html = f'<div class="arch-trustlist"><h3>Where untrusted text can reach an action</h3>{trust_body}</div>'

    reach_html = ""
    if spec:
        many = len(every) > 1
        rows = [
            ([labels[v]] if many else []) + [names[p[-1]], names[p[0]], " → ".join(names[k] for k in p)]
            for v in every
            for p in reaches[v][1]
        ]
        if rows:
            columns = (["Variant"] if many else []) + ["Reaches", "Starts at", "Shortest path"]
            head = "".join(f"<th>{_esc(c)}</th>" for c in columns)
            body = "".join("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in rows)
            reach_body = (
                f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
            )
        else:
            reach_body = (
                '<div class="callout plate labelled c-ok"><span class="label">ok</span><p>None of the listed '
                "targets is reached: every path stops first.</p></div>"
            )
        reach_html = f'<div class="arch-trustlist"><h3>{_inline(spec["label"])}: what it reaches</h3>{reach_body}</div>'

    # One diagram per variant. The script shows the chosen one; without it every variant is drawn,
    # each under its name.
    stage = "".join(
        (f'<p class="arch-vlabel">{_esc(labels[v])}</p>' if len(every) > 1 else "")
        + draw(block, v, every, tainted[v], reaches.get(v))
        for v in every
    )
    return (
        f'<div class="arch" data-default="{_esc(every[0])}">{controls_html}'
        f'<div class="arch-stage">{stage}</div>'
        f'<div class="arch-caption" aria-live="polite"></div><div class="legend">{"".join(legend)}</div>'
        + (f'<div class="arch-vnotes">{notes}</div>' if notes else "")
        + f"{cards_html}{flows_html}{trust_html}{reach_html}</div>"
    )


NEST_W = 180  # a closed box's width
NEST_PAD = 18  # inside an open box
NEST_HEAD = 50  # an open box's title
NEST_GAP_X = 68  # between columns, where the links run
NEST_GAP_Y = 18  # between boxes in a column
NEST_MARGIN = 22
NEST_MAX_COLUMNS = {1: 4}  # inside a box; deeper boxes get 3. Long chains fold, so a level still fits a screen


def _nest_views(block: Json) -> list[tuple[str, set[str]]]:
    """(level id, the boxes open at that level). Without levels, one view with everything open."""
    if block.get("levels"):
        return [(level["id"], set(level["open"])) for level in block["levels"]]
    return [("_", {b["parent"] for b in block["boxes"] if b.get("parent")})]


def _nest_visible(block: Json, opened: set[str]) -> set[str]:
    """A box shows when every box around it is open."""
    parent = {b["id"]: b.get("parent") for b in block["boxes"]}

    def shows(key: str) -> bool:
        at = parent[key]
        while at is not None:
            if at not in opened:
                return False
            at = parent[at]
        return True

    return {key for key in parent if shows(key)}


def _nest_links(block: Json, visible: set[str]) -> list[Json]:
    """The links as seen at one level: an end inside a closed box moves out to that box, and links that
    end up joining the same two boxes become one."""
    parent = {b["id"]: b.get("parent") for b in block["boxes"]}

    def outward(key: str) -> str:
        while key not in visible:
            key = parent[key]
        return key

    def around(key: str) -> set[str]:
        found: set[str] = set()
        at = parent[key]
        while at is not None:
            found.add(at)
            at = parent[at]
        return found

    merged: dict[tuple[str, str], list[Json]] = {}
    for link in block.get("links", []):
        a, b = outward(link["from"]), outward(link["to"])
        if a != b and a not in around(b) and b not in around(a):
            merged.setdefault((a, b), []).append(link)
    result = []
    for (a, b), group in merged.items():
        lifted: Json = {"from": a, "to": b}
        names = list(dict.fromkeys(item["label"] for item in group if item.get("label")))
        if names:
            lifted["label"] = names[0] + (f" +{len(names) - 1}" if len(names) > 1 else "")
        if any(item.get("trust") == "untrusted" for item in group):
            lifted["trust"] = "untrusted"
        flags = {item.get("flag") for item in group}
        if flags & set(FLAGS):
            lifted["flag"] = "bad" if "bad" in flags else "warn"
        result.append(lifted)
    return result


def _nest_as_architecture(block: Json) -> tuple[Json, Json]:
    """The block as an architecture block whose variants are its levels, and the one its cards are written from."""
    views = _nest_views(block)
    has_levels = bool(block.get("levels"))
    labels = {b["id"]: b["label"] for b in block["boxes"]}
    parents = list(dict.fromkeys(b["parent"] for b in block["boxes"] if b.get("parent")))
    zones = [{"id": "_top", "label": "Top level"}, *({"id": k, "label": labels[k]} for k in parents)]
    arch: Json = {"type": "architecture", "zones": zones, "components": [], "links": []}
    if block.get("title"):
        arch["title"] = block["title"]
    plain = []
    for box in block["boxes"]:
        comp = {**box, "zone": box.get("parent", "_top")}
        plain.append(dict(comp))
        if has_levels:
            comp["variants"] = [v for v, opened in views if box["id"] in _nest_visible(block, opened)]
        arch["components"].append(comp)
    for name, opened in views:
        for link in _nest_links(block, _nest_visible(block, opened)):
            arch["links"].append({**link, "variants": [name]} if has_levels else link)
    if has_levels:
        arch["variants"] = [{k: level[k] for k in ("id", "label", "note") if k in level} for level in block["levels"]]
    for key in ("flows", "reach"):
        if key in block:
            arch[key] = block[key]
    raw_links = [{k: v for k, v in link.items() if k != "variants"} for link in block.get("links", [])]
    return arch, {"zones": zones, "components": plain, "links": raw_links}


def _nest_svg(
    block: Json,
    variant: str,
    every: list[str],
    found: tuple[set[str], list[tuple[Json, str, list[str]]]],
    reached: tuple[set[str], list[list[str]]] | None = None,
) -> str:
    """One level: open boxes hold their children, laid out left to right with the graph helpers, recursively."""
    comps = {c["id"]: c for c in block["components"] if variant in _shown_in(c, every)}
    links = [link for link in block.get("links", []) if variant in _shown_in(link, every)]
    children: dict[str | None, list[str]] = {}
    for key, comp in comps.items():
        children.setdefault(comp.get("parent"), []).append(key)

    def inside(key: str, group: set[str]) -> str | None:
        at: str | None = key
        while at is not None and at not in group:
            at = comps[at].get("parent")
        return at

    def closed_h(comp: Json) -> int:
        return 64 if comp.get("tech") or comp.get("note") else 48

    sizes: dict[str, tuple[float, float]] = {}
    offsets: dict[str, tuple[float, float]] = {}

    def place(kids: list[str], deep: int = 0) -> tuple[float, float]:
        """Lay out siblings; return the width and height they take. Offsets are relative to their corner."""
        group = set(kids)
        pairs: dict[tuple[str, str], None] = {}
        for link in links:
            a, b = inside(link["from"], group), inside(link["to"], group)
            if a and b and a != b:
                pairs[(a, b)] = None
        # A store takes no column of its own: whoever writes it and whoever reads it count as joined, and
        # it stands under its last writer. Chains of service, queue, service, database stay short.
        stores = {k for k in kids if comps[k].get("kind") == "store" and not children.get(k)}
        into = {k: [a for a, b in pairs if b == k and a not in stores] for k in stores}
        joined = {(a, b) for a, b in pairs if a not in stores and b not in stores}
        for k in stores:
            out_of = [b for a, b in pairs if a == k and b not in stores]
            joined |= {(a, b) for a in into[k] for b in out_of if a != b}
        edges = [{"from": a, "to": b} for a, b in sorted(joined)]
        rest = [k for k in kids if k not in stores]
        layer, back = _layers(rest, edges) if rest else ({}, set())
        for k in stores:
            near = into[k] or [b for a, b in pairs if a == k and b not in stores]
            layer[k] = max((layer[n] for n in near), default=0)
        count = max(layer.values()) + 1
        most = NEST_MAX_COLUMNS.get(deep, 3) if deep else count
        if count > most:
            layer = {k: v * most // count for k, v in layer.items()}
        columns: list[list[str]] = [[] for _ in range(max(layer.values()) + 1)]
        for key in kids:
            columns[layer[key]].append(key)
        _order(columns, edges, back)
        for col in columns:
            col.sort(key=lambda k: k in stores)
        for key in kids:
            measure(key, deep + 1)
        widths = [max(sizes[k][0] for k in col) for col in columns]
        heights = [sum(sizes[k][1] for k in col) + NEST_GAP_Y * (len(col) - 1) for col in columns]
        inner = max(heights)
        x = 0.0
        for c, col in enumerate(columns):
            y = (inner - heights[c]) / 2
            for key in col:
                offsets[key] = (x + (widths[c] - sizes[key][0]) / 2, y)
                y += sizes[key][1] + NEST_GAP_Y
            x += widths[c] + NEST_GAP_X
        return x - NEST_GAP_X, inner

    def measure(key: str, deep: int) -> None:
        kids = children.get(key)
        if not kids:
            sizes[key] = (float(NEST_W), float(closed_h(comps[key])))
            return
        w, h = place(kids, deep)
        sizes[key] = (max(w, NEST_W) + 2 * NEST_PAD, h + NEST_HEAD + NEST_PAD)

    roots = children.get(None, [])
    total_w, total_h = place(roots)
    pos: dict[str, tuple[float, float, float, float]] = {}

    def settle(kids: list[str], ox: float, oy: float) -> None:
        for key in kids:
            x, y = ox + offsets[key][0], oy + offsets[key][1]
            pos[key] = (x, y, *sizes[key])
            if children.get(key):
                settle(children[key], x + NEST_PAD, y + NEST_HEAD)

    settle(roots, float(NEST_MARGIN), float(NEST_MARGIN))
    width, height = total_w + 2 * NEST_MARGIN, total_h + 2 * NEST_MARGIN

    def sides_of(a: str, b: str) -> tuple[str, str]:
        ax, ay, aw, ah = pos[a]
        bx, by, bw, _ = pos[b]
        if ax + aw <= bx:
            return "R", "L"
        if bx + bw <= ax:
            return "L", "R"
        return ("B", "T") if ay + ah <= by else ("T", "B")

    link_sides = [sides_of(link["from"], link["to"]) for link in links]

    def in_the_way(a: str, b: str, sides: tuple[str, str]) -> float | None:
        """The lowest bottom edge among the closed boxes a straight link would run through, if any."""
        ax, ay, aw, ah = pos[a]
        bx, by, bw, bh = pos[b]
        x1, y1 = (ax + aw if sides[0] == "R" else ax), ay + ah / 2
        x2, y2 = (bx + bw if sides[1] == "R" else bx), by + bh / 2
        bottoms = []
        for key, (x, y, w, h) in pos.items():
            if key not in (a, b) and not children.get(key):
                for t in (i / 40 for i in range(1, 40)):
                    if x - 2 <= x1 + (x2 - x1) * t <= x + w + 2 and y - 2 <= y1 + (y2 - y1) * t <= y + h + 2:
                        bottoms.append(y + h)
                        break
        return max(bottoms) if bottoms else None

    # A link that would cross a box goes underneath it instead: out of the bottom, into the bottom.
    arcs: dict[int, float] = {}
    for idx, link in enumerate(links):
        a, b = link["from"], link["to"]
        if link_sides[idx][0] in "RL" and (low := in_the_way(a, b, link_sides[idx])) is not None:
            base = max(pos[a][1] + pos[a][3], pos[b][1] + pos[b][3])
            lowest = max(low, base) + 16 + 10 * len(arcs)
            arcs[idx] = base + (lowest - base) / 0.75
            height = max(height, lowest + NEST_MARGIN)
            link_sides[idx] = ("B", "B")
    at_side: dict[tuple[str, str], list[tuple[float, int, str]]] = {}
    for idx, link in enumerate(links):
        a, b = link["from"], link["to"]
        sa, sb = link_sides[idx]
        at_side.setdefault((a, sa), []).append((_nest_along(pos[b], sa), idx, "from"))
        at_side.setdefault((b, sb), []).append((_nest_along(pos[a], sb), idx, "to"))
    port: dict[tuple[int, str], tuple[float, float]] = {}
    for (key, side), items in at_side.items():
        x, y, w, h = pos[key]
        for n, (_, idx, end) in enumerate(sorted(items)):
            share = (n + 1) / (len(items) + 1)
            port[(idx, end)] = {
                "R": (x + w, y + h * share),
                "L": (x, y + h * share),
                "T": (x + w * share, y),
                "B": (x + w * share, y + h),
            }[side]

    touched, paths = found
    risk = {target for _, target, _ in paths}
    on_path = {pair for _, _, p in paths for pair in pairwise(p)}
    reach_hit = {p[-1] for p in reached[1]} if reached else set()
    reach_on = {pair for p in reached[1] for pair in pairwise(p)} if reached else set()
    v = _esc(variant)
    parts = [
        f'<svg class="arch-svg nested" data-variant="{v}" role="img" '
        f'aria-label="{_esc(block.get("title", "Architecture"))}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'style="width:100%;max-width:{width:.0f}px;min-width:{min(width, max(width * 0.72, 720)):.0f}px" '
        'xmlns="http://www.w3.org/2000/svg"><defs>'
    ]
    for kind in ("base", "red", "in", "out", "hot"):
        parts.append(
            f'<marker id="arch-arrow-{kind}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="ah-{kind}"/></marker>'
        )
    parts.append("</defs>")

    def opening(key: str, comp: Json, extra: list[str]) -> str:
        kind = comp.get("kind", "service")
        classes = ["comp", f"k-{kind}", *extra]
        if comp.get("side_effect"):
            classes.append("se")
        if comp.get("flag"):
            classes.append(f"f-{comp['flag']}")
        marks = (
            f' data-reach="{v if key in reached[0] else ""}" data-rhit="{v if key in reach_hit else ""}"'
            if reached
            else ""
        )
        return (
            f'<g class="{" ".join(classes)}" data-k="{_esc(key)}" data-label="{_esc(comp["label"])}" '
            f'data-v="{v}" data-taint="{v if key in touched else ""}" data-risk="{v if key in risk else ""}"{marks} '
            f'tabindex="0" role="button" aria-pressed="false"><title>{_esc(comp["label"])}</title>'
        )

    def depth(key: str) -> int:
        count, at = 0, comps[key].get("parent")
        while at is not None:
            count, at = count + 1, comps[at].get("parent")
        return count

    for key in sorted((k for k in comps if children.get(k)), key=depth):
        comp = comps[key]
        x, y, w, h = pos[key]
        parts.append(opening(key, comp, ["open-box"]))
        parts.append(f'<rect class="plate" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="12"/>')
        caption = KINDS[comp.get("kind", "service")].upper()
        parts.append(f'<text class="ck" x="{x + 14:.1f}" y="{y + 18:.1f}">{_esc(caption)}</text>')
        title = _clip(comp["label"], int((w - 28) // 8))
        parts.append(f'<text class="cl" x="{x + 14:.1f}" y="{y + 38:.1f}">{_esc(title)}</text>')
        if comp.get("tech"):
            parts.append(
                f'<text class="ct" x="{x + w - 14:.1f}" y="{y + 18:.1f}" text-anchor="end">'
                f"{_esc(_clip(comp['tech'], int((w - 28) // 14)))}</text>"
            )
        if comp.get("flag"):
            parts.append(f'<circle class="flag" cx="{x + w - 13:.1f}" cy="{y + 34:.1f}" r="4.5"/>')
        parts.append("</g>")
    labels: list[str] = []
    labelled: set[tuple[str, str]] = set()
    pull = {"R": (1, 0), "L": (-1, 0), "T": (0, -1), "B": (0, 1)}
    for idx, link in enumerate(links):
        a, b = link["from"], link["to"]
        (x1, y1), (x2, y2) = port[(idx, "from")], port[(idx, "to")]
        sa, sb = link_sides[idx]
        reach_x, reach_y = max(30.0, abs(x2 - x1) / 2), max(24.0, abs(y2 - y1) / 2)
        c1 = (x1 + pull[sa][0] * reach_x, y1 + pull[sa][1] * reach_y)
        c2 = (x2 + pull[sb][0] * reach_x, y2 + pull[sb][1] * reach_y)
        if idx in arcs:
            c1, c2 = (x1, arcs[idx]), (x2, arcs[idx])
        classes = ["link"]
        if link.get("trust") == "untrusted":
            classes.append("untrusted")
        if link.get("flag"):
            classes.append(f"f-{link['flag']}")
        attrs = (
            f'data-a="{_esc(a)}" data-b="{_esc(b)}" data-v="{v}" '
            f'data-path="{v if (a, b) in on_path or (b, a) in on_path else ""}"'
        )
        if reached:
            attrs += f' data-rpath="{v if (a, b) in reach_on else ""}"'
        parts.append(
            f'<path class="{" ".join(classes)}" d="M{x1:.1f},{y1:.1f} C{c1[0]:.1f},{c1[1]:.1f} '
            f'{c2[0]:.1f},{c2[1]:.1f} {x2:.1f},{y2:.1f}" {attrs}/>'
        )
        if link.get("label") and (b, link["label"]) not in labelled:
            labelled.add((b, link["label"]))
            lx, ly, anchor = {
                "L": (x2 - 8, y2 - 6, "end"),
                "R": (x2 + 8, y2 - 6, "start"),
                "T": (x2 + 7, y2 - 9, "start"),
                "B": (x2 + 7, y2 + 16, "start"),
            }[sb]
            labels.append(
                f'<text class="link-label{" untrusted" if "untrusted" in classes else ""}" x="{lx:.1f}" '
                f'y="{ly:.1f}" text-anchor="{anchor}" {attrs}>{_esc(_clip(link["label"], 16))}</text>'
            )
    for key, comp in comps.items():
        if children.get(key):
            continue
        x, y, w, h = pos[key]
        caption = KINDS[comp.get("kind", "service")] + (" · acts" if comp.get("side_effect") else "")
        parts.append(opening(key, comp, []))
        parts.append(
            f'<rect class="plate" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8"/>'
            f'<rect class="bar" x="{x + 1:.1f}" y="{y + 7:.1f}" width="3.5" height="{h - 14:.1f}" rx="1.5"/>'
            f'<text class="ck" x="{x + 16:.1f}" y="{y + 17:.1f}">{_esc(_clip(caption.upper(), 22))}</text>'
            f'<text class="cl" x="{x + 16:.1f}" y="{y + 36:.1f}">{_esc(_clip(comp["label"], 21))}</text>'
        )
        line = comp.get("tech") or comp.get("note")
        if line:
            parts.append(f'<text class="ct" x="{x + 16:.1f}" y="{y + 53:.1f}">{_esc(_clip(line, 24))}</text>')
        if comp.get("flag"):
            parts.append(f'<circle class="flag" cx="{x + w - 13:.1f}" cy="{y + 13:.1f}" r="4.5"/>')
        parts.append("</g>")
    parts.extend(labels)
    parts.append("</svg>")
    return "".join(parts)


def _nest_along(rect: tuple[float, float, float, float], side: str) -> float:
    """Where the other end sits along a side, so links leave a box without crossing each other."""
    x, y, w, h = rect
    return x + w / 2 if side in "TB" else y + h / 2


def _nested(block: Json) -> str:
    arch, cards = _nest_as_architecture(block)
    return _architecture(arch, draw=_nest_svg, cards_from=cards)


MODEL_W = 236  # a table's width
MODEL_GAP_X = 108  # between columns, where the relations run
MODEL_GAP_Y = 20  # between tables in a column
MODEL_PAD = 24
MODEL_KEYS = 3  # key columns shown on the box; the card lists them all
MODEL_BULGE = 40  # a relation inside one column bows out to the right


def _model_keys(table: Json) -> list[str]:
    return [c["name"] for c in table["columns"] if c.get("key") == "pk"]


def _model_h(table: Json) -> int:
    return 66 + 17 * max(1, min(len(_model_keys(table)), MODEL_KEYS))


def _model_svg(block: Json) -> str:
    """Tables left to right: the many side of a relation stands left of the one side, so a star reads
    fact, then dimensions, and a vault link, then its hubs."""
    tables = {t["id"]: t for t in block["tables"]}
    relations = block.get("relations", [])
    flipped = [r.get("cardinality", "n:1") == "1:n" for r in relations]
    edges = [
        {"from": r["to"], "to": r["from"]} if flip else {"from": r["from"], "to": r["to"]}
        for r, flip in zip(relations, flipped, strict=True)
    ]
    layer, back = _layers(list(tables), edges)
    columns: list[list[str]] = [[] for _ in range(max(layer.values()) + 1)]
    for key in tables:
        columns[layer[key]].append(key)
    _order(columns, edges, back)
    heights = [sum(_model_h(tables[k]) for k in col) + MODEL_GAP_Y * max(0, len(col) - 1) for col in columns]
    inner = max(heights)
    pos: dict[str, tuple[float, float, float]] = {}
    for i, col in enumerate(columns):
        x = float(MODEL_PAD + i * (MODEL_W + MODEL_GAP_X))
        y = MODEL_PAD + (inner - heights[i]) / 2
        for key in col:
            pos[key] = (x, y, float(_model_h(tables[key])))
            y += _model_h(tables[key]) + MODEL_GAP_Y
    width = 2 * MODEL_PAD + len(columns) * MODEL_W + (len(columns) - 1) * MODEL_GAP_X + MODEL_BULGE
    height = 2 * MODEL_PAD + inner

    sides: dict[tuple[str, str], list[tuple[float, int, str]]] = {}
    side_of: list[tuple[str, str]] = []
    for idx, edge in enumerate(edges):
        a, b = edge["from"], edge["to"]
        sa, sb = ("R", "L") if layer[a] < layer[b] else ("L", "R") if layer[a] > layer[b] else ("R", "R")
        side_of.append((sa, sb))
        sides.setdefault((a, sa), []).append((pos[b][1] + pos[b][2] / 2, idx, "from"))
        sides.setdefault((b, sb), []).append((pos[a][1] + pos[a][2] / 2, idx, "to"))
    port: dict[tuple[int, str], tuple[float, float]] = {}
    for (key, side), items in sides.items():
        x, y, h = pos[key]
        for n, (_, idx, end) in enumerate(sorted(items)):
            port[(idx, end)] = (x + MODEL_W if side == "R" else x, y + h * (n + 1) / (len(items) + 1))

    parts = [
        f'<svg class="model-svg" role="img" aria-label="{_esc(block.get("title", "Data model"))}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" style="width:100%;max-width:{width:.0f}px;'
        f'min-width:{min(width, max(width * 0.72, 720)):.0f}px" xmlns="http://www.w3.org/2000/svg"><defs>'
    ]
    for name in ("base", "on"):
        parts.append(
            f'<marker id="model-arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="mh-{name}"/></marker>'
        )
    parts.append("</defs>")
    labels: list[str] = []
    for idx, edge in enumerate(edges):
        rel = relations[idx]
        (x1, y1), (x2, y2) = port[(idx, "from")], port[(idx, "to")]
        sa, sb = side_of[idx]
        if sa == sb:
            c1, c2 = (x1 + MODEL_BULGE, y1), (x2 + MODEL_BULGE, y2)
        else:
            dx = max(30.0, abs(x2 - x1) / 2)
            c1 = (x1 + dx if sa == "R" else x1 - dx, y1)
            c2 = (x2 - dx if sb == "L" else x2 + dx, y2)
        cardinality = rel.get("cardinality", "n:1")
        attrs = f'data-a="{_esc(edge["from"])}" data-b="{_esc(edge["to"])}"'
        many = " many" if cardinality == "n:n" else ""
        parts.append(
            f'<path class="rel{many}" d="M{x1:.1f},{y1:.1f} C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} '
            f'{x2:.1f},{y2:.1f}" {attrs}/>'
        )
        if sa == sb:
            lx, ly, anchor = max(x1, x2) + MODEL_BULGE * 0.75 + 4, (y1 + y2) / 2 + 4, "start"
        elif sb == "L":
            lx, ly, anchor = x2 - 8, y2 - 6, "end"
        else:
            lx, ly, anchor = x2 + 8, y2 - 6, "start"
        labels.append(
            f'<text class="rel-label{many}" x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" {attrs}>'
            f"{_esc(cardinality)}</text>"
        )
    for key, table in tables.items():
        x, y, h = pos[key]
        kind = table.get("kind", "table")
        keys = _model_keys(table)
        others = len(table["columns"]) - min(len(keys), MODEL_KEYS)
        personal = sum(1 for c in table["columns"] if c.get("personal"))
        classes = ["tbl", f"m-{kind}"]
        if table.get("flag"):
            classes.append(f"f-{table['flag']}")
        parts.append(
            f'<g class="{" ".join(classes)}" data-k="{_esc(key)}" data-label="{_esc(table["label"])}" '
            f'data-area="{_esc(table.get("area", ""))}" tabindex="0" role="button" aria-pressed="false">'
            f"<title>{_esc(table['label'])}</title>"
            f'<rect class="plate" x="{x:.1f}" y="{y:.1f}" width="{MODEL_W}" height="{h:.1f}" rx="8"/>'
            f'<rect class="bar" x="{x + 1:.1f}" y="{y + 7:.1f}" width="3.5" height="{h - 14:.1f}" rx="1.5"/>'
            f'<text class="ck" x="{x + 16:.1f}" y="{y + 17:.1f}">{_esc(kind.upper())}</text>'
            f'<text class="cl" x="{x + 16:.1f}" y="{y + 36:.1f}">{_esc(_clip(table["label"], 25))}</text>'
        )
        for n, name in enumerate(keys[:MODEL_KEYS]):
            parts.append(
                f'<text class="cr" x="{x + 16:.1f}" y="{y + 55 + 17 * n:.1f}">PK {_esc(_clip(name, 28))}</text>'
            )
        if not keys:
            parts.append(f'<text class="cr none" x="{x + 16:.1f}" y="{y + 55:.1f}">no primary key</text>')
        more = f"+ {others} more column{'' if others == 1 else 's'}" if others else "no other columns"
        if personal:
            more += f" · {personal} personal"
        parts.append(f'<text class="cm" x="{x + 16:.1f}" y="{y + h - 10:.1f}">{_esc(more)}</text>')
        if table.get("flag"):
            parts.append(f'<circle class="flag" cx="{x + MODEL_W - 13:.1f}" cy="{y + 13:.1f}" r="4.5"/>')
        parts.append("</g>")
    parts.extend(labels)
    parts.append("</svg>")
    return "".join(parts)


def _model_card(table: Json, block: Json, names: dict[str, str], areas: dict[str, str]) -> str:
    kind = table.get("kind", "table")
    chips = [f'<span class="chip">{_esc(kind)}</span>']
    if table.get("area"):
        chips.insert(0, f'<span class="chip">{_esc(areas[table["area"]])}</span>')
    if table.get("flag"):
        chips.append(
            f'<span class="chip sev-{"high" if table["flag"] == "bad" else "medium"}">'
            f"{'risk' if table['flag'] == 'bad' else 'watch'}</span>"
        )
    body = [f"<header>{''.join(chips)}</header><h4>{_inline(table['label'])}</h4>"]
    if table.get("grain"):
        body.append(f'<p class="grain"><span class="fix-label">Grain</span> {_inline(table["grain"])}</p>')
    if table.get("history"):
        body.append(f'<p class="grain"><span class="fix-label">History</span> {_inline(table["history"])}</p>')
    if table.get("note"):
        body.append(f'<div class="evidence">{_paragraphs(table["note"])}</div>')
    rows = []
    for column in table["columns"]:
        notes = [column.get("note", "")]
        if column.get("history"):
            notes.append(f"history: {column['history']}")
        if column.get("mask"):
            notes.append(f"mask: {column['mask']}")
        personal = '<span class="chip se">personal</span>' if column.get("personal") else ""
        rows.append(
            f'<tr><td class="mono">{_esc(column["name"])}</td><td class="mono">{_esc(column.get("type", ""))}</td>'
            f'<td class="mono">{_esc(column.get("key", ""))}</td><td>{personal}</td>'
            f"<td>{_inline(' · '.join(n for n in notes if n))}</td></tr>"
        )
    body.append(
        '<div class="table-wrap"><table><thead><tr><th>Column</th><th>Type</th><th>Key</th><th>Data</th><th>Note</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )
    joins = []
    for rel in block.get("relations", []):
        if table["id"] in (rel["from"], rel["to"]):
            other = rel["to"] if rel["from"] == table["id"] else rel["from"]
            bits = [rel.get("cardinality", "n:1")]
            if rel.get("on"):
                bits.append(f"on {rel['on']}")
            if rel.get("label"):
                bits.append(rel["label"])
            joins.append(f"<li>{_esc(names[other])} · {_inline(' · '.join(bits))}</li>")
    if joins:
        body.append(f'<div class="io"><div><span class="fix-label">Joins</span><ul>{"".join(joins)}</ul></div></div>')
    return f'<article class="arch-card model-card plate" data-k="{_esc(table["id"])}">{"".join(body)}</article>'


def _model(block: Json) -> str:
    names = {t["id"]: t["label"] for t in block["tables"]}
    area_list = block.get("areas", [])
    areas = {a["id"]: a["label"] for a in area_list}
    controls = ""
    if len(area_list) > 1:
        buttons = "".join(
            f'<button type="button" data-set-area="{_esc(a["id"])}" aria-pressed="false">{_esc(a["label"])}</button>'
            for a in area_list
        )
        controls = f'<div class="arch-controls"><div class="seg" role="group" aria-label="Area">{buttons}</div></div>'
    kinds = [k for k in TABLE_KINDS if any(t.get("kind", "table") == k for t in block["tables"])]
    legend = "".join(f'<span class="legend-item"><i class="swatch m-{k}"></i>{_esc(k)}</span>' for k in kinds)
    cards = "".join(_model_card(t, block, names, areas) for t in block["tables"])
    return (
        f'<div class="model">{controls}<div class="arch-stage">{_model_svg(block)}</div>'
        f'<div class="legend">{legend}</div>'
        '<div class="arch-cards"><p class="arch-hint comp-hint">Click a table: its grain, every column, what it '
        f"joins to</p>{cards}</div></div>"
    )


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
    elif kind == "decision":
        body = _decision(block)
    elif kind == "architecture":
        body = _architecture(block)
    elif kind == "model":
        body = _model(block)
    elif kind == "nested":
        body = _nested(block)
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
.verdict{padding:26px 20px 20px}.finding{padding:18px 18px 16px}.label{left:16px}ol.steps li{padding-left:48px}
.legend .hint{margin-left:0;width:100%}}
"""

CSS += """
.graph .node{cursor:pointer;outline:none}.graph .node:focus-visible .plate{stroke:var(--gold);stroke-width:2.4}
.graph .node,.graph .edge,.graph .edge-label{transition:opacity .18s}
.graph.tracing .edge.off,.graph.tracing .edge-label.off{opacity:.07}.graph.tracing .node.off{opacity:.22}
.graph.tracing .edge.on-up{stroke:var(--purple);stroke-width:2.2;opacity:1}
.graph.tracing .edge.on-down{stroke:var(--orange);stroke-width:2.2;opacity:1}
.graph.tracing .edge-label.on-up{fill:var(--purple-soft)}.graph.tracing .edge-label.on-down{fill:var(--orange)}
.graph.tracing .node.on-up .plate{stroke:var(--purple);stroke-width:2;fill:rgba(138,99,242,.14)}
.graph.tracing .node.on-up .bar{fill:var(--purple)}
.graph.tracing .node.on-down .plate{stroke:var(--orange);stroke-width:2;fill:rgba(255,166,87,.11)}
.graph.tracing .node.on-down .bar{fill:var(--orange)}
.graph.tracing .node.sel .plate{fill:rgba(138,99,242,.45);stroke:var(--purple-soft);stroke-width:2.6}
.graph.tracing .node.sel .bar{fill:var(--purple-soft)}.graph.tracing .node.sel .node-label{font-weight:700}
.legend .hint{margin-left:auto;color:var(--purple-soft)}
.filter{display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px;margin-bottom:14px}
.filter input{width:min(380px,100%);padding:9px 14px;background:rgba(8,5,19,.6);border:1px solid var(--plate-border);
border-radius:8px;color:var(--ink);font:500 15px var(--mono)}
.filter input::placeholder{color:var(--ink-3)}.filter input:focus{outline:none;border-color:var(--purple-soft)}
.filter .count{font:600 12px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3)}
figure.code .copy{position:absolute;right:28px;top:-15px;background:var(--bg);border:1px solid var(--line);
border-radius:8px;padding:4px 12px;font:600 13px/1.35 var(--mono);letter-spacing:.14em;text-transform:uppercase;
color:var(--ink-3);cursor:pointer}
figure.code .copy:hover{color:var(--ink);border-color:var(--ink-3)}
figure.code .copy.done{color:var(--green);border-color:rgba(126,224,168,.5)}
figure.code:not(.labelled){margin-top:14px;padding-top:28px}
"""

# The decision table and the architecture block. Without the script the architecture still reads: every
# component card, every flow and every variant note is listed; the script turns them into a panel, a
# step-through and a toggle (the html element gets the class "js").
CSS += """
.dec-wrap{overflow-x:auto}
table.dec th[scope=row]{font:inherit;letter-spacing:0;text-transform:none;white-space:normal;color:var(--ink);
padding:14px 24px 14px 14px;border-bottom:1px solid var(--line-2);vertical-align:top;min-width:230px}
table.dec thead th:first-child{padding-left:14px}
table.dec td{vertical-align:top;font-size:16px;line-height:1.45;min-width:150px}
.dec .opt{font-size:18.5px;font-weight:700}
.dec .why{margin-top:5px;font-size:15.5px;line-height:1.4;color:var(--ink-2)}
.dec .mark{display:inline-block;margin-right:7px;padding:4px 6px 3px;border:1px solid;border-radius:5px;
font:600 11px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;vertical-align:2px}
.dec .r-pass .mark{color:var(--green);border-color:rgba(126,224,168,.45)}
.dec .r-weak .mark{color:var(--gold);border-color:rgba(255,210,63,.45)}
.dec .r-fail .mark{color:var(--red);border-color:rgba(255,138,115,.5)}
.dec tr.o-chosen th,.dec tr.o-chosen td{background:rgba(138,99,242,.15)}
.dec tr.o-chosen th{box-shadow:inset 4px 0 0 var(--purple-soft)}
.dec tr.o-eliminated td:not(.st),.dec tr.o-eliminated .opt{opacity:.5}
.dec td.st{white-space:nowrap}
.dec .by{margin-top:7px;font:500 13px/1.4 var(--mono);color:var(--red);white-space:normal}
.chip.st-chosen{color:var(--purple-soft);border-color:var(--purple);background:rgba(138,99,242,.18)}
.chip.st-viable{color:var(--green);border-color:rgba(126,224,168,.45)}
.chip.st-eliminated{color:var(--red);border-color:rgba(255,138,115,.5)}
.arch-controls{display:none;flex-wrap:wrap;align-items:center;gap:10px 18px;margin-bottom:14px}
.js .arch-controls{display:flex}
.arch-controls button{background:rgba(8,5,19,.6);color:var(--ink-2);border:1px solid var(--plate-border);
border-radius:9px;padding:9px 13px;font:600 12.5px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;
cursor:pointer}
.arch-controls button:hover{color:var(--ink)}
.arch-controls button:disabled{opacity:.35;cursor:default}
.arch-controls .seg{display:inline-flex;flex-wrap:wrap}
.arch-controls .seg button{border-radius:0;margin-left:-1px}
.arch-controls .seg button:first-child{border-radius:9px 0 0 9px;margin-left:0}
.arch-controls .seg button:last-child{border-radius:0 9px 9px 0}
.arch-controls .seg button:only-child{border-radius:9px}
.arch-controls .seg button[hidden]{display:none}
.arch-controls button[aria-pressed=true]{background:rgba(138,99,242,.34);color:var(--ink);border-color:var(--purple)}
.arch-controls .arch-trust[aria-pressed=true]{background:rgba(255,138,115,.16);color:var(--red);
border-color:rgba(255,138,115,.6)}
.stepper{display:inline-flex;align-items:center;gap:6px}
.stepper .count{margin-left:6px;font:600 12px var(--mono);letter-spacing:.12em;color:var(--ink-3)}
.arch-vlabel{padding:16px 20px 0;font:600 13px/1.4 var(--mono);letter-spacing:.14em;text-transform:uppercase;
color:var(--purple-soft)}
.js .arch-vlabel,.js svg.arch-svg:not(.on){display:none}
.arch-stage{width:min(1820px,calc(100vw - 48px));margin-left:calc(50% - min(910px,50vw - 24px));overflow-x:auto;
border:1px solid var(--plate-border);border-radius:14px;
background:linear-gradient(160deg,rgba(27,20,54,.7) 0%,rgba(17,12,36,.7) 100%)}
svg.arch-svg{display:block;height:auto;font-family:var(--mono)}
svg.arch-svg.nested{margin:0 auto}
.zone-bg{fill:rgba(236,231,248,.022);stroke:rgba(173,150,255,.14);stroke-width:1}
.zone-label{font-size:11.5px;font-weight:600;letter-spacing:.14em;fill:var(--ink-3)}
.comp{cursor:pointer;outline:none;transition:opacity .18s}
.comp .plate{fill:rgba(236,231,248,.045);stroke:rgba(173,150,255,.32);stroke-width:1.2}
.comp .bar{fill:rgba(173,150,255,.42)}
.comp .ck{font-size:10px;font-weight:600;letter-spacing:.12em;fill:var(--ink-3)}
.comp .cl{font-family:var(--sans);font-size:15px;font-weight:700;fill:var(--ink)}
.comp .ct{font-size:11.5px;fill:var(--purple-soft)}
.comp:focus-visible .plate{stroke:var(--gold);stroke-width:2.4}
.k-user .plate,.k-channel .plate{stroke:var(--purple-soft)}.k-user .bar,.k-channel .bar{fill:var(--purple-soft)}
.k-model .plate{fill:rgba(138,99,242,.17);stroke:var(--purple)}.k-model .bar{fill:var(--purple)}
.k-retrieval .plate,.k-store .plate{fill:rgba(255,210,63,.05);stroke:rgba(255,210,63,.5)}
.k-retrieval .bar,.k-store .bar{fill:var(--gold)}
.k-tool .bar{fill:var(--orange)}
.k-system .plate{fill:none;stroke:rgba(236,231,248,.42);stroke-dasharray:5 4}.k-system .bar{fill:var(--ink-3)}
.k-human .plate{fill:rgba(126,224,168,.06);stroke:rgba(126,224,168,.55)}.k-human .bar{fill:var(--green)}
.k-guard .plate{stroke:rgba(126,224,168,.55)}.k-guard .bar{fill:var(--green)}
.k-ops .plate{fill:none;stroke:var(--line)}.k-ops .cl{fill:var(--ink-2)}.k-ops .bar{fill:var(--ink-3)}
.comp.open-box .plate{fill:rgba(173,150,255,.04);stroke:rgba(173,150,255,.4);stroke-width:1.2;stroke-dasharray:7 5}
.comp.se .plate{stroke:var(--orange);stroke-width:1.9}
.comp.vonly .plate{stroke-dasharray:4 3}
.comp.f-warn .plate{stroke:var(--gold);stroke-width:2.3}.comp.f-bad .plate{stroke:var(--red);stroke-width:2.4}
.comp.f-warn .flag{fill:var(--gold)}.comp.f-bad .flag{fill:var(--red)}
.link{fill:none;stroke:rgba(201,184,255,.42);stroke-width:1.5;marker-end:url(#arch-arrow-base);
transition:opacity .18s}
.link.untrusted{stroke:rgba(255,138,115,.8);stroke-dasharray:6 5;marker-end:url(#arch-arrow-red)}
.link.f-warn{stroke:var(--gold)}.link.f-bad{stroke:var(--red)}
.ah-base{fill:rgba(201,184,255,.55)}.ah-red{fill:var(--red)}.ah-in{fill:var(--purple)}.ah-out{fill:var(--orange)}
.ah-hot{fill:var(--gold)}
.link-label{font-size:11px;fill:var(--ink-2);paint-order:stroke;stroke:#0f0a1e;stroke-width:5px;
stroke-linejoin:round;transition:opacity .18s}
.link-label.untrusted{fill:var(--red)}
.arch .comp.gone{opacity:.07;pointer-events:none}.arch .link.gone,.arch .link-label.gone{display:none}
.arch.focus .comp:not(.sel):not(.near):not(.hot):not(.gone){opacity:.3}
.arch.focus .link:not(.in):not(.out):not(.hot):not(.done),
.arch.focus .link-label:not(.in):not(.out):not(.hot){opacity:.1}
.comp.sel .plate{fill:rgba(138,99,242,.42);stroke:var(--purple-soft);stroke-width:2.4}
.link.in{stroke:var(--purple);stroke-width:2.3;marker-end:url(#arch-arrow-in)}
.link.out{stroke:var(--orange);stroke-width:2.3;marker-end:url(#arch-arrow-out)}
.link-label.in{fill:var(--purple-soft)}.link-label.out,.link-label.hot{fill:var(--orange)}
.link.hot{stroke:var(--gold);stroke-width:3;stroke-dasharray:8 6;marker-end:url(#arch-arrow-hot);
animation:arch-dash 1s linear infinite}
.link.done{stroke:rgba(255,210,63,.42);stroke-width:2;stroke-dasharray:none}
.comp.hot .plate{fill:rgba(255,210,63,.1);stroke:var(--gold);stroke-width:2.4}
@keyframes arch-dash{to{stroke-dashoffset:-28}}
@media (prefers-reduced-motion:reduce){.link.hot{animation:none}}
.arch.trust .comp:not(.taint):not(.gone){opacity:.32}
.arch.trust .comp.taint .plate{stroke:rgba(255,138,115,.75)}
.arch.trust .comp.risk .plate{fill:rgba(255,138,115,.2);stroke:var(--red);stroke-width:2.8}
.arch.trust .link:not(.path):not(.untrusted),.arch.trust .link-label:not(.untrusted){opacity:.14}
.arch.trust .link.path{stroke:var(--red);stroke-width:2.4;opacity:1;marker-end:url(#arch-arrow-red)}
.arch-controls .arch-reach[aria-pressed=true]{background:rgba(255,166,87,.16);color:var(--orange);
border-color:rgba(255,166,87,.6)}
.arch.reach .comp:not(.rch):not(.gone){opacity:.32}
.arch.reach .comp.rch .plate{stroke:rgba(255,166,87,.75)}
.arch.reach .comp.rhit .plate{fill:rgba(255,166,87,.2);stroke:var(--orange);stroke-width:2.8}
.arch.reach .link:not(.rpath),.arch.reach .link-label:not(.rpath){opacity:.14}
.arch.reach .link.rpath{stroke:var(--orange);stroke-width:2.4;opacity:1;marker-end:url(#arch-arrow-out)}
svg.model-svg{display:block;height:auto;margin:0 auto;font-family:var(--mono)}
.tbl{cursor:pointer;outline:none;transition:opacity .18s}
.tbl .plate{fill:rgba(236,231,248,.045);stroke:rgba(173,150,255,.32);stroke-width:1.2}
.tbl .bar{fill:rgba(173,150,255,.42)}
.tbl .ck{font-size:10px;font-weight:600;letter-spacing:.12em;fill:var(--ink-3)}
.tbl .cl{font-family:var(--sans);font-size:15px;font-weight:700;fill:var(--ink)}
.tbl .cr{font-size:11.5px;fill:var(--purple-soft)}.tbl .cr.none{fill:var(--red)}
.tbl .cm{font-size:11px;fill:var(--ink-3)}
.tbl:focus-visible .plate{stroke:var(--gold);stroke-width:2.4}
.m-fact .plate{fill:rgba(138,99,242,.17);stroke:var(--purple)}.m-fact .bar{fill:var(--purple)}
.m-dimension .plate{fill:rgba(255,210,63,.05);stroke:rgba(255,210,63,.5)}.m-dimension .bar{fill:var(--gold)}
.m-bridge .plate{stroke:rgba(255,166,87,.6)}.m-bridge .bar{fill:var(--orange)}
.m-hub .plate{fill:rgba(138,99,242,.17);stroke:var(--purple)}.m-hub .bar{fill:var(--purple)}
.m-link .plate{stroke:rgba(255,166,87,.6)}.m-link .bar{fill:var(--orange)}
.m-satellite .plate{fill:rgba(255,210,63,.05);stroke:rgba(255,210,63,.5)}.m-satellite .bar{fill:var(--gold)}
.m-staging .plate{fill:none;stroke:var(--line);stroke-dasharray:5 4}.m-staging .bar{fill:var(--ink-3)}
.tbl.f-warn .plate{stroke:var(--gold);stroke-width:2.3}.tbl.f-bad .plate{stroke:var(--red);stroke-width:2.4}
.tbl.f-warn .flag{fill:var(--gold)}.tbl.f-bad .flag{fill:var(--red)}
.rel{fill:none;stroke:rgba(201,184,255,.42);stroke-width:1.5;marker-end:url(#model-arrow-base);transition:opacity .18s}
.rel.many{stroke:var(--red);stroke-dasharray:6 5}
.rel-label{font-size:11px;fill:var(--ink-2);paint-order:stroke;stroke:#0f0a1e;stroke-width:5px;stroke-linejoin:round;
transition:opacity .18s}
.rel-label.many{fill:var(--red)}
.mh-base{fill:rgba(201,184,255,.55)}.mh-on{fill:var(--orange)}
.model.focus .tbl:not(.sel):not(.near){opacity:.3}
.model.focus .rel:not(.on),.model.focus .rel-label:not(.on){opacity:.1}
.tbl.sel .plate{fill:rgba(138,99,242,.42);stroke:var(--purple-soft);stroke-width:2.4}
.tbl.near .plate{stroke:var(--orange);stroke-width:2}
.rel.on{stroke:var(--orange);stroke-width:2.3;marker-end:url(#model-arrow-on)}.rel-label.on{fill:var(--orange)}
.tbl.out{opacity:.12}.model .rel.fade,.model .rel-label.fade{opacity:.08}
.swatch.m-fact,.swatch.m-hub{background:rgba(138,99,242,.25);border-color:var(--purple)}
.swatch.m-dimension,.swatch.m-satellite{background:rgba(255,210,63,.08);border-color:rgba(255,210,63,.6)}
.swatch.m-bridge,.swatch.m-link{border-color:var(--orange)}
.swatch.m-staging{background:none;border-style:dashed;border-color:var(--line)}
.model-card .grain{margin-top:8px;font-size:17px;color:var(--ink-2)}
.model-card .table-wrap{margin-top:14px}
.model-card td.mono{font:500 14px/1.5 var(--mono)}
.arch-caption{display:none;margin-top:12px;padding:12px 18px;border:1px solid rgba(255,210,63,.4);border-radius:10px;
background:rgba(255,210,63,.06);font-size:17px;color:var(--ink)}
.js .arch-caption.on{display:block}
.swatch.k-model{background:rgba(138,99,242,.25);border-color:var(--purple)}
.swatch.k-user,.swatch.k-channel{border-color:var(--purple-soft)}
.swatch.k-retrieval,.swatch.k-store{background:rgba(255,210,63,.08);border-color:rgba(255,210,63,.6)}
.swatch.k-tool{border-color:var(--orange)}
.swatch.k-system{border-style:dashed;border-color:rgba(236,231,248,.42);background:none}
.swatch.k-human,.swatch.k-guard{border-color:rgba(126,224,168,.6)}
.swatch.k-ops{background:none;border-color:var(--line)}
.swatch.se{border-color:var(--orange);border-width:2px}
.swatch.vonly{border-style:dashed}
.swatch.untrusted{height:0;border-width:0;border-top:2px dashed var(--red);border-radius:0;background:none}
.arch-vnotes{margin-top:14px;display:grid;gap:6px;color:var(--ink-2);font-size:17px}
.js .arch-vnote{display:none}.js .arch-vnote.open{display:block}
.arch-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px;margin-top:24px}
.js .arch-cards{display:block}
.arch-card{padding:20px 24px 18px}
.js .arch-card{display:none}.js .arch-card.open{display:block}
.arch-card header{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
.arch-card h4{font-size:21px;font-weight:700;line-height:1.3}
.arch-card dl.kv{margin-top:12px;grid-template-columns:minmax(120px,210px) 1fr}
.arch-card dl.kv dd{font-size:16.5px}
.arch-card .io{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px 28px;margin-top:14px}
.arch-card .io ul{list-style:none;display:grid;gap:4px;font-size:16px;color:var(--ink-2)}
.arch-card .only,.arch-flow .only,.arch-card .io .only{font:500 13px/1.5 var(--mono);color:var(--ink-3)}
.arch-card .only{margin-top:12px}
.chip.se{color:var(--orange);border-color:rgba(255,166,87,.5)}
.chip.untrusted{color:var(--red);border-color:rgba(255,138,115,.5);font-size:10px;padding:3px 6px 2px}
.arch-hint{display:none;font:600 12px/1.6 var(--mono);letter-spacing:.12em;text-transform:uppercase;
color:var(--ink-3)}
.js .arch-hint{display:block}.js .arch-hint.off{display:none}
.arch-flows{margin-top:26px;display:grid;gap:22px}
.js .arch-flows{display:block}
.arch-flow h4{font:600 14px/1.4 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);
margin-bottom:12px}
.js .arch-flow{display:none}.js .arch-flow.open{display:block}
ol.flow-steps{list-style:none;counter-reset:fs;display:grid;gap:6px;max-width:1120px}
ol.flow-steps li{counter-increment:fs;position:relative;padding:10px 14px 10px 54px;border:1px solid transparent;
border-radius:10px;color:var(--ink-2);font-size:17px;line-height:1.45}
ol.flow-steps li::before{content:counter(fs,decimal-leading-zero);position:absolute;left:16px;top:12px;
font:600 14px var(--mono);color:var(--purple-soft)}
ol.flow-steps .who{display:block;font:600 12.5px/1.5 var(--mono);letter-spacing:.04em;color:var(--purple-soft)}
.js ol.flow-steps li{cursor:pointer}
ol.flow-steps li.now{border-color:rgba(255,210,63,.5);background:rgba(255,210,63,.07);color:var(--ink)}
ol.flow-steps li.now .who{color:var(--gold)}
ol.flow-steps li.past{opacity:.62}
.arch-trustlist{margin-top:30px}
.arch-trustlist>h3{font:600 14px/1.4 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);
margin-bottom:16px}
@media print{.arch-controls,.arch-hint,.arch-caption{display:none!important}
.js .arch-vlabel,.js svg.arch-svg{display:block!important}
.js .arch-card,.js .arch-flow,.js .arch-vnote{display:block}.js .arch-cards{display:grid}
.arch .comp,.arch .link,.arch .link-label{opacity:1!important}}
"""

# One small inline script, the same on every page. It only adds behaviour; the page reads the same
# without it. Click a node to trace what leads to it (purple) and what it reaches (orange), Esc or a
# click on the empty graph clears it, and #node=<id or label> in the link opens a page traced. Tables
# with 8 or more rows get a filter box, code blocks a copy button. It reads text only through
# textContent and builds elements with createElement, so page content never becomes markup.
SCRIPT = """
(function () {
  "use strict";
  document.documentElement.classList.add("js");
  function all(root, sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }
  function listed(el, name, word) { return (" " + (el.getAttribute(name) || "") + " ").indexOf(" " + word + " ") >= 0; }
  var params = {};
  location.hash.slice(1).split("&").forEach(function (part) {
    var at = part.indexOf("=");
    if (at > 0) {
      try { params[part.slice(0, at)] = decodeURIComponent(part.slice(at + 1)); } catch (err) { /* a broken link */ }
    }
  });
  function walk(start, map) {
    var seen = {}, stack = [start];
    while (stack.length) {
      (map[stack.pop()] || []).forEach(function (k) {
        if (!seen[k] && k !== start) { seen[k] = true; stack.push(k); }
      });
    }
    return seen;
  }
  var wanted = /^#node=(.+)$/.exec(location.hash);
  wanted = wanted ? decodeURIComponent(wanted[1]) : null;
  all(document, "svg.graph").forEach(function (svg) {
    var nodes = all(svg, ".node"), edges = all(svg, ".edge"), lines = edges.concat(all(svg, ".edge-label"));
    var up = {}, down = {};
    edges.forEach(function (e) {
      e.dataset.m = e.getAttribute("marker-end");
      (down[e.dataset.a] = down[e.dataset.a] || []).push(e.dataset.b);
      (up[e.dataset.b] = up[e.dataset.b] || []).push(e.dataset.a);
    });
    function clear() {
      svg.classList.remove("tracing");
      nodes.forEach(function (n) {
        n.classList.remove("sel", "on-up", "on-down", "off");
        n.setAttribute("aria-pressed", "false");
      });
      lines.forEach(function (e) {
        e.classList.remove("on-up", "on-down", "off");
        if (e.dataset.m) { e.setAttribute("marker-end", e.dataset.m); }
      });
    }
    function trace(key) {
      clear();
      var u = walk(key, up), d = walk(key, down);
      svg.classList.add("tracing");
      nodes.forEach(function (n) {
        var k = n.dataset.k;
        n.classList.add(k === key ? "sel" : u[k] ? "on-up" : d[k] ? "on-down" : "off");
        n.setAttribute("aria-pressed", String(k === key));
      });
      lines.forEach(function (e) {
        var a = e.dataset.a, b = e.dataset.b;
        var cls = (b === key || u[b]) && u[a] ? "on-up" : (a === key || d[a]) && d[b] ? "on-down" : "off";
        e.classList.add(cls);
        var head = cls === "on-up" ? "up" : cls === "on-down" ? "down" : "dim";
        if (e.dataset.m) { e.setAttribute("marker-end", "url(#arrow-" + head + ")"); }
      });
    }
    function toggle(n) {
      if (n.classList.contains("sel")) { clear(); history.replaceState(null, "", location.pathname + location.search); }
      else { trace(n.dataset.k); history.replaceState(null, "", "#node=" + encodeURIComponent(n.dataset.k)); }
    }
    nodes.forEach(function (n) {
      n.addEventListener("click", function (ev) { ev.stopPropagation(); toggle(n); });
      n.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); toggle(n); }
      });
    });
    svg.addEventListener("click", clear);
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") { clear(); } });
    var legend = svg.parentNode.nextElementSibling;
    if (legend && legend.classList.contains("legend")) {
      var hint = document.createElement("span");
      hint.className = "hint";
      hint.textContent = "Click a node to trace it · Esc clears";
      legend.appendChild(hint);
    }
    if (wanted) {
      var hit = nodes.filter(function (n) { return n.dataset.k === wanted || n.dataset.label === wanted; })[0];
      if (hit) { trace(hit.dataset.k); hit.scrollIntoView({ block: "center" }); }
    }
  });
  // The architecture: click a component for its card, step a flow through, switch the variant, show
  // where untrusted text can reach an action. #variant=, #component=, #flow=…&step= and #trust=1 open it so.
  var archActive = null;
  all(document, ".arch").forEach(function (root) {
    var svgs = all(root, "svg.arch-svg");
    if (!svgs.length) { return; }
    var comps = all(root, "svg.arch-svg .comp"), links = all(root, "svg.arch-svg .link, svg.arch-svg .link-label");
    var cards = all(root, ".arch-card"), flows = all(root, ".arch-flow"), notes = all(root, ".arch-vnote");
    var vbuttons = all(root, "button[data-set-variant]"), fbuttons = all(root, "button[data-set-flow]");
    var trustButton = root.querySelector(".arch-trust"), caption = root.querySelector(".arch-caption");
    var reachButton = root.querySelector(".arch-reach");
    var compHint = root.querySelector(".comp-hint"), flowHint = root.querySelector(".flows-hint");
    var prev = root.querySelector(".stepper .prev"), next = root.querySelector(".stepper .next");
    var play = root.querySelector(".stepper .play"), count = root.querySelector(".stepper .count");
    var first = root.getAttribute("data-default");
    var st = { v: first, comp: null, flow: null, step: 0, trust: false, reach: false }, timer = null;
    function find(list, attr, key) {
      return list.filter(function (el) { return el.getAttribute(attr) === key; })[0] || null;
    }
    function steps() { var f = find(flows, "data-flow", st.flow); return f ? all(f, "li") : []; }
    function stop() { if (timer) { clearInterval(timer); timer = null; } }
    function inVariant(key, v) {
      return comps.some(function (c) { return c.getAttribute("data-k") === key && listed(c, "data-v", v); });
    }
    function setVariant(v) {
      st.v = v;
      var f = st.flow && find(flows, "data-flow", st.flow);
      if (st.comp && !inVariant(st.comp, v)) { st.comp = null; }
      if (f && !listed(f, "data-v", v)) { st.flow = null; stop(); }
    }
    function pick(key) { stop(); st.flow = null; st.comp = st.comp === key ? null : key; }
    function pickFlow(id) {
      stop();
      var f = find(flows, "data-flow", id);
      if (!f || st.flow === id) { st.flow = null; return; }
      if (!listed(f, "data-v", st.v)) { setVariant(f.getAttribute("data-v").split(" ")[0]); }
      st.flow = id; st.step = 0; st.comp = null;
    }
    function go(delta) {
      var n = steps().length;
      if (n) { st.step = Math.max(0, Math.min(n - 1, st.step + delta)); }
    }
    function writeHash() {
      var parts = [];
      if (st.v !== first) { parts.push("variant=" + encodeURIComponent(st.v)); }
      if (st.comp) { parts.push("component=" + encodeURIComponent(st.comp)); }
      if (st.flow) { parts.push("flow=" + encodeURIComponent(st.flow), "step=" + (st.step + 1)); }
      if (st.trust) { parts.push("trust=1"); }
      if (st.reach) { parts.push("reach=1"); }
      history.replaceState(null, "", parts.length ? "#" + parts.join("&") : location.pathname + location.search);
    }
    function paint() {
      var v = st.v, list = steps(), now = list[st.step] || null, near = {}, done = {};
      var a = now ? now.getAttribute("data-a") : null, b = now ? now.getAttribute("data-b") : null;
      var shown = st.comp || b;
      list.slice(0, st.step).forEach(function (li) {
        done[li.getAttribute("data-a") + ">" + li.getAttribute("data-b")] = true;
      });
      svgs.forEach(function (s) { s.classList.toggle("on", s.getAttribute("data-variant") === v); });
      root.classList.toggle("trust", st.trust);
      root.classList.toggle("reach", st.reach);
      root.classList.toggle("focus", !!(st.comp || now));
      links.forEach(function (l) {
        var la = l.getAttribute("data-a"), lb = l.getAttribute("data-b"), gone = !listed(l, "data-v", v);
        var out = !gone && la === st.comp, inn = !gone && lb === st.comp;
        var hot = !gone && !!now && ((la === a && lb === b) || (la === b && lb === a));
        l.classList.toggle("gone", gone);
        l.classList.toggle("path", listed(l, "data-path", v));
        l.classList.toggle("rpath", listed(l, "data-rpath", v));
        l.classList.toggle("out", out);
        l.classList.toggle("in", inn);
        l.classList.toggle("hot", hot);
        l.classList.toggle("done", !gone && !hot && (done[la + ">" + lb] || done[lb + ">" + la]) === true);
        if (out) { near[lb] = true; }
        if (inn) { near[la] = true; }
      });
      comps.forEach(function (c) {
        var k = c.getAttribute("data-k");
        c.classList.toggle("gone", !listed(c, "data-v", v));
        c.classList.toggle("sel", k === st.comp);
        c.classList.toggle("near", near[k] === true);
        c.classList.toggle("hot", !!now && (k === a || k === b));
        c.classList.toggle("taint", listed(c, "data-taint", v));
        c.classList.toggle("risk", listed(c, "data-risk", v));
        c.classList.toggle("rch", listed(c, "data-reach", v));
        c.classList.toggle("rhit", listed(c, "data-rhit", v));
        c.setAttribute("aria-pressed", String(k === st.comp));
      });
      cards.forEach(function (card) { card.classList.toggle("open", card.getAttribute("data-k") === shown); });
      flows.forEach(function (f) { f.classList.toggle("open", f.getAttribute("data-flow") === st.flow); });
      list.forEach(function (li, i) {
        li.classList.toggle("now", i === st.step);
        li.classList.toggle("past", i < st.step);
      });
      notes.forEach(function (n) { n.classList.toggle("open", n.getAttribute("data-variant") === v); });
      vbuttons.forEach(function (btn) {
        btn.setAttribute("aria-pressed", String(btn.getAttribute("data-set-variant") === v));
      });
      fbuttons.forEach(function (btn) {
        var id = btn.getAttribute("data-set-flow"), f = find(flows, "data-flow", id);
        btn.hidden = !!f && !listed(f, "data-v", v);
        btn.setAttribute("aria-pressed", String(id === st.flow));
      });
      if (compHint) { compHint.classList.toggle("off", !!shown); }
      if (flowHint) { flowHint.classList.toggle("off", !!st.flow); }
      if (trustButton) { trustButton.setAttribute("aria-pressed", String(st.trust)); }
      if (reachButton) { reachButton.setAttribute("aria-pressed", String(st.reach)); }
      if (count) { count.textContent = now ? (st.step + 1) + " / " + list.length : ""; }
      if (prev) { prev.disabled = !now || st.step === 0; }
      if (next) { next.disabled = !now || st.step >= list.length - 1; }
      if (play) { play.disabled = !now; play.textContent = timer ? "Pause" : "Play"; }
      if (caption) {
        caption.textContent = now ? (st.step + 1) + ". " + now.querySelector(".who").textContent + " · " +
          now.querySelector(".what").textContent : "";
        caption.classList.toggle("on", !!now);
      }
    }
    function update() { archActive = root; paint(); writeHash(); }
    comps.forEach(function (c) {
      function act(ev) { ev.stopPropagation(); pick(c.getAttribute("data-k")); update(); }
      c.addEventListener("click", act);
      c.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); act(ev); }
      });
    });
    svgs.forEach(function (s) {
      s.addEventListener("click", function () { stop(); st.comp = null; st.flow = null; update(); });
    });
    vbuttons.forEach(function (btn) {
      btn.addEventListener("click", function () { setVariant(btn.getAttribute("data-set-variant")); update(); });
    });
    fbuttons.forEach(function (btn) {
      btn.addEventListener("click", function () { pickFlow(btn.getAttribute("data-set-flow")); update(); });
    });
    flows.forEach(function (f) {
      all(f, "li").forEach(function (li, i) {
        li.addEventListener("click", function () {
          stop(); st.flow = f.getAttribute("data-flow"); st.step = i; update();
        });
      });
    });
    if (trustButton) {
      trustButton.addEventListener("click", function () {
        st.trust = !st.trust;
        if (st.trust) { st.reach = false; }
        update();
      });
    }
    if (reachButton) {
      reachButton.addEventListener("click", function () {
        st.reach = !st.reach;
        if (st.reach) { st.trust = false; }
        update();
      });
    }
    if (prev) { prev.addEventListener("click", function () { stop(); go(-1); update(); }); }
    if (next) { next.addEventListener("click", function () { stop(); go(1); update(); }); }
    if (play) {
      play.addEventListener("click", function () {
        if (timer) { stop(); } else {
          if (st.step >= steps().length - 1) { st.step = 0; }
          timer = setInterval(function () {
            if (st.step >= steps().length - 1) { stop(); } else { go(1); }
            update();
          }, 1800);
        }
        update();
      });
    }
    document.addEventListener("keydown", function (ev) {
      var tag = ev.target && ev.target.tagName;
      if (archActive !== root || tag === "INPUT" || tag === "TEXTAREA") { return; }
      if (ev.key === "Escape") { stop(); st.comp = null; st.flow = null; update(); }
      else if (st.flow && (ev.key === "ArrowRight" || ev.key === "ArrowLeft")) {
        ev.preventDefault(); stop(); go(ev.key === "ArrowRight" ? 1 : -1); update();
      }
    });
    var linked = false;
    if (params.variant && find(vbuttons, "data-set-variant", params.variant)) {
      setVariant(params.variant); linked = true;
    }
    if (params.component && inVariant(params.component, st.v)) { pick(params.component); linked = true; }
    if (params.flow && find(flows, "data-flow", params.flow)) {
      pickFlow(params.flow);
      go((parseInt(params.step, 10) || 1) - 1);
      linked = true;
    }
    if (params.trust === "1" && trustButton) { st.trust = true; linked = true; }
    if (params.reach === "1" && reachButton) { st.reach = true; linked = true; }
    paint();
    if (linked) { archActive = root; params = {}; root.scrollIntoView({ block: "start" }); }
  });
  // The data model: click a table for its card and its neighbours, filter by area. #table= and #area= open it so.
  all(document, ".model").forEach(function (root) {
    var svg = root.querySelector("svg.model-svg");
    if (!svg) { return; }
    var tables = all(svg, ".tbl"), rels = all(svg, ".rel, .rel-label"), cards = all(root, ".model-card");
    var buttons = all(root, "button[data-set-area]"), hint = root.querySelector(".comp-hint");
    var st = { table: null, area: null };
    function paint() {
      var near = {}, areaOf = {};
      tables.forEach(function (t) { areaOf[t.getAttribute("data-k")] = t.getAttribute("data-area"); });
      rels.forEach(function (r) {
        var a = r.getAttribute("data-a"), b = r.getAttribute("data-b");
        var on = !!st.table && (a === st.table || b === st.table);
        r.classList.toggle("on", on);
        r.classList.toggle("fade", !!st.area && !on && (areaOf[a] !== st.area || areaOf[b] !== st.area));
        if (on) { near[a === st.table ? b : a] = true; }
      });
      root.classList.toggle("focus", !!st.table);
      tables.forEach(function (t) {
        var k = t.getAttribute("data-k");
        t.classList.toggle("sel", k === st.table);
        t.classList.toggle("near", near[k] === true);
        t.classList.toggle("out", !!st.area && areaOf[k] !== st.area && k !== st.table && near[k] !== true);
        t.setAttribute("aria-pressed", String(k === st.table));
      });
      cards.forEach(function (c) { c.classList.toggle("open", c.getAttribute("data-k") === st.table); });
      buttons.forEach(function (b) {
        b.setAttribute("aria-pressed", String(b.getAttribute("data-set-area") === st.area));
      });
      if (hint) { hint.classList.toggle("off", !!st.table); }
    }
    function update() {
      var parts = [];
      if (st.area) { parts.push("area=" + encodeURIComponent(st.area)); }
      if (st.table) { parts.push("table=" + encodeURIComponent(st.table)); }
      paint();
      history.replaceState(null, "", parts.length ? "#" + parts.join("&") : location.pathname + location.search);
    }
    tables.forEach(function (t) {
      function act(ev) {
        ev.stopPropagation();
        var k = t.getAttribute("data-k");
        st.table = st.table === k ? null : k;
        update();
      }
      t.addEventListener("click", act);
      t.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); act(ev); }
      });
    });
    svg.addEventListener("click", function () { st.table = null; update(); });
    buttons.forEach(function (b) {
      b.addEventListener("click", function () {
        var id = b.getAttribute("data-set-area");
        st.area = st.area === id ? null : id;
        update();
      });
    });
    document.addEventListener("keydown", function (ev) {
      var tag = ev.target && ev.target.tagName;
      if (ev.key === "Escape" && tag !== "INPUT" && st.table) { st.table = null; update(); }
    });
    if (params.area && buttons.some(function (b) { return b.getAttribute("data-set-area") === params.area; })) {
      st.area = params.area;
    }
    if (params.table && tables.some(function (t) { return t.getAttribute("data-k") === params.table; })) {
      st.table = params.table;
    }
    paint();
    if (st.table || st.area) { root.scrollIntoView({ block: "start" }); }
  });
  all(document, ".table-wrap").forEach(function (wrap) {
    var rows = all(wrap, "tbody tr");
    if (rows.length < 8) { return; }
    var bar = document.createElement("div");
    var input = document.createElement("input");
    var count = document.createElement("span");
    bar.className = "filter";
    input.type = "search";
    input.placeholder = "Filter " + rows.length + " rows";
    input.setAttribute("aria-label", "Filter the rows of this table");
    count.className = "count";
    bar.appendChild(input);
    bar.appendChild(count);
    wrap.parentNode.insertBefore(bar, wrap);
    input.addEventListener("input", function () {
      var text = input.value.trim().toLowerCase(), shown = 0;
      rows.forEach(function (r) {
        var hit = !text || r.textContent.toLowerCase().indexOf(text) >= 0;
        r.hidden = !hit;
        if (hit) { shown += 1; }
      });
      count.textContent = text ? shown + " of " + rows.length : "";
    });
  });
  all(document, "figure.code").forEach(function (fig) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "copy";
    button.textContent = "Copy";
    function done() {
      button.textContent = "Copied";
      button.classList.add("done");
      setTimeout(function () { button.textContent = "Copy"; button.classList.remove("done"); }, 1600);
    }
    function fallback(text) {
      var area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try { document.execCommand("copy"); done(); } catch (err) { button.textContent = "Select and copy"; }
      area.remove();
    }
    button.addEventListener("click", function () {
      var text = all(fig, ".ln").map(function (line) {
        var copy = line.cloneNode(true), no = copy.querySelector(".no");
        if (no) { no.remove(); }
        return copy.textContent === " " ? "" : copy.textContent;
      }).join("\\n");
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done, function () { fallback(text); });
      } else { fallback(text); }
    });
    fig.appendChild(button);
  });
})();
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


# Only a page rendered through --site carries these, so a lone page stays exactly as it was.
SITE_CSS = """
header.site{position:sticky;top:0;z-index:30;background:rgba(8,5,19,.88);backdrop-filter:blur(10px);
border-bottom:1px solid var(--line)}
header.site .in{display:flex;align-items:center;gap:28px;max-width:1360px;height:56px;margin:0 auto;padding:0 48px}
header.site .home{flex:none;max-width:280px;overflow:hidden;font-size:17px;font-weight:700;letter-spacing:-.01em;
color:var(--ink);text-decoration:none;text-overflow:ellipsis;white-space:nowrap}
header.site nav{position:relative;display:flex;align-items:center;gap:4px;min-width:0;overflow-x:auto;
scrollbar-width:none;white-space:nowrap}
header.site nav::-webkit-scrollbar{display:none}
header.site nav a{flex:none;padding:6px 10px;border-radius:8px;font:600 14px/1.3 var(--mono);color:var(--ink-2);
text-decoration:none}
header.site nav a:hover{background:var(--line-2);color:var(--ink)}
header.site a:focus-visible{outline:2px solid var(--purple-soft);outline-offset:-2px}
header.site nav a[aria-current]{background:rgba(138,99,242,.28);box-shadow:inset 0 0 0 1px var(--plate-border);
color:var(--ink)}
header.site .g{flex:none;margin-left:16px;padding-right:2px;font:600 11.5px/1.3 var(--mono);letter-spacing:.12em;
text-transform:uppercase;color:var(--ink-3)}
header.site .g:first-child{margin-left:0}
section{scroll-margin-top:84px}
@media (max-width:760px){header.site .in{gap:14px;height:50px;padding:0 16px}
header.site .home{max-width:130px;font-size:15px}}
@media print{header.site{display:none}}
"""

# On a narrow screen the links scroll sideways; start with the current page in view.
SITE_SCRIPT = """
(function(){var cur=document.querySelector('header.site [aria-current]');if(!cur)return;var nav=cur.parentNode;
nav.scrollLeft=cur.offsetLeft-(nav.clientWidth-cur.offsetWidth)/2;})();
"""


def _site_bar(site: Json, current: int, hrefs: list[str]) -> str:
    """The header of one page of a set: the set's name, then a link to every page, this one marked."""
    items: list[str] = []
    group = None
    for i, (entry, href) in enumerate(zip(site["pages"], hrefs, strict=True)):
        if entry.get("group") != group:
            group = entry.get("group")
            if group:
                items.append(f'<span class="g">{_esc(group)}</span>')
        mark = ' aria-current="page"' if i == current else ""
        items.append(f'<a href="{_esc(href)}"{mark}>{_esc(entry["label"])}</a>')
    return (
        f'<header class="site"><div class="in"><a class="home" href="{_esc(hrefs[0])}" title="{_esc(site["title"])}">'
        f'{_esc(site["title"])}</a><nav aria-label="Pages">{"".join(items)}</nav></div></header>'
    )


def render(page: Json, bar: str = "") -> str:
    """Return the HTML of a page that validate() accepted, under the header of its set if it has one."""
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
        f"<title>{_esc(page['title'])}</title><style>{font_css()}{CSS}{SITE_CSS if bar else ''}</style></head>"
        f"<body>{bar}<main>"
        f'<div class="status">{status}</div><h1>{_inline(page["title"])}</h1>'
        + (f'<p class="lead">{_inline(page["subtitle"])}</p>' if page.get("subtitle") else "")
        + verdict_html
        + _facts(page.get("stats", []))
        + toc_html
        + "".join(sections)
        + f"<footer>Written by the {_esc(skill)} skill{date} · numbers from the skill's scripts · "
        "claims tagged high (checked), med (likely), guess (not checked)</footer>"
        f"</main><script>{SCRIPT}{SITE_SCRIPT if bar else ''}</script></body></html>\n"
    )


def _print_problems(source: Path, errors: list[str]) -> None:
    print(f"{source}: {len(errors)} problem(s)", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)


def render_site(site_path: Path, *, check: bool = False) -> int:
    """Write every page of a site file beside its JSON, each under a header linking the whole set.

    Nothing is written unless every page is valid, so a set is never left half new and half old.
    """
    try:
        site = json.loads(site_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {site_path}: {exc}", file=sys.stderr)
        return 2
    errors = validate_site(site)
    if errors:
        _print_problems(site_path, errors)
        return 1
    base = site_path.resolve().parent
    sources = [(base / entry["page"]).resolve() for entry in site["pages"]]
    pages: list[Json] = []
    for source in sources:
        try:
            page = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"cannot read {source}: {exc}", file=sys.stderr)
            continue
        problems = validate(page)
        if problems:
            _print_problems(source, problems)
            continue
        pages.append(page)
    if len(pages) != len(sources):
        return 1
    if check:
        print(f"{site_path}: {len(pages)} pages valid")
        return 0
    targets = [source.with_suffix(".html") for source in sources]
    for i, (page, target) in enumerate(zip(pages, targets, strict=True)):
        hrefs = [quote(Path(os.path.relpath(other, target.parent)).as_posix()) for other in targets]
        target.write_text(render(page, _site_bar(site, i, hrefs)), encoding="utf-8")
        print(target)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a skill page from its JSON.")
    parser.add_argument("page", type=Path, nargs="?", help="the page JSON")
    parser.add_argument("-o", "--output", type=Path, help="where to write the HTML")
    parser.add_argument("--site", type=Path, help="a site JSON: write all its pages, with a header linking them")
    parser.add_argument("--check", action="store_true", help="validate only, write nothing")
    args = parser.parse_args(argv)
    if (args.page is None) == (args.site is None):
        parser.error("give either a page JSON or --site SITE.json")
    if args.site is not None:
        if args.output is not None:
            parser.error("--output is for one page; --site writes each page beside its JSON")
        return render_site(args.site, check=args.check)
    try:
        page = json.loads(args.page.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {args.page}: {exc}", file=sys.stderr)
        return 2
    errors = validate(page)
    if errors:
        _print_problems(args.page, errors)
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
