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
    python3 render_page.py --index FOLDER           # write FOLDER/index.html, listing every page under it
    python3 render_page.py PAGE.json --md -o PAGE.md  # the same page as a Markdown note; drawings become tables

The fonts (Bricolage Grotesque and JetBrains Mono, SIL OFL 1.1) are read from ../assets/fonts and
inlined, so the page is one file; without them it falls back to system fonts.

Single source: shared/render_page.py in claude-role-skills. The copies under each skill's
scripts/ and assets/ are written by tools/sync_shared.py; edit the shared files, never a copy.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import html
import json
import math
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
FLOW_KINDS = {"start": "start", "step": "step", "decision": "decision", "end": "end"}
BLOCK_TYPES = (
    "text",
    "list",
    "table",
    "findings",
    "code",
    "graph",
    "flowchart",
    "steps",
    "kv",
    "callout",
    "decision",
    "architecture",
    "model",
    "nested",
    "chart",
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
CHART_KINDS = ("bar", "line", "waterfall", "heatmap")
CHART_MAX_SERIES = 6


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
                _str(item, "cloud", ipath, errs, required=False)
                _str(item, "variant", ipath, errs, required=False)
            if key == "components":
                _str(item, "region", ipath, errs, required=False)
    for key in ("assumptions", "open", "specialists"):
        for i, item in enumerate(_list(facts, key, path, errs, required=False)):
            if not isinstance(item, str):
                errs.append(f"{path}.{key}[{i}]: must be a string")
    if "budget" in facts:
        _validate_budget(facts["budget"], f"{path}.budget", errs)


def _validate_budget(budget: Json, path: str, errs: list[str]) -> None:
    """The money a brief allows, in one currency: solution-blueprint compares totals against it."""
    if not isinstance(budget, dict):
        errs.append(f"{path}: must be an object")
        return
    if not isinstance(budget.get("monthly"), int | float) or isinstance(budget.get("monthly"), bool):
        errs.append(f"{path}.monthly: must be a number")
    _str(budget, "currency", path, errs)
    _str(budget, "source", path, errs)


def _number_ok(value: Json) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_chart(block: Json, path: str, errs: list[str]) -> None:
    kind = block.get("kind")
    if kind not in CHART_KINDS:
        errs.append(f"{path}.kind: must be one of {', '.join(CHART_KINDS)}")
        return
    for key in ("x_label", "y_label", "unit", "caption"):
        _str(block, key, path, errs, required=False)
    places = block.get("places")
    if places is not None and (not isinstance(places, int) or isinstance(places, bool) or not 0 <= places <= 6):
        errs.append(f"{path}.places: must be an integer from 0 to 6")
    if kind in ("bar", "line"):
        categories = _list(block, "categories", path, errs)
        if not categories:
            errs.append(f"{path}.categories: at least one category")
        for i, category in enumerate(categories):
            if not isinstance(category, str):
                errs.append(f"{path}.categories[{i}]: must be a string")
        series = _list(block, "series", path, errs)
        if not 1 <= len(series) <= CHART_MAX_SERIES:
            errs.append(f"{path}.series: from 1 to {CHART_MAX_SERIES} series")
        seen: set[str] = set()
        count = 0
        for i, item in enumerate(series):
            spath = f"{path}.series[{i}]"
            if not isinstance(item, dict):
                errs.append(f"{spath}: must be an object")
                continue
            _str(item, "name", spath, errs)
            if isinstance(item.get("name"), str):
                if item["name"] in seen:
                    errs.append(f"{spath}.name: duplicate series {item['name']!r}")
                seen.add(item["name"])
            values = _list(item, "values", spath, errs)
            if isinstance(categories, list) and len(values) != len(categories):
                errs.append(f"{spath}.values: must have one value per category ({len(categories)})")
            for j, value in enumerate(values):
                if value is not None and not _number_ok(value):
                    errs.append(f"{spath}.values[{j}]: must be a number or null")
                elif value is not None:
                    count += 1
        if series and count == 0 and not any(e.startswith(f"{path}.series") for e in errs):
            errs.append(f"{path}.series: no values to draw")
        if kind == "line" and not isinstance(block.get("zero", True), bool):
            errs.append(f"{path}.zero: must be true or false")
    elif kind == "waterfall":
        items = _list(block, "items", path, errs)
        if len(items) < 2:
            errs.append(f"{path}.items: at least two steps")
        running = 0.0
        for i, item in enumerate(items):
            ipath = f"{path}.items[{i}]"
            if not isinstance(item, dict):
                errs.append(f"{ipath}: must be an object")
                continue
            _str(item, "label", ipath, errs)
            amount: Json = item.get("value")
            if not _number_ok(amount):
                errs.append(f"{ipath}.value: must be a number")
                continue
            if not isinstance(item.get("total", False), bool):
                errs.append(f"{ipath}.total: must be true or false")
            if item.get("total"):
                if i > 0 and abs(float(amount) - running) > 0.005:
                    errs.append(
                        f"{ipath}.value: a total must equal the running sum of the steps before it ({running:.2f})"
                    )
                running = float(amount)
            else:
                running += float(amount)
    else:  # heatmap
        rows = _list(block, "rows", path, errs)
        columns = _list(block, "columns", path, errs)
        for name, labels in (("rows", rows), ("columns", columns)):
            if not labels:
                errs.append(f"{path}.{name}: at least one")
            for i, label in enumerate(labels):
                if not isinstance(label, str):
                    errs.append(f"{path}.{name}[{i}]: must be a string")
        grid = _list(block, "values", path, errs)
        if len(grid) != len(rows):
            errs.append(f"{path}.values: must have one list per row ({len(rows)})")
        any_value = False
        for r, row in enumerate(grid):
            rpath = f"{path}.values[{r}]"
            if not isinstance(row, list) or len(row) != len(columns):
                errs.append(f"{rpath}: must have one value per column ({len(columns)})")
                continue
            for c, value in enumerate(row):
                if value is not None and not _number_ok(value):
                    errs.append(f"{rpath}[{c}]: must be a number or null")
                elif value is not None:
                    any_value = True
        if grid and not any_value and not any(e.startswith(f"{path}.values") for e in errs):
            errs.append(f"{path}.values: nothing to draw")
        scale = block.get("scale")
        if scale is not None and (
            not isinstance(scale, list) or len(scale) != 2 or not all(_number_ok(v) for v in scale)
        ):
            errs.append(f"{path}.scale: must be [low, high]")
        if not isinstance(block.get("show_values", True), bool):
            errs.append(f"{path}.show_values: must be true or false")


def _validate_nodes(
    block: Json, path: str, errs: list[str], node_ids: set[str], *, field: str, allowed: dict[str, str], default: str
) -> None:
    """Nodes with ids and labels, edges between them: a graph (by group) or a flowchart (by kind)."""
    ids: set[str] = set()
    for i, node in enumerate(_list(block, "nodes", path, errs)):
        npath = f"{path}.nodes[{i}]"
        if not isinstance(node, dict):
            errs.append(f"{npath}: must be an object")
            continue
        _str(node, "id", npath, errs)
        _str(node, "label", npath, errs)
        _str(node, "note", npath, errs, required=False)
        if node.get(field, default) not in allowed:
            errs.append(f"{npath}.{field}: must be one of {', '.join(allowed)}")
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
        _validate_nodes(block, path, errs, node_ids, field="group", allowed=GROUPS, default="module")
    elif kind == "flowchart":
        _validate_nodes(block, path, errs, node_ids, field="kind", allowed=FLOW_KINDS, default="step")
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
    elif kind == "chart":
        _validate_chart(block, path, errs)
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
_SAFE_URL = re.compile(r"^(https?://|#|\./|\.\./|/)|^[\w.~%-]+(/[\w.~%-]*)*(#[\w-]*)?$")


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
CHAR_W = 8.45  # JetBrains Mono at 14px (600 units to the em), with a small margin
NOTE_CHAR_W = 7.25  # JetBrains Mono at 12px
COL_GAP = 84
ROW_GAP = 16
PAD = 24
MAX_LABEL = 38

# Where each node group sits in the palette: the focal change in blue, what it reaches in orange.


def _clip(text: str, limit: int = MAX_LABEL) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _hex_plate(x: float, y: float, w: float, h: float, cut: float | None = None) -> str:
    """A box as a cell of the comb: a stretched hexagon, pointed at both ends. data-* keep the box it stands in."""
    c = min(16.0, h / 3) if cut is None else cut
    return (
        f'<path class="plate" data-x="{x:.1f}" data-y="{y:.1f}" data-w="{w:.1f}" data-h="{h:.1f}" '
        f'd="M{x + c:.1f},{y:.1f}H{x + w - c:.1f}L{x + w:.1f},{y + h / 2:.1f}L{x + w - c:.1f},{y + h:.1f}'
        f'H{x + c:.1f}L{x:.1f},{y + h / 2:.1f}Z"/>'
    )


def _hex_cut(h: float) -> float:
    """How far the points of a hexagon plate reach in: where a flag or a label must stop."""
    return min(16.0, h / 3)


def _capsule_plate(x: float, y: float, w: float, h: float) -> str:
    """A box with round ends, for where a flow starts and ends."""
    r = h / 2
    return (
        f'<path class="plate" data-x="{x:.1f}" data-y="{y:.1f}" data-w="{w:.1f}" data-h="{h:.1f}" '
        f'd="M{x + r:.1f},{y:.1f}H{x + w - r:.1f}A{r:.1f},{r:.1f} 0 0 1 {x + w - r:.1f},{y + h:.1f}'
        f'H{x + r:.1f}A{r:.1f},{r:.1f} 0 0 1 {x + r:.1f},{y:.1f}Z"/>'
    )


def _flow_plate(kind: str, x: float, y: float, w: float, h: float) -> str:
    """Start and end are capsules, a decision a cell with deep points, a step an ordinary cell."""
    if kind in ("start", "end"):
        return _capsule_plate(x, y, w, h)
    if kind == "decision":
        return _hex_plate(x, y, w, h, cut=h / 2)
    return _hex_plate(x, y, w, h)


def _node_box(node: Json, flow: bool = False) -> tuple[float, float]:
    label = _clip(node["label"])
    note = _clip(node.get("note", ""), 44)
    width = max(128.0, min(392.0, 46 + max(CHAR_W * len(label), NOTE_CHAR_W * len(note))))
    height = NODE_H + (NOTE_H if note else 0)
    if flow:  # deeper points and round ends need room beside the text
        kind = node.get("kind", "step")
        width += height - 32 if kind == "decision" else (8 if kind in ("start", "end") else 0)
    return width, height


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
    """Into the change and out of an entry point in blue, straight out of the change in orange,
    the next hops in a softer orange, everything else dimmed: the eye follows the change."""
    source, target = groups[edge["from"]], groups[edge["to"]]
    if target == "changed" or source == "entry":
        return "up"
    if source == "changed":
        return "down"
    if source == "affected":
        return "warm"
    return "dim"


def _graph_svg(block: Json, title: str, flow: bool = False) -> str:
    nodes = {n["id"]: n for n in block["nodes"]}
    ids = list(nodes)
    groups = {i: nodes[i].get("group", "module") for i in ids}
    kinds = {i: nodes[i].get("kind", "step") for i in ids}
    edges = [e for e in block.get("edges", []) if e["from"] in nodes and e["to"] in nodes]
    if not ids:
        return '<p class="muted">The graph is empty.</p>'
    layer, back = _layers(ids, edges)
    columns: list[list[str]] = [[] for _ in range(max(layer.values()) + 1)]
    for node_id in ids:
        columns[layer[node_id]].append(node_id)
    _order(columns, edges, back)

    size = {i: _node_box(nodes[i], flow) for i in ids}
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
        kind = "dim" if flow else _edge_class(edge, groups)
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
        css = f"f-{kinds[node_id]}" if flow else f"g-{groups[node_id]}"
        parts.append(
            f'<g class="node {css}" data-k="{_esc(node_id)}" data-label="{_esc(node["label"])}" '
            f'tabindex="0" role="button" aria-pressed="false"><title>{_esc(node["label"])}</title>'
        )
        parts.append(_flow_plate(kinds[node_id], x0, y0, w, h) if flow else _hex_plate(x0, y0, w, h))
        label_y = y0 + (24 if note else h / 2 + 5)
        parts.append(f'<text class="node-label" x="{x0 + 18:.1f}" y="{label_y:.1f}">{_esc(label)}</text>')
        if note:
            parts.append(f'<text class="node-note" x="{x0 + 18:.1f}" y="{y0 + 43:.1f}">{_esc(note)}</text>')
        parts.append("</g>")
    parts.extend(labels)
    parts.append("</svg>")
    return "".join(parts)


def _edge_list(block: Json, caption: str) -> str:
    """The edges as a table, for readers without the drawing and for print."""
    names = {n["id"]: n["label"] for n in block["nodes"]}
    rows = "".join(
        f"<tr><td><code>{_esc(names[e['from']])}</code></td><td><code>{_esc(names[e['to']])}</code></td>"
        f"<td>{_inline(e.get('label', ''))}</td></tr>"
        for e in block.get("edges", [])
    )
    if not rows:
        return ""
    return (
        f'<details class="graph-list"><summary>{caption} · {len(block.get("edges", []))} links</summary>'
        f'<div class="table-wrap"><table><thead><tr><th>From</th><th>To</th><th>How</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div></details>"
    )


def _graph(block: Json) -> str:
    title = block.get("title", "Graph")
    groups = [g for g in GROUPS if any(n.get("group", "module") == g for n in block["nodes"])]
    legend = "".join(f'<span class="legend-item"><i class="swatch g-{g}"></i>{_esc(GROUPS[g])}</span>' for g in groups)
    listing = _edge_list(block, "The graph as a list")
    return f'<div class="graph-wrap">{_graph_svg(block, title)}</div><div class="legend">{legend}</div>{listing}'


def _flowchart(block: Json) -> str:
    """A process with branches, drawn and traced like a graph; the shapes say what each node is."""
    title = block.get("title", "Flowchart")
    kinds = [k for k in FLOW_KINDS if any(n.get("kind", "step") == k for n in block["nodes"])]
    legend = "".join(
        f'<span class="legend-item"><i class="swatch f-{k}"></i>{_esc(FLOW_KINDS[k])}</span>' for k in kinds
    )
    listing = _edge_list(block, "The flowchart as a list")
    return (
        f'<div class="graph-wrap">{_graph_svg(block, title, flow=True)}</div>'
        f'<div class="legend">{legend}</div>{listing}'
    )


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
    fits = {"label": (box_w - 32) // 8, "line": (box_w - 32) // 7, "zone": (box_w + 2 * zpad - 20) // 9}
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
            + _hex_plate(x, y, w, h)
            + f'<text class="ck" x="{x + 16:.1f}" y="{y + 17:.1f}">{_esc(_clip(caption.upper(), fits["line"]))}</text>'
            f'<text class="cl" x="{x + 16:.1f}" y="{y + 36:.1f}">{_esc(_clip(comp["label"], fits["label"]))}</text>'
        )
        line = comp.get("tech") or comp.get("note")
        if line:
            parts.append(f'<text class="ct" x="{x + 16:.1f}" y="{y + 53:.1f}">{_esc(_clip(line, fits["line"]))}</text>')
        if comp.get("flag"):
            parts.append(f'<circle class="flag" cx="{x + w - _hex_cut(h) - 5:.1f}" cy="{y + 13:.1f}" r="4.5"/>')
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
        parts.append(
            f'<rect class="plate" data-x="{x:.1f}" data-y="{y:.1f}" data-w="{w:.1f}" data-h="{h:.1f}" x="{x:.1f}" '
            f'y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="12"/>'
        )
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
            _hex_plate(x, y, w, h)
            + f'<text class="ck" x="{x + 16:.1f}" y="{y + 17:.1f}">{_esc(_clip(caption.upper(), 21))}</text>'
            + f'<text class="cl" x="{x + 16:.1f}" y="{y + 36:.1f}">{_esc(_clip(comp["label"], 20))}</text>'
        )
        line = comp.get("tech") or comp.get("note")
        if line:
            parts.append(f'<text class="ct" x="{x + 16:.1f}" y="{y + 53:.1f}">{_esc(_clip(line, 23))}</text>')
        if comp.get("flag"):
            parts.append(f'<circle class="flag" cx="{x + w - _hex_cut(h) - 5:.1f}" cy="{y + 13:.1f}" r="4.5"/>')
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
            + _hex_plate(x, y, MODEL_W, h)
            + f'<text class="ck" x="{x + 16:.1f}" y="{y + 17:.1f}">{_esc(kind.upper())}</text>'
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
            parts.append(f'<circle class="flag" cx="{x + MODEL_W - _hex_cut(h) - 5:.1f}" cy="{y + 13:.1f}" r="4.5"/>')
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

# ---------------------------------------------------------------------------- chart

CHART_W = 900.0
CHAR_13 = 7.85  # JetBrains Mono at 13px
CHART_MAX_THICK = 22  # thin marks: a bar never fills its band
MINUS = chr(0x2212)
SERIES_CLASSES = tuple(f"cs{i}" for i in range(CHART_MAX_SERIES))
HEAT_STEPS = 6  # sequential: one hue, recedes to the surface at the low end, bright at the high end


def _chart_places(values: list[float], given: Json) -> int:
    if isinstance(given, int) and not isinstance(given, bool):
        return given
    return 0 if all(float(v).is_integer() for v in values) else 2


def _chart_value(value: float, places: int, unit: str = "") -> str:
    text = f"{abs(value):,.{places}f}"
    if value < 0:
        text = MINUS + text
    if unit == "%":
        return f"{text}%"
    return f"{text} {unit}" if unit else text


def _tick_text(value: float, top: float) -> str:
    """Round axis labels: in full under 10,000, compact (10K, 2.5M) on an axis that reaches it."""
    if value == 0:
        return "0"
    size = abs(value)
    if top >= 1_000_000:
        text = f"{size / 1_000_000:g}M"
    elif top >= 10_000:
        text = f"{size / 1000:g}K"
    else:
        text = f"{size:,g}"
    return (MINUS + text) if value < 0 else text


def _nice_ticks(low: float, high: float, count: int = 5) -> tuple[list[float], float, float]:
    """Round tick values, and the domain (which starts and ends on a tick) that holds low to high."""
    if low == high:
        high = low + 1.0
    raw = (high - low) / max(count - 1, 1)
    power = 10 ** math.floor(math.log10(raw))
    step = next(m * power for m in (1, 2, 2.5, 5, 10) if m * power >= raw)
    start = math.floor(low / step) * step
    end = math.ceil(high / step) * step
    total = round((end - start) / step)
    ticks = [round(start + i * step, 10) for i in range(total + 1)]
    return ticks, start, end


def _end_rounded(x0: float, x1: float, y0: float, y1: float, *, vertical: bool, radius: float = 4) -> str:
    """A bar path with its value end rounded and its baseline end square."""
    if vertical:
        left, right = min(x0, x1), max(x0, x1)
        base, tip = y0, y1
        radius = min(radius, abs(tip - base), (right - left) / 2)
        if tip <= base:  # grows up
            return (
                f"M{left:.1f},{base:.1f} V{tip + radius:.1f} Q{left:.1f},{tip:.1f} {left + radius:.1f},{tip:.1f} "
                f"H{right - radius:.1f} Q{right:.1f},{tip:.1f} {right:.1f},{tip + radius:.1f} V{base:.1f} Z"
            )
        return (
            f"M{left:.1f},{base:.1f} V{tip - radius:.1f} Q{left:.1f},{tip:.1f} {left + radius:.1f},{tip:.1f} "
            f"H{right - radius:.1f} Q{right:.1f},{tip:.1f} {right:.1f},{tip - radius:.1f} V{base:.1f} Z"
        )
    top, bottom = min(y0, y1), max(y0, y1)
    base, tip = x0, x1
    radius = min(radius, abs(tip - base), (bottom - top) / 2)
    if tip >= base:  # grows right
        return (
            f"M{base:.1f},{top:.1f} H{tip - radius:.1f} Q{tip:.1f},{top:.1f} {tip:.1f},{top + radius:.1f} "
            f"V{bottom - radius:.1f} Q{tip:.1f},{bottom:.1f} {tip - radius:.1f},{bottom:.1f} H{base:.1f} Z"
        )
    return (
        f"M{base:.1f},{top:.1f} H{tip + radius:.1f} Q{tip:.1f},{top:.1f} {tip:.1f},{top + radius:.1f} "
        f"V{bottom - radius:.1f} Q{tip:.1f},{bottom:.1f} {tip + radius:.1f},{bottom:.1f} H{base:.1f} Z"
    )


def _wrap(text: str, width: int, lines: int = 2) -> list[str]:
    """Split a label at spaces into at most `lines` lines of `width` characters; the last line is clipped."""
    words, out, current = text.split(), [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            out.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    out.append(current)
    if len(out) > lines:
        out[lines - 1] = _clip(" ".join(out[lines - 1 :]), width)
    return [_clip(line, width) for line in out[:lines]]


def _svg_open(height: float, title: str) -> str:
    return (
        f'<svg class="chart-svg" role="img" aria-label="{_esc(title)}" viewBox="0 0 {CHART_W:.0f} {height:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg">'
    )


def _axis_lines(ticks: list[float], x0: float, x1: float, y_of: Any, top: float) -> list[str]:
    parts = [
        f'<line class="grid{" zero" if tick == 0 else ""}" x1="{x0:.1f}" y1="{y_of(tick):.1f}" x2="{x1:.1f}" '
        f'y2="{y_of(tick):.1f}"/>'
        f'<text class="tick" x="{x0 - 10:.1f}" y="{y_of(tick) + 4:.1f}" text-anchor="end">'
        f"{_tick_text(tick, top)}</text>"
        for tick in ticks
    ]
    return parts


def _chart_labels(block: Json, height: float, *, x_axis: bool) -> list[str]:
    """Plain axis names, set in text tokens, so the unit is never carried by the marks alone."""
    parts: list[str] = []
    if block.get("y_label") or block.get("unit"):
        text = block.get("y_label") or block.get("unit")
        parts.append(f'<text class="axis-title" x="8" y="14">{_esc(_clip(str(text), 60))}</text>')
    if block.get("x_label") and x_axis:
        parts.append(
            f'<text class="axis-title" x="{CHART_W - 8:.0f}" y="{height - 6:.1f}" text-anchor="end">'
            f"{_esc(_clip(str(block['x_label']), 60))}</text>"
        )
    return parts


def _chart_series_values(block: Json) -> list[float]:
    return [float(v) for s in block["series"] for v in s["values"] if v is not None]


def _bar_svg(block: Json, title: str) -> tuple[str, list[str]]:
    categories = block["categories"]
    series = block["series"]
    values = _chart_series_values(block)
    unit = block.get("unit", "")
    places = _chart_places(values, block.get("places"))
    labels = [_clip(c, 30) for c in categories]
    value_w = max((len(_chart_value(v, places, unit)) for v in values), default=4) * CHAR_13 + 12
    left = max(max((len(t) for t in labels), default=4) * CHAR_13 + 16, 90.0)
    has_neg = any(v < 0 for v in values)
    left_edge = left + (value_w if has_neg else 0)
    right_edge = CHART_W - value_w - 8
    low, high = min(0.0, *values), max(0.0, *values)
    span = high - low or 1.0
    scale = (right_edge - left_edge) / span
    zero_x = left_edge - low * scale
    n = len(series)
    thick = min(CHART_MAX_THICK, 22 if n == 1 else 16 if n <= 3 else 12)
    gap = 2  # the surface gap between neighbouring bars of one category
    band = n * thick + (n - 1) * gap + 14
    top = 26.0
    y = top
    bottom_y = top + band * len(categories) - 8
    parts: list[str] = [
        f'<line class="axis" x1="{zero_x:.1f}" y1="{top - 6:.1f}" x2="{zero_x:.1f}" y2="{bottom_y:.1f}"/>'
    ]
    for c_index, category in enumerate(categories):
        group_h = n * thick + (n - 1) * gap
        center = y + group_h / 2
        parts.append(
            f'<text class="cat" x="{left - 10:.1f}" y="{center + 4:.1f}" text-anchor="end">'
            f"{_esc(labels[c_index])}<title>{_esc(category)}</title></text>"
        )
        for s_index, item in enumerate(series):
            value = item["values"][c_index]
            bar_y = y + s_index * (thick + gap)
            if value is None:
                continue
            tip = zero_x + float(value) * scale
            text = _chart_value(float(value), places, unit)
            tooltip = f"{category}: {text}" if n == 1 else f"{category}, {item['name']}: {text}"
            path = _end_rounded(zero_x, tip, bar_y, bar_y + thick, vertical=False)
            parts.append(
                f'<g class="mark"><path class="bar {SERIES_CLASSES[s_index]}" d="{path}">'
                f"<title>{_esc(tooltip)}</title></path>"
            )
            if float(value) >= 0:
                parts.append(f'<text class="val" x="{tip + 6:.1f}" y="{bar_y + thick / 2 + 4:.1f}">{_esc(text)}</text>')
            else:
                parts.append(
                    f'<text class="val" x="{tip - 6:.1f}" y="{bar_y + thick / 2 + 4:.1f}" text-anchor="end">'
                    f"{_esc(text)}</text>"
                )
            parts.append("</g>")
        y += band
    height = y + 10
    return _svg_open(height, title) + "".join(parts) + "".join(
        _chart_labels(block, height, x_axis=False)
    ) + "</svg>", []


def _line_svg(block: Json, title: str) -> str:
    categories = block["categories"]
    series = block["series"]
    values = _chart_series_values(block)
    unit = block.get("unit", "")
    places = _chart_places(values, block.get("places"))
    zero = block.get("zero", True)
    low = min(0.0, *values) if zero else min(values)
    high = max(0.0, *values) if zero else max(values)
    ticks, y_low, y_high = _nice_ticks(low, high)
    left = 62.0
    end_w = max((len(_chart_value(v, places, unit)) for v in values), default=4) * CHAR_13 + 14
    right = CHART_W - end_w
    top = 26.0
    bottom = 300.0
    span = y_high - y_low or 1.0

    def y_of(value: float) -> float:
        return bottom - (float(value) - y_low) * (bottom - top) / span

    n = len(categories)

    def x_of(index: int) -> float:
        return left + (right - left) / 2 if n == 1 else left + index * (right - left) / (n - 1)

    parts = _axis_lines(ticks, left, right, y_of, y_high)
    label_every = max(
        1, math.ceil(max((len(c) for c in categories), default=1) * CHAR_13 * 1.3 / ((right - left) / max(n, 1)))
    )
    for i, category in enumerate(categories):
        if i % label_every == 0 or i == n - 1:
            parts.append(
                f'<text class="tick" x="{x_of(i):.1f}" y="{bottom + 22:.1f}" text-anchor="middle">'
                f"{_esc(_clip(category, 16))}</text>"
            )
    ends: list[tuple[float, str]] = []
    dots = n <= 14
    for s_index, item in enumerate(series):
        cls = SERIES_CLASSES[s_index]
        points = [(i, v) for i, v in enumerate(item["values"]) if v is not None]
        if not points:
            continue
        coords = " ".join(f"{x_of(i):.1f},{y_of(v):.1f}" for i, v in points)
        parts.append(f'<polyline class="line {cls}" points="{coords}"/>')
        for i, v in points:
            text = _chart_value(float(v), places, unit)
            tooltip = f"{categories[i]}: {text}" if len(series) == 1 else f"{categories[i]}, {item['name']}: {text}"
            is_end = (i, v) == points[-1]
            dot = f'<circle class="dot {cls}" cx="{x_of(i):.1f}" cy="{y_of(v):.1f}" r="4"/>' if dots or is_end else ""
            parts.append(
                f'<g class="mark">{dot}<circle class="hit" cx="{x_of(i):.1f}" cy="{y_of(v):.1f}" r="12" '
                f'fill="transparent">'
                f"<title>{_esc(tooltip)}</title></circle></g>"
            )
        ends.append((y_of(points[-1][1]), _chart_value(float(points[-1][1]), places, unit)))
    ends.sort(key=lambda e: e[0])
    used: list[float] = []
    for y, text in ends:
        if any(abs(y - other) < 16 for other in used):
            continue
        used.append(y)
        parts.append(f'<text class="val" x="{right + 10:.1f}" y="{y + 4:.1f}">{_esc(text)}</text>')
    height = bottom + 42
    notice = (
        []
        if zero
        else [
            f'<text class="axis-title" x="{CHART_W - 8:.0f}" y="14" text-anchor="end">'
            "axis does not start at zero</text>"
        ]
    )
    return (
        _svg_open(height, title)
        + "".join(parts)
        + "".join(_chart_labels(block, height, x_axis=True))
        + "".join(notice)
        + "</svg>"
    )


def _waterfall_svg(block: Json, title: str) -> tuple[str, list[str]]:
    items = block["items"]
    unit = block.get("unit", "")
    values = [float(i["value"]) for i in items]
    places = _chart_places(values, block.get("places"))
    running = 0.0
    bars: list[tuple[float, float, str]] = []  # base, tip, kind
    levels = [0.0]
    for item in items:
        value = float(item["value"])
        if item.get("total"):
            bars.append((0.0, value, "total"))
            running = value
        else:
            bars.append((running, running + value, "up" if value >= 0 else "down"))
            running += value
        levels.append(running)
    ticks, y_low, y_high = _nice_ticks(min(levels), max(levels))
    left = 62.0
    right = CHART_W - 12
    top = 30.0
    bottom = 310.0
    span = y_high - y_low or 1.0

    def y_of(value: float) -> float:
        return bottom - (float(value) - y_low) * (bottom - top) / span

    n = len(items)
    band = (right - left) / n
    bar_w = min(band * 0.56, 64.0)
    parts = _axis_lines(ticks, left, right, y_of, y_high)
    label_chars = max(int(band / CHAR_13) - 1, 6)
    x_center = [left + band * (i + 0.5) for i in range(n)]
    for i in range(n - 1):
        level = bars[i][1]
        parts.append(
            f'<line class="connector" x1="{x_center[i] + bar_w / 2:.1f}" y1="{y_of(level):.1f}" '
            f'x2="{x_center[i + 1] - bar_w / 2:.1f}" y2="{y_of(level):.1f}"/>'
        )
    for i, item in enumerate(items):
        base, tip, kind = bars[i]
        cx = x_center[i]
        x0, x1 = cx - bar_w / 2, cx + bar_w / 2
        value_text = _chart_value(float(item["value"]), places, unit if kind == "total" else "")
        if kind != "total" and float(item["value"]) > 0:
            value_text = "+" + value_text
        tooltip = f"{item['label']}: {_chart_value(float(item['value']), places, unit)}"
        if kind != "total":
            tooltip += f" (running total {_chart_value(tip, places, unit)})"
        path = _end_rounded(x0, x1, y_of(base), y_of(tip), vertical=True)
        parts.append(f'<g class="mark"><path class="bar wf-{kind}" d="{path}"><title>{_esc(tooltip)}</title></path>')
        label_y = min(y_of(base), y_of(tip)) - 7
        if kind == "down":
            label_y = y_of(tip) + 16
            if label_y > bottom - 2:
                label_y = y_of(base) - 7
        parts.append(
            f'<text class="val" x="{cx:.1f}" y="{label_y:.1f}" text-anchor="middle">{_esc(value_text)}</text></g>'
        )
        for line_no, part in enumerate(_wrap(item["label"], label_chars)):
            parts.append(
                f'<text class="cat" x="{cx:.1f}" y="{bottom + 20 + line_no * 16:.1f}" text-anchor="middle">'
                f"{_esc(part)}</text>"
            )
    legend = []
    for kind, label in (("up", "Increase"), ("down", "Decrease"), ("total", "Total")):
        if any(k == kind for _, _, k in bars):
            legend.append(f'<span class="legend-item"><i class="swatch sw-{kind}"></i>{label}</span>')
    height = bottom + 62
    return _svg_open(height, title) + "".join(parts) + "".join(
        _chart_labels(block, height, x_axis=False)
    ) + "</svg>", legend


def _heat_color(value: float, low: float, high: float) -> int:
    if high <= low:
        return HEAT_STEPS - 1
    return min(HEAT_STEPS - 1, int((value - low) / (high - low) * HEAT_STEPS))


def _heatmap_svg(block: Json, title: str) -> tuple[str, list[str]]:
    rows = block["rows"]
    columns = block["columns"]
    grid = block["values"]
    flat = [float(v) for r in grid for v in r if v is not None]
    unit = block.get("unit", "")
    places = _chart_places(flat, block.get("places"))
    scale = block.get("scale")
    low = float(scale[0]) if scale else (min(flat) if flat else 0.0)
    high = float(scale[1]) if scale else (max(flat) if flat else 1.0)
    row_labels = [_clip(r, 26) for r in rows]
    left = max(max((len(t) for t in row_labels), default=4) * CHAR_13 + 18, 70.0)
    cell_w = max(36.0, min(84.0, (CHART_W - left - 8) / max(len(columns), 1)))
    cell_h = 34.0
    top = 34.0
    parts: list[str] = []
    for c, column in enumerate(columns):
        parts.append(
            f'<text class="tick" x="{left + c * cell_w + cell_w / 2:.1f}" y="{top - 12:.1f}" text-anchor="middle">'
            f"{_esc(_clip(column, 10))}<title>{_esc(column)}</title></text>"
        )
    show_values = block.get("show_values", len(columns) <= 14) and cell_w >= 44
    for r, row in enumerate(rows):
        y = top + r * cell_h
        parts.append(
            f'<text class="cat" x="{left - 10:.1f}" y="{y + cell_h / 2 + 4:.1f}" text-anchor="end">'
            f"{_esc(row_labels[r])}<title>{_esc(row)}</title></text>"
        )
        for c, column in enumerate(columns):
            value = grid[r][c]
            x = left + c * cell_w
            if value is None:
                parts.append(
                    f'<g class="mark"><rect class="heat-empty" x="{x + 1:.1f}" y="{y + 1:.1f}" '
                    f'width="{cell_w - 2:.1f}" '
                    f'height="{cell_h - 2:.1f}" rx="3"><title>{_esc(row)}, {_esc(column)}: no data</title></rect></g>'
                )
                continue
            step = _heat_color(float(value), low, high)
            text = _chart_value(float(value), places, unit)
            cell = (
                f'<g class="mark"><rect class="heat h{step}" x="{x + 1:.1f}" y="{y + 1:.1f}" width="{cell_w - 2:.1f}" '
                f'height="{cell_h - 2:.1f}" rx="3"><title>{_esc(row)}, {_esc(column)}: {_esc(text)}</title></rect>'
            )
            if show_values:
                cell += (
                    f'<text class="heat-val{" on-light" if step >= 3 else ""}" x="{x + cell_w / 2:.1f}" '
                    f'y="{y + cell_h / 2 + 4:.1f}" text-anchor="middle">'
                    f"{_esc(_chart_value(float(value), places, ''))}</text>"
                )
            parts.append(cell + "</g>")
    grid_bottom = top + len(rows) * cell_h
    legend_y = grid_bottom + 18
    swatch_w = 34.0
    legend_x = left
    parts.append(
        f'<text class="tick" x="{legend_x - 6:.1f}" y="{legend_y + 10:.1f}" text-anchor="end">'
        f"{_esc(_chart_value(low, places, unit))}</text>"
    )
    for s in range(HEAT_STEPS):
        parts.append(
            f'<rect class="heat h{s}" x="{legend_x + s * swatch_w:.1f}" y="{legend_y:.1f}" width="{swatch_w - 2:.1f}" '
            'height="12" rx="2"/>'
        )
    parts.append(
        f'<text class="tick" x="{legend_x + HEAT_STEPS * swatch_w + 6:.1f}" y="{legend_y + 10:.1f}">'
        f"{_esc(_chart_value(high, places, unit))}</text>"
    )
    height = legend_y + 28
    return _svg_open(height, title) + "".join(parts) + "".join(
        _chart_labels(block, height, x_axis=False)
    ) + "</svg>", []


def _chart_table_html(columns: list[str], rows: list[list[str]]) -> str:
    """The chart's data, for readers without the drawing, screen readers and print; every cell is plain escaped text."""
    head = "".join(f'<th class="a-{"left" if i == 0 else "right"}">{_esc(c)}</th>' for i, c in enumerate(columns))
    body = "".join(
        "<tr>"
        + "".join(f'<td class="a-{"left" if i == 0 else "right"}">{_esc(cell)}</td>' for i, cell in enumerate(row))
        + "</tr>"
        for row in rows
    )
    return (
        f'<div class="chart-data table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
    )


def _chart_table(block: Json) -> str:
    return _chart_table_html(*_chart_rows(block))


def _chart_rows(block: Json) -> tuple[list[str], list[list[str]]]:
    """The chart's numbers as columns and rows of text."""
    kind = block["kind"]
    unit = block.get("unit", "")
    if kind == "waterfall":
        values = [float(i["value"]) for i in block["items"]]
        places = _chart_places(values, block.get("places"))
        rows = []
        running = 0.0
        for item in block["items"]:
            value = float(item["value"])
            if item.get("total"):
                running = value
                rows.append([item["label"], "", _chart_value(value, places, unit)])
            else:
                running += value
                rows.append(
                    [
                        item["label"],
                        ("+" if value > 0 else "") + _chart_value(value, places, unit),
                        _chart_value(running, places, unit),
                    ]
                )
        return ["Step", "Change", "Running total"], rows
    if kind == "heatmap":
        flat = [float(v) for r in block["values"] for v in r if v is not None]
        places = _chart_places(flat, block.get("places"))
        cells = [
            [row] + ["" if v is None else _chart_value(float(v), places, unit) for v in values]
            for row, values in zip(block["rows"], block["values"], strict=True)
        ]
        return ["", *block["columns"]], cells
    places = _chart_places(_chart_series_values(block), block.get("places"))
    rows = [
        [category]
        + ["" if s["values"][i] is None else _chart_value(float(s["values"][i]), places, unit) for s in block["series"]]
        for i, category in enumerate(block["categories"])
    ]
    return [block.get("x_label") or "", *[s["name"] for s in block["series"]]], rows


def _chart(block: Json) -> str:
    kind = block["kind"]
    title = block.get("title") or kind
    legend: list[str] = []
    if kind == "bar":
        svg, legend = _bar_svg(block, title)
    elif kind == "line":
        svg = _line_svg(block, title)
    elif kind == "waterfall":
        svg, legend = _waterfall_svg(block, title)
    else:
        svg, legend = _heatmap_svg(block, title)
    if kind in ("bar", "line") and len(block["series"]) >= 2:
        legend = [
            f'<span class="legend-item"><i class="swatch sw-{SERIES_CLASSES[i]}"></i>{_esc(s["name"])}</span>'
            for i, s in enumerate(block["series"])
        ]
    legend_html = f'<div class="legend">{"".join(legend)}</div>' if legend else ""
    caption = f'<p class="chart-caption">{_inline(block["caption"])}</p>' if block.get("caption") else ""
    return f'<figure class="chart plate">{svg}{legend_html}{caption}</figure>{_chart_table(block)}'


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
    elif kind == "flowchart":
        body = _flowchart(block)
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
    elif kind == "chart":
        body = _chart(block)
    else:  # kv
        rows = "".join(f"<dt>{_cell(k)}</dt><dd>{_cell(v)}</dd>" for k, v in block["items"])
        body = f'<dl class="kv">{rows}</dl>'
    return f'<div class="block b-{kind}">{title}{body}</div>'


# ---------------------------------------------------------------------------- page

# The page design, written for this repository: a hive. Dark only; every text colour clears 4.5:1 on the panel
# surface. The tokens, the honeycomb and the hexagons are in CSS below; the boxes of the diagrams are drawn by
# _hex_plate.

LATIN = (
    "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, "
    "U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD"
)
LATIN_EXT = (
    "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, "
    "U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF"
)
# Variable fonts, the Latin and Latin Extended subsets (the second holds š, đ, č, ć, ž).
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


def _honeycomb() -> str:
    """The background tile: flat-top hexagons with a 28px side, one whole cell and the corners of four more."""
    side, height = 28.0, 28.0 * math.sqrt(3)

    def cell(cx: float, cy: float) -> str:
        points = (
            (cx + side, cy),
            (cx + side / 2, cy + height / 2),
            (cx - side / 2, cy + height / 2),
            (cx - side, cy),
            (cx - side / 2, cy - height / 2),
            (cx + side / 2, cy - height / 2),
        )
        return "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in points) + "Z"

    centres = ((0, 0), (1.5 * side, height / 2), (3 * side, 0), (0, height), (3 * side, height))
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{3 * side:.0f}" height="{height:.1f}" '
        f'viewBox="0 0 {3 * side:.0f} {height:.1f}"><path d="{"".join(cell(x, y) for x, y in centres)}" '
        'fill="none" stroke="#f2b632" stroke-opacity=".11"/></svg>'
    )
    return "data:image/svg+xml," + quote(svg, safe="")


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


# The page design: a hive. A dark amber ground with a faint honeycomb and a warm glow at the top, honey as the one
# accent, panels with a honey edge, Bricolage Grotesque for text and JetBrains Mono for labels. Counters, tags and
# the boxes of every diagram are hexagons: the cells of the comb. In graphs, honey marks what leads to a change
# and sky blue what it reaches.
CSS = """
:root{--ground:#120e08;--bg:#1a140b;--surface:#1d160c;--surface-2:#261d10;--surface-3:#312617;--ink:#f7f0e3;
--ink-2:rgba(247,240,227,.7);--ink-3:rgba(247,240,227,.5);--line:rgba(242,182,50,.2);--line-2:rgba(242,182,50,.1);
--accent:#f2b632;--accent-2:#ffd166;--accent-bg:rgba(242,182,50,.13);--accent-bg-2:rgba(242,182,50,.26);
--down:#6cb4ff;--down-bg:rgba(108,180,255,.14);--amber:#ff8f45;--amber-bg:rgba(255,143,69,.14);--red:#ff7b6e;
--red-bg:rgba(255,123,110,.14);--green:#8ae0a3;--green-bg:rgba(138,224,163,.12);--aqua:#3fc8ad;
--aqua-bg:rgba(63,200,173,.12);--magenta:#e88fbe;--user:#cdbd9f;--node:#221a0f;--node-line:#5e4a22;
--edge:rgba(247,240,227,.3);--plate:linear-gradient(160deg,#281e10 0%,#1b150c 100%);--plate-border:rgba(242,182,50,.24);
--hex:polygon(25% 0,75% 0,100% 50%,75% 100%,25% 100%,0 50%);
--cell:polygon(8px 0,calc(100% - 8px) 0,100% 50%,calc(100% - 8px) 100%,8px 100%,0 50%);
--sans:'Bricolage Grotesque',ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif;
--mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color-scheme:dark}
*{margin:0;padding:0;box-sizing:border-box}
html{background:var(--ground)}
body{position:relative;min-height:100%;background:var(--ground);color:var(--ink);font:400 17px/1.55 var(--sans);
-webkit-font-smoothing:antialiased}
body::before{content:'';position:absolute;left:0;right:0;top:0;height:min(1500px,100%);z-index:0;pointer-events:none;
background:radial-gradient(1500px 820px at 50% 380px,#2e210b 0%,#1b1409 55%,rgba(18,14,8,0) 100%)}
body::after{content:'';position:absolute;inset:0;z-index:0;pointer-events:none;background-size:84px 48.5px;
background-image:url("HONEYCOMB")}
main{position:relative;z-index:1;max-width:1360px;margin:0 auto;padding:60px 48px 96px}
a{color:var(--accent-2);text-decoration-color:rgba(255,209,102,.45);text-underline-offset:3px}
a:hover{text-decoration-color:currentColor}
code,pre{font-family:var(--mono);font-variant-ligatures:none}
code{font-size:.88em;color:var(--accent-2)}
strong{font-weight:700;color:var(--ink)}
p{max-width:1100px;text-wrap:pretty}
.muted{color:var(--ink-3)}
.status{display:flex;flex-wrap:wrap;align-items:center;gap:8px 22px;font:600 13px/1.4 var(--mono);letter-spacing:.14em;
text-transform:uppercase;color:var(--ink-3)}
.status .skill{display:inline-flex;align-items:center;gap:10px;color:var(--accent-2)}
.status .skill i{width:12px;height:13px;background:var(--accent);clip-path:var(--hex)}
.status b{font-weight:600;color:var(--ink-2);text-transform:none;letter-spacing:.04em}
h1{margin-top:18px;font-size:clamp(34px,4.6vw,58px);font-weight:800;letter-spacing:-.022em;line-height:1.05;
text-wrap:balance;max-width:1200px}
h1 code{font-size:.82em;font-weight:600}
.lead{margin-top:16px;font-size:clamp(18px,1.8vw,22px);line-height:1.45;color:var(--ink-2);max-width:1100px}
.plate{position:relative;background:var(--plate);border:1px solid var(--plate-border);border-radius:12px}
.label{position:absolute;left:24px;top:-13px;padding:6px 18px;background:var(--accent);color:var(--ground);
clip-path:var(--cell);font:700 11.5px/1.3 var(--mono);letter-spacing:.14em;text-transform:uppercase;white-space:nowrap;
max-width:calc(100% - 48px);overflow:hidden;text-overflow:ellipsis}
.verdict{margin-top:44px;padding:30px 32px 26px;font-size:clamp(18px,1.6vw,21px);line-height:1.5}
.verdict p+p{margin-top:10px}
.v-bad,.c-bad{border-color:rgba(255,123,110,.45)}.v-warn,.c-warn{border-color:rgba(255,143,69,.45)}
.v-ok,.c-ok{border-color:rgba(138,224,163,.4)}
.v-bad .label,.c-bad .label{background:var(--red)}.v-warn .label,.c-warn .label{background:var(--amber)}
.v-ok .label,.c-ok .label{background:var(--green)}.v-info .label,.c-info .label{background:var(--accent)}
.facts{display:grid;grid-template-columns:repeat(var(--cols),minmax(0,1fr));margin-top:40px;
border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.fact{padding:22px 26px 22px 0;border-bottom:1px solid var(--line)}
.fact.mid{border-left:1px solid var(--line);padding-left:26px}.fact.last{border-bottom:0}
.fact .l{font:600 12.5px/1.35 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3)}
.fact .v{margin-top:8px;font-size:clamp(28px,3vw,38px);font-weight:800;letter-spacing:-.015em;line-height:1.1;
font-variant-numeric:tabular-nums;text-wrap:balance;color:var(--accent-2)}
.fact .n{margin-top:6px;font-size:15px;line-height:1.4;color:var(--ink-2)}
.t-bad .v{color:var(--red)}.t-warn .v{color:var(--amber)}.t-ok .v{color:var(--green)}
nav.toc{display:flex;flex-wrap:wrap;gap:8px;margin-top:30px}
nav.toc a{padding:7px 20px;background:var(--surface-2);clip-path:var(--cell);font:600 12px/1.4 var(--mono);
letter-spacing:.1em;text-transform:uppercase;color:var(--ink-2);text-decoration:none}
nav.toc a span{color:var(--accent-2);margin-right:8px}nav.toc a:hover{background:var(--accent-bg-2);color:var(--ink)}
section{margin-top:76px;scroll-margin-top:24px}
section>header{display:flex;align-items:center;gap:16px;padding-bottom:14px;border-bottom:1px solid var(--line);
margin-bottom:24px}
section>header .n{flex:none;display:inline-grid;place-items:center;width:38px;height:34px;background:var(--accent);
color:var(--ground);clip-path:var(--hex);font:800 13px var(--mono)}
section>header h2{font-size:clamp(26px,2.8vw,36px);font-weight:700;letter-spacing:-.015em;line-height:1.1;
text-wrap:balance}
.intro{color:var(--ink-2)}
.block{margin-top:28px}.block:first-of-type{margin-top:0}.intro+.block{margin-top:20px}
.block>h3{font:600 12.5px/1.4 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);
margin-bottom:14px}
.block p+p{margin-top:12px}
.block>h3+.plate.labelled{margin-top:28px}
.tag{display:inline-block;font:700 10.5px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;padding:4px 10px;
clip-path:polygon(6px 0,calc(100% - 6px) 0,100% 50%,calc(100% - 6px) 100%,6px 100%,0 50%);vertical-align:2px;
margin-left:3px}
.tag-high{color:var(--green);background:var(--green-bg)}.tag-med{color:var(--amber);background:var(--amber-bg)}
.tag-guess{color:var(--red);background:var(--red-bg)}
ul.bul,ol.bul{list-style:none;display:grid;gap:10px;max-width:1100px}
ul.bul li,ol.bul li{position:relative;padding-left:26px}
ul.bul li::before{content:'';position:absolute;left:2px;top:.52em;width:9px;height:10px;background:var(--accent);
clip-path:var(--hex)}
ol.bul{counter-reset:b}ol.bul li{counter-increment:b}
ol.bul li::before{content:counter(b);position:absolute;left:0;font:700 .78em/1.95 var(--mono);color:var(--accent-2)}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th{font:600 12px/1.4 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);text-align:left;
padding:0 20px 10px 0;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:bottom}
td{padding:11px 20px 11px 0;border-bottom:1px solid var(--line-2);vertical-align:baseline;font-size:16px;
line-height:1.5}
tr:last-child td{border-bottom:0}
td.a-right,th.a-right{text-align:right}
td.a-right{font-family:var(--mono);font-size:14.5px;font-variant-numeric:tabular-nums}
td.a-center,th.a-center{text-align:center}
td:first-child{color:var(--ink)}td{color:var(--ink-2)}
.findings{display:grid;gap:14px}
.finding{position:relative;padding:22px 26px 20px;background:var(--plate);border:1px solid var(--plate-border);
border-radius:12px;box-shadow:inset 4px 0 0 var(--ink-3)}
.finding.f-high{box-shadow:inset 4px 0 0 var(--red)}.finding.f-medium{box-shadow:inset 4px 0 0 var(--amber)}
.finding.f-low{box-shadow:inset 4px 0 0 var(--green)}
.finding header{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.finding h4{font-size:21px;font-weight:700;line-height:1.3;letter-spacing:-.005em}
.finding.s-declined h4,.finding.s-fixed h4{color:var(--ink-2)}
.chip{font:700 10.5px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;padding:5px 12px;clip-path:var(--cell);
color:var(--ink-2);background:var(--surface-3)}
.chip.sev-high{color:var(--red);background:var(--red-bg)}.chip.sev-medium{color:var(--amber);background:var(--amber-bg)}
.chip.sev-low{color:var(--green);background:var(--green-bg)}.chip.sev-info{color:var(--accent-2);
background:var(--accent-bg)}
.where{font:500 14px/1.5 var(--mono);color:var(--accent-2);margin-top:5px;word-break:break-word}
.evidence{margin-top:10px;color:var(--ink-2);font-size:16.5px}
.fix{margin-top:14px;padding:12px 16px;border-radius:8px;background:rgba(18,14,8,.5);border:1px solid var(--line-2);
font-size:16.5px}
.fix-label{display:block;font:600 11.5px/1.6 var(--mono);letter-spacing:.14em;text-transform:uppercase;
color:var(--ink-3)}
figure.code{padding:16px 0 14px}figure.code.labelled{margin-top:26px;padding-top:26px}
figure.code pre{overflow-x:auto;font-size:14px;line-height:1.6}
.ln{display:block;padding:0 20px 0 0;white-space:pre;color:var(--ink)}
.ln .no{display:inline-block;width:3.6em;padding-right:1.1em;text-align:right;color:var(--ink-3);user-select:none}
.ln.hl{background:var(--accent-bg);box-shadow:inset 3px 0 0 var(--accent)}
.callout{margin-top:26px;padding:26px 24px 20px}
ol.steps{list-style:none;counter-reset:s;max-width:1100px}
ol.steps li{position:relative;counter-increment:s;padding:0 0 22px 50px}
ol.steps li::before{content:counter(s);position:absolute;left:0;top:0;width:30px;height:32px;display:grid;
place-items:center;background:var(--accent);color:var(--ground);clip-path:var(--hex);font:800 12.5px var(--mono)}
ol.steps li::after{content:'';position:absolute;left:14.5px;top:36px;bottom:4px;width:1px;background:var(--line)}
ol.steps li:last-child{padding-bottom:0}ol.steps li:last-child::after{display:none}
ol.steps h4{font-size:18px;font-weight:700;line-height:1.4}
ol.steps p{color:var(--ink-2);margin-top:4px;font-size:16px}
dl.kv{display:grid;grid-template-columns:minmax(140px,240px) 1fr;max-width:1100px}
dl.kv dt,dl.kv dd{padding:10px 0;border-bottom:1px solid var(--line-2)}
dl.kv dt{font:600 12px/1.7 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);
padding-right:16px}
dl.kv dd{font-size:16px;color:var(--ink)}
.graph-wrap{overflow-x:auto;border:1px solid var(--plate-border);border-radius:12px;background:var(--plate)}
svg.graph{display:block;height:auto;font-family:var(--mono)}
.node .plate{fill:var(--node);stroke:var(--node-line);stroke-width:1.1}
.node-label{font-size:14px;font-weight:500;fill:var(--ink)}.node-note{font-size:12px;fill:var(--ink-3)}
.g-entry .plate{stroke:var(--accent);stroke-width:1.6}
.g-boundary .plate{fill:var(--accent-bg);stroke:var(--accent)}
.g-changed .plate{fill:var(--accent-bg-2);stroke:var(--accent-2);stroke-width:2}.g-changed .node-label{font-weight:700}
.g-affected .plate{fill:var(--down-bg);stroke:var(--down);stroke-width:1.6}
.g-data .plate{fill:var(--aqua-bg);stroke:var(--aqua)}
.g-external .plate{fill:none;stroke:var(--ink-3);stroke-dasharray:5 4}
.g-test .plate{fill:none;stroke:var(--line)}.g-test .node-label{fill:var(--ink-2)}
.g-safe .plate{fill:var(--green-bg);stroke:var(--green)}
.g-unknown{opacity:.55}.g-unknown .plate{fill:none;stroke-dasharray:2 4}
.f-start .plate{fill:var(--accent-bg);stroke:var(--accent);stroke-width:1.6}
.f-end .plate{fill:var(--green-bg);stroke:var(--green);stroke-width:1.6}
.f-decision .plate{fill:var(--amber-bg);stroke:var(--amber);stroke-width:1.6}.f-decision .node-label{font-weight:600}
.edge{fill:none;stroke-width:1.3}.edge.dim{stroke:var(--edge)}
.edge.up{stroke:var(--accent);stroke-width:2}.edge.down{stroke:var(--down);stroke-width:2}
.edge.warm{stroke:rgba(108,180,255,.45)}.edge.back{stroke-dasharray:6 5}
.head-dim{fill:rgba(247,240,227,.45)}.head-up{fill:var(--accent)}.head-down{fill:var(--down)}
.head-warm{fill:rgba(108,180,255,.65)}
.edge-label{font-size:11.5px;fill:var(--ink-2);paint-order:stroke;stroke:#1d160c;stroke-width:5px;stroke-linejoin:round}
.edge-label.up{fill:var(--accent-2)}.edge-label.down,.edge-label.warm{fill:var(--down)}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:14px;font:400 12px/1.4 var(--mono);color:var(--ink-3)}
.legend-item{display:inline-flex;align-items:center;gap:7px}
.swatch{display:inline-block;width:16px;height:11px;clip-path:var(--hex);background:var(--node-line)}
.swatch::after{content:'';display:block;width:12px;height:7px;margin:2px;clip-path:var(--hex);background:var(--node)}
.swatch.g-entry{background:var(--accent)}.swatch.g-boundary{background:var(--accent)}
.swatch.g-boundary::after{background:#3f3416}
.swatch.g-changed{background:var(--accent-2)}.swatch.g-changed::after{background:#574419}
.swatch.g-affected{background:var(--down)}.swatch.g-affected::after{background:#243447}
.swatch.g-data{background:var(--aqua)}.swatch.g-data::after{background:#1f352e}
.swatch.g-external{background:var(--ink-3)}
.swatch.g-test{background:var(--line)}
.swatch.g-safe{background:var(--green)}.swatch.g-safe::after{background:#28392b}
.swatch.g-unknown{opacity:.6}
.swatch.f-start{background:var(--accent)}.swatch.f-start::after{background:#3f3416}
.swatch.f-end{background:var(--green)}.swatch.f-end::after{background:#28392b}
.swatch.f-decision{background:var(--amber)}.swatch.f-decision::after{background:#4a2e14}
.swatch.f-step{background:var(--node-line)}
details.graph-list{margin-top:14px}
details.graph-list summary{cursor:pointer;font:600 12px/1.4 var(--mono);letter-spacing:.1em;
text-transform:uppercase;color:var(--ink-3)}
details.graph-list .table-wrap{margin-top:12px}
footer{margin-top:80px;padding-top:16px;border-top:1px solid var(--line);font:400 12px/1.7 var(--mono);
color:var(--ink-3)}
@media (max-width:760px){main{padding:32px 16px 56px}body{font-size:16px}
.facts{grid-template-columns:1fr 1fr}.fact{padding:16px 16px 16px 0}.fact.mid{padding-left:16px}
section{margin-top:48px}td{font-size:15px}dl.kv{grid-template-columns:1fr}dl.kv dt{border-bottom:0;padding-bottom:0}
.verdict{padding:24px 18px 18px}.finding{padding:18px 16px 16px}ol.steps li{padding-left:42px}
.legend .hint{margin-left:0;width:100%}}
"""
CSS = CSS.replace("HONEYCOMB", _honeycomb())

# Series and heat colours follow the dataviz method for the dark panel: the six series pass its lightness, chroma,
# colour-blindness and 3:1 contrast checks against #1a140b (honey first, then blue, teal, coral, violet, olive), the
# heat steps are one honey from dark to light, and the cell text clears 4.5:1 on every step. Marks are thin, axis
# lines recessive, and text uses text tokens.
CSS += """
:root{--cs0:#bf8714;--cs1:#3f8ae0;--cs2:#1fa087;--cs3:#e35f55;--cs4:#9270e6;--cs5:#76a526}
figure.chart{padding:18px 18px 12px;margin-top:14px;overflow-x:auto}
svg.chart-svg{display:block;width:100%;min-width:640px;max-width:1040px;height:auto;font-family:var(--mono)}
.chart-svg text{fill:var(--ink-2);font-size:12.5px}.chart-svg .tick,.chart-svg .axis-title{fill:var(--ink-3)}
.chart-svg .cat{fill:var(--ink)}.chart-svg .val{fill:var(--ink-2);font-size:12.5px;font-variant-numeric:tabular-nums}
.chart-svg .grid{stroke:var(--line-2);stroke-width:1}
.chart-svg .grid.zero,.chart-svg .axis{stroke:var(--line);stroke-width:1}
.chart-svg .connector{stroke:var(--ink-3);stroke-width:1}
.chart-svg .bar.cs0,.chart-svg .dot.cs0{fill:var(--cs0)}.chart-svg .bar.cs1,.chart-svg .dot.cs1{fill:var(--cs1)}
.chart-svg .bar.cs2,.chart-svg .dot.cs2{fill:var(--cs2)}.chart-svg .bar.cs3,.chart-svg .dot.cs3{fill:var(--cs3)}
.chart-svg .bar.cs4,.chart-svg .dot.cs4{fill:var(--cs4)}.chart-svg .bar.cs5,.chart-svg .dot.cs5{fill:var(--cs5)}
.chart-svg .dot{stroke:#1b150c;stroke-width:2;paint-order:stroke}
.chart-svg .line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.chart-svg .line.cs0{stroke:var(--cs0)}.chart-svg .line.cs1{stroke:var(--cs1)}.chart-svg .line.cs2{stroke:var(--cs2)}
.chart-svg .line.cs3{stroke:var(--cs3)}.chart-svg .line.cs4{stroke:var(--cs4)}.chart-svg .line.cs5{stroke:var(--cs5)}
.chart-svg .hit{fill:transparent}.chart-svg .mark:hover .bar,.chart-svg .mark:hover .dot{filter:brightness(1.2)}
.chart-svg .wf-up{fill:var(--cs0)}.chart-svg .wf-down{fill:var(--cs1)}.chart-svg .wf-total{fill:#7a6a4e}
.chart-svg .heat-val{fill:var(--ink);font-size:12px;font-variant-numeric:tabular-nums}
.chart-svg .heat-val.on-light{fill:#120e08}
.chart-svg .heat-empty{fill:none;stroke:var(--line-2);stroke-dasharray:3 3}
.h0{fill:#4a3306}.h1{fill:#6b4a08}.h2{fill:#8f640c}.h3{fill:#b8841a}.h4{fill:#dba82e}.h5{fill:#f5cf6a}
.swatch.sw-cs0,.swatch.sw-cs0::after{background:var(--cs0)}.swatch.sw-cs1,.swatch.sw-cs1::after{background:var(--cs1)}
.swatch.sw-cs2,.swatch.sw-cs2::after{background:var(--cs2)}.swatch.sw-cs3,.swatch.sw-cs3::after{background:var(--cs3)}
.swatch.sw-cs4,.swatch.sw-cs4::after{background:var(--cs4)}.swatch.sw-cs5,.swatch.sw-cs5::after{background:var(--cs5)}
.swatch.sw-up,.swatch.sw-up::after{background:var(--cs0)}.swatch.sw-down,.swatch.sw-down::after{background:var(--cs1)}
.swatch.sw-total,.swatch.sw-total::after{background:#7a6a4e}
.chart-caption{margin-top:10px;font-size:15px;color:var(--ink-2)}
.chart-data{margin-top:12px}.chart-data th{font-size:11px;padding-bottom:6px}
.chart-data td{font-size:14.5px;padding-top:6px;padding-bottom:6px}
"""

CSS += """
.graph .node{cursor:pointer;outline:none}.graph .node:focus-visible .plate{stroke:var(--ink);stroke-width:2.2}
.graph .node,.graph .edge,.graph .edge-label{transition:opacity .18s}
.graph.tracing .edge.off,.graph.tracing .edge-label.off{opacity:.07}.graph.tracing .node.off{opacity:.22}
.graph.tracing .edge.on-up{stroke:var(--accent);stroke-width:2.2;opacity:1}
.graph.tracing .edge.on-down{stroke:var(--down);stroke-width:2.2;opacity:1}
.graph.tracing .edge-label.on-up{fill:var(--accent-2)}.graph.tracing .edge-label.on-down{fill:var(--down)}
.graph.tracing .node.on-up .plate{stroke:var(--accent);stroke-width:1.8;fill:var(--accent-bg)}
.graph.tracing .node.on-down .plate{stroke:var(--down);stroke-width:1.8;fill:var(--down-bg)}
.graph.tracing .node.sel .plate{fill:var(--accent-bg-2);stroke:var(--accent-2);stroke-width:2.4}
.graph.tracing .node.sel .node-label{font-weight:700}
.legend .hint{margin-left:auto;color:var(--ink-3)}
.filter{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin-bottom:12px}
.filter input{width:min(360px,100%);padding:8px 12px;background:var(--surface-2);border:1px solid var(--line);
border-radius:8px;color:var(--ink);font:400 14px var(--mono)}
.filter input::placeholder{color:var(--ink-3)}.filter input:focus{outline:none;border-color:var(--accent)}
.filter .count{font:400 12px var(--mono);color:var(--ink-3)}
figure.code .copy{position:absolute;right:12px;top:10px;background:var(--surface-2);border:1px solid var(--line);
border-radius:6px;padding:4px 10px;font:700 10.5px/1.4 var(--mono);letter-spacing:.08em;text-transform:uppercase;
color:var(--ink-3);cursor:pointer}
figure.code .copy:hover{color:var(--ink);border-color:var(--accent)}
figure.code .copy.done{color:var(--green);border-color:var(--green)}
figure.code:not(.labelled){margin-top:14px;padding-top:40px}
"""

# The decision table and the architecture block. Without the script the architecture still reads: every
# component card, every flow and every variant note is listed; the script turns them into a panel, a
# step-through and a toggle (the html element gets the class "js").
CSS += """
.dec-wrap{overflow-x:auto}
table.dec th[scope=row]{font:inherit;letter-spacing:0;text-transform:none;white-space:normal;color:var(--ink);
padding:12px 16px 12px 12px;border-bottom:1px solid var(--line-2);vertical-align:top;min-width:200px}
table.dec thead th:first-child{padding-left:12px}
table.dec td{vertical-align:top;font-size:15px;line-height:1.5;min-width:118px}
.dec .opt{font-size:17px;font-weight:700}
.dec .why{margin-top:4px;font-size:14.5px;line-height:1.45;color:var(--ink-2)}
.dec .mark{display:inline-block;margin-right:6px;padding:3px 7px;clip-path:polygon(5px 0,calc(100% - 5px) 0,100% 50%,
calc(100% - 5px) 100%,5px 100%,0 50%);font:700 10px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;
vertical-align:1px}
.dec .r-pass .mark{color:var(--green);background:var(--green-bg)}
.dec .r-weak .mark{color:var(--amber);background:var(--amber-bg)}
.dec .r-fail .mark{color:var(--red);background:var(--red-bg)}
.dec tr.o-chosen th,.dec tr.o-chosen td{background:var(--accent-bg)}
.dec tr.o-chosen th{box-shadow:inset 3px 0 0 var(--accent)}
.dec tr.o-eliminated td:not(.st),.dec tr.o-eliminated .opt{opacity:.5}
.dec td.st{white-space:nowrap}
.dec .by{margin-top:6px;font:400 12.5px/1.4 var(--mono);color:var(--red);white-space:normal}
.chip.st-chosen{color:var(--ground);background:var(--accent)}
.chip.st-viable{color:var(--green);background:var(--green-bg)}
.chip.st-eliminated{color:var(--red);background:var(--red-bg)}
.arch-controls{display:none;flex-wrap:wrap;align-items:center;gap:8px 14px;margin-bottom:12px}
.js .arch-controls{display:flex}
.arch-controls button{background:var(--surface-2);color:var(--ink-2);border:1px solid var(--line);border-radius:7px;
padding:8px 12px;font:700 11px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;cursor:pointer}
.arch-controls button:hover{color:var(--ink);border-color:var(--accent)}
.arch-controls button:disabled{opacity:.35;cursor:default}
.arch-controls .seg{display:inline-flex;flex-wrap:wrap}
.arch-controls .seg button{border-radius:0;margin-left:-1px}
.arch-controls .seg button:first-child{border-radius:7px 0 0 7px;margin-left:0}
.arch-controls .seg button:last-child{border-radius:0 7px 7px 0}
.arch-controls .seg button:only-child{border-radius:7px}
.arch-controls .seg button[hidden]{display:none}
.arch-controls button[aria-pressed=true]{background:var(--accent);color:var(--ground);border-color:var(--accent)}
.arch-controls .arch-trust[aria-pressed=true]{background:var(--red);color:var(--ground);border-color:var(--red)}
.stepper{display:inline-flex;align-items:center;gap:6px}
.stepper .count{margin-left:6px;font:400 12px var(--mono);color:var(--ink-3)}
.arch-vlabel{padding:14px 18px 0;font:600 12px/1.4 var(--mono);letter-spacing:.14em;text-transform:uppercase;
color:var(--accent-2)}
.js .arch-vlabel,.js svg.arch-svg:not(.on){display:none}
.arch-stage{width:min(1820px,calc(100vw - 48px));margin-left:calc(50% - min(910px,50vw - 24px));overflow-x:auto;
border:1px solid var(--plate-border);border-radius:12px;background:var(--plate)}
svg.arch-svg{display:block;height:auto;font-family:var(--mono)}
svg.arch-svg.nested{margin:0 auto}
.zone-bg{fill:rgba(242,182,50,.03);stroke:var(--line);stroke-width:1}
.zone-label{font-size:11px;font-weight:600;letter-spacing:.1em;fill:var(--ink-3)}
.comp{cursor:pointer;outline:none;transition:opacity .18s}
.comp .plate{fill:var(--node);stroke:var(--node-line);stroke-width:1.1}
.comp .ck{font-size:10px;font-weight:600;letter-spacing:.1em;fill:var(--ink-3)}
.comp .cl{font-family:var(--sans);font-size:15.5px;font-weight:700;fill:var(--ink)}
.comp .ct{font-size:11.5px;fill:var(--accent-2)}
.comp:focus-visible .plate{stroke:var(--ink);stroke-width:2.2}
.k-user .plate,.k-channel .plate{stroke:var(--user)}
.k-model .plate{fill:var(--accent-bg);stroke:var(--accent)}
.k-retrieval .plate,.k-store .plate{fill:var(--aqua-bg);stroke:var(--aqua)}
.k-tool .plate{stroke:var(--magenta)}
.k-system .plate{fill:none;stroke:var(--ink-3);stroke-dasharray:5 4}
.k-human .plate{fill:var(--green-bg);stroke:var(--green)}
.k-guard .plate{stroke:var(--green)}
.k-ops .plate{fill:none;stroke:var(--line)}.k-ops .cl{fill:var(--ink-2)}
.comp.open-box .plate{fill:rgba(242,182,50,.025);stroke:var(--node-line);stroke-width:1.1;stroke-dasharray:7 5}
.comp.se .plate{stroke:var(--down);stroke-width:1.8}
.comp.vonly .plate{stroke-dasharray:4 3}
.comp.f-warn .plate{stroke:var(--amber);stroke-width:2.2}.comp.f-bad .plate{stroke:var(--red);stroke-width:2.3}
.comp.f-warn .flag{fill:var(--amber)}.comp.f-bad .flag{fill:var(--red)}
.link{fill:none;stroke:var(--edge);stroke-width:1.4;marker-end:url(#arch-arrow-base);transition:opacity .18s}
.link.untrusted{stroke:var(--red);stroke-dasharray:6 5;marker-end:url(#arch-arrow-red)}
.link.f-warn{stroke:var(--amber)}.link.f-bad{stroke:var(--red)}
.ah-base{fill:rgba(247,240,227,.55)}.ah-red{fill:var(--red)}.ah-in{fill:var(--accent)}.ah-out{fill:var(--down)}
.ah-hot{fill:var(--accent-2)}
.link-label{font-size:11px;fill:var(--ink-2);paint-order:stroke;stroke:#1d160c;stroke-width:5px;stroke-linejoin:round;
transition:opacity .18s}
.link-label.untrusted{fill:var(--red)}
.arch .comp.gone{opacity:.07;pointer-events:none}.arch .link.gone,.arch .link-label.gone{display:none}
.arch.focus .comp:not(.sel):not(.near):not(.hot):not(.gone){opacity:.3}
.arch.focus .link:not(.in):not(.out):not(.hot):not(.done),
.arch.focus .link-label:not(.in):not(.out):not(.hot){opacity:.1}
.comp.sel .plate{fill:var(--accent-bg-2);stroke:var(--accent-2);stroke-width:2.3}
.link.in{stroke:var(--accent);stroke-width:2.2;marker-end:url(#arch-arrow-in)}
.link.out{stroke:var(--down);stroke-width:2.2;marker-end:url(#arch-arrow-out)}
.link-label.in{fill:var(--accent-2)}.link-label.out{fill:var(--down)}.link-label.hot{fill:var(--accent-2)}
.link.hot{stroke:var(--accent-2);stroke-width:2.8;stroke-dasharray:8 6;marker-end:url(#arch-arrow-hot);
animation:arch-dash 1s linear infinite}
.link.done{stroke:rgba(255,209,102,.45);stroke-width:2;stroke-dasharray:none}
.comp.hot .plate{fill:var(--accent-bg-2);stroke:var(--accent-2);stroke-width:2.3}
@keyframes arch-dash{to{stroke-dashoffset:-28}}
@media (prefers-reduced-motion:reduce){.link.hot{animation:none}}
.arch.trust .comp:not(.taint):not(.gone){opacity:.32}
.arch.trust .comp.taint .plate{stroke:rgba(255,123,110,.75)}
.arch.trust .comp.risk .plate{fill:var(--red-bg);stroke:var(--red);stroke-width:2.6}
.arch.trust .link:not(.path):not(.untrusted),.arch.trust .link-label:not(.untrusted){opacity:.14}
.arch.trust .link.path{stroke:var(--red);stroke-width:2.3;opacity:1;marker-end:url(#arch-arrow-red)}
.arch-controls .arch-reach[aria-pressed=true]{background:var(--down);color:var(--ground);border-color:var(--down)}
.arch.reach .comp:not(.rch):not(.gone){opacity:.32}
.arch.reach .comp.rch .plate{stroke:rgba(108,180,255,.75)}
.arch.reach .comp.rhit .plate{fill:var(--down-bg);stroke:var(--down);stroke-width:2.6}
.arch.reach .link:not(.rpath),.arch.reach .link-label:not(.rpath){opacity:.14}
.arch.reach .link.rpath{stroke:var(--down);stroke-width:2.3;opacity:1;marker-end:url(#arch-arrow-out)}
svg.model-svg{display:block;height:auto;margin:0 auto;font-family:var(--mono)}
.tbl{cursor:pointer;outline:none;transition:opacity .18s}
.tbl .plate{fill:var(--node);stroke:var(--node-line);stroke-width:1.1}
.tbl .ck{font-size:10px;font-weight:600;letter-spacing:.1em;fill:var(--ink-3)}
.tbl .cl{font-family:var(--sans);font-size:15.5px;font-weight:700;fill:var(--ink)}
.tbl .cr{font-size:11.5px;fill:var(--accent-2)}.tbl .cr.none{fill:var(--red)}
.tbl .cm{font-size:11px;fill:var(--ink-3)}
.tbl:focus-visible .plate{stroke:var(--ink);stroke-width:2.2}
.m-fact .plate,.m-hub .plate{fill:var(--accent-bg);stroke:var(--accent)}
.m-dimension .plate,.m-satellite .plate{fill:var(--aqua-bg);stroke:var(--aqua)}
.m-bridge .plate,.m-link .plate{stroke:var(--magenta)}
.m-staging .plate{fill:none;stroke:var(--line);stroke-dasharray:5 4}
.tbl.f-warn .plate{stroke:var(--amber);stroke-width:2.2}.tbl.f-bad .plate{stroke:var(--red);stroke-width:2.3}
.tbl.f-warn .flag{fill:var(--amber)}.tbl.f-bad .flag{fill:var(--red)}
.rel{fill:none;stroke:var(--edge);stroke-width:1.4;marker-end:url(#model-arrow-base);transition:opacity .18s}
.rel.many{stroke:var(--red);stroke-dasharray:6 5}
.rel-label{font-size:11px;fill:var(--ink-2);paint-order:stroke;stroke:#1d160c;stroke-width:5px;stroke-linejoin:round;
transition:opacity .18s}
.rel-label.many{fill:var(--red)}
.mh-base{fill:rgba(247,240,227,.55)}.mh-on{fill:var(--down)}
.model.focus .tbl:not(.sel):not(.near){opacity:.3}
.model.focus .rel:not(.on),.model.focus .rel-label:not(.on){opacity:.1}
.tbl.sel .plate{fill:var(--accent-bg-2);stroke:var(--accent-2);stroke-width:2.3}
.tbl.near .plate{stroke:var(--down);stroke-width:2}
.rel.on{stroke:var(--down);stroke-width:2.2;marker-end:url(#model-arrow-on)}.rel-label.on{fill:var(--down)}
.tbl.out{opacity:.12}.model .rel.fade,.model .rel-label.fade{opacity:.08}
.swatch.m-fact,.swatch.m-hub{background:var(--accent)}.swatch.m-fact::after,.swatch.m-hub::after{background:#3f3416}
.swatch.m-dimension,.swatch.m-satellite{background:var(--aqua)}
.swatch.m-dimension::after,.swatch.m-satellite::after{background:#1f352e}
.swatch.m-bridge,.swatch.m-link{background:var(--magenta)}
.swatch.m-staging{background:var(--line)}
.model-card .grain{margin-top:6px;font-size:15.5px;color:var(--ink-2)}
.model-card .table-wrap{margin-top:12px}
.model-card td.mono{font:400 13.5px/1.5 var(--mono)}
.arch-caption{display:none;margin-top:12px;padding:12px 16px;border:1px solid rgba(255,209,102,.45);border-radius:8px;
background:var(--accent-bg);font-size:15.5px;color:var(--ink)}
.js .arch-caption.on{display:block}
.swatch.k-model{background:var(--accent)}.swatch.k-model::after{background:#3f3416}
.swatch.k-user,.swatch.k-channel{background:var(--user)}
.swatch.k-retrieval,.swatch.k-store{background:var(--aqua)}
.swatch.k-retrieval::after,.swatch.k-store::after{background:#1f352e}
.swatch.k-tool{background:var(--magenta)}
.swatch.k-system{background:var(--ink-3)}
.swatch.k-human,.swatch.k-guard{background:var(--green)}.swatch.k-human::after{background:#28392b}
.swatch.k-ops{background:var(--line)}
.swatch.se{background:var(--down)}
.swatch.vonly{opacity:.7}
.swatch.untrusted{height:0;width:16px;clip-path:none;border-top:2px dashed var(--red);background:none}
.swatch.untrusted::after{display:none}
.arch-vnotes{margin-top:14px;display:grid;gap:6px;color:var(--ink-2);font-size:15.5px}
.js .arch-vnote{display:none}.js .arch-vnote.open{display:block}
.arch-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;margin-top:22px}
.js .arch-cards{display:block}
.arch-card{padding:18px 22px}
.js .arch-card{display:none}.js .arch-card.open{display:block}
.arch-card header{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.arch-card h4{font-size:19px;font-weight:700;line-height:1.3}
.arch-card dl.kv{margin-top:10px;grid-template-columns:minmax(110px,200px) 1fr}
.arch-card dl.kv dd{font-size:15.5px}
.arch-card .io{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px 24px;margin-top:12px}
.arch-card .io ul{list-style:none;display:grid;gap:4px;font-size:15px;color:var(--ink-2)}
.arch-card .only,.arch-flow .only,.arch-card .io .only{font:400 12.5px/1.5 var(--mono);color:var(--ink-3)}
.arch-card .only{margin-top:10px}
.chip.se{color:var(--down);background:var(--down-bg)}
.chip.untrusted{color:var(--red);background:var(--red-bg);font-size:9.5px;padding:4px 9px}
.arch-hint{display:none;font:400 12px/1.6 var(--mono);color:var(--ink-3)}
.js .arch-hint{display:block}.js .arch-hint.off{display:none}
.arch-flows{margin-top:22px;display:grid;gap:18px}
.js .arch-flows{display:block}
.arch-flow h4{font:600 12px/1.4 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);
margin-bottom:10px}
.js .arch-flow{display:none}.js .arch-flow.open{display:block}
ol.flow-steps{list-style:none;counter-reset:fs;display:grid;gap:4px;max-width:1100px}
ol.flow-steps li{counter-increment:fs;position:relative;padding:9px 12px 9px 48px;border:1px solid transparent;
border-radius:8px;color:var(--ink-2);font-size:15.5px;line-height:1.5}
ol.flow-steps li::before{content:counter(fs);position:absolute;left:14px;top:10px;font:700 13px var(--mono);
color:var(--accent-2)}
ol.flow-steps .who{display:block;font:600 12px/1.5 var(--mono);color:var(--accent-2)}
.js ol.flow-steps li{cursor:pointer}
ol.flow-steps li.now{border-color:rgba(255,209,102,.5);background:var(--accent-bg);color:var(--ink)}
ol.flow-steps li.now .who{color:var(--accent)}
ol.flow-steps li.past{opacity:.6}
.arch-trustlist{margin-top:24px}
.arch-trustlist>h3{font:600 12px/1.4 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);
margin-bottom:12px}
@media print{.arch-controls,.arch-hint,.arch-caption{display:none!important}
.js .arch-vlabel,.js svg.arch-svg{display:block!important}
.js .arch-card,.js .arch-flow,.js .arch-vnote{display:block}.js .arch-cards{display:grid}
.arch .comp,.arch .link,.arch .link-label{opacity:1!important}}
"""

# One small inline script, the same on every page. It only adds behaviour; the page reads the same
# without it. Click a node to trace what leads to it (blue) and what it reaches (orange), Esc or a
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
header.site{position:sticky;top:0;z-index:30;background:rgba(18,14,8,.9);backdrop-filter:blur(10px);
border-bottom:1px solid var(--line)}
header.site .in{display:flex;align-items:center;gap:28px;max-width:1360px;height:56px;margin:0 auto;padding:0 48px}
header.site .home{flex:none;max-width:280px;overflow:hidden;font-size:16px;font-weight:600;letter-spacing:-.01em;
color:var(--ink);text-decoration:none;text-overflow:ellipsis;white-space:nowrap}
header.site nav{position:relative;display:flex;align-items:center;gap:4px;min-width:0;overflow-x:auto;
scrollbar-width:none;white-space:nowrap}
header.site nav::-webkit-scrollbar{display:none}
header.site nav a{flex:none;padding:5px 10px;border-radius:5px;font:400 13px/1.3 var(--mono);color:var(--ink-2);
text-decoration:none}
header.site nav a:hover{background:var(--line-2);color:var(--ink)}
header.site a:focus-visible{outline:2px solid var(--accent-2);outline-offset:-2px}
header.site nav a[aria-current]{background:var(--accent-bg-2);box-shadow:inset 0 0 0 1px var(--accent);
color:var(--ink)}
header.site .g{flex:none;margin-left:16px;padding-right:2px;font:600 11px/1.3 var(--mono);letter-spacing:.08em;
text-transform:uppercase;color:var(--ink-3)}
header.site .g:first-child{margin-left:0}
section{scroll-margin-top:84px}
@media (max-width:760px){header.site .in{gap:14px;height:50px;padding:0 16px}
header.site .home{max-width:130px;font-size:14px}}
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
        + (
            f"<footer>Written by render_page.py --index · {_esc(meta.get('written', ''))}</footer>"
            if skill == "index"
            else f"<footer>Written by the {_esc(skill)} skill{date} · numbers from the skill's scripts · "
            "claims tagged high (checked), med (likely), guess (not checked)</footer>"
        )
        + f"</main><script>{SCRIPT}{SITE_SCRIPT if bar else ''}</script></body></html>\n"
    )


# ---------------------------------------------------------------------------- markdown


def _plain(value: Json) -> str:
    """A cell as text, numbers formatted the way the page shows them."""
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return value if isinstance(value, str) else ""


def _md_cell(value: Json) -> str:
    return _plain(value).replace("|", "\\|").replace("\n", " ")


def _md_table(columns: list[Json], rows: list[list[Json]]) -> str:
    head = "| " + " | ".join(_md_cell(c) for c in columns) + " |"
    rule = "|" + "|".join("---" for _ in columns) + "|"
    body = ["| " + " | ".join(_md_cell(v) for v in row) + " |" for row in rows]
    return "\n".join([head, rule, *body])


def _md_quote(text: str) -> str:
    return "\n".join(f"> {line}" for line in text.split("\n"))


def _md_block(block: Json) -> str:
    """One block as Markdown. A drawing becomes its table; the page keeps the drawing."""
    kind = block["type"]
    out: list[str] = []
    if block.get("title"):
        out.append(f"### {block['title']}")
    if kind == "text":
        out.append(block["text"])
    elif kind == "callout":
        out.append(_md_quote(f"**{TONE_LABEL[block.get('tone', 'info')]}:** {block['text']}"))
    elif kind == "list":
        ordered = block.get("ordered", False)
        out.append("\n".join((f"{i}. " if ordered else "- ") + item for i, item in enumerate(block["items"], 1)))
    elif kind == "table":
        out.append(_md_table(block["columns"], block["rows"]))
    elif kind == "kv":
        out.append("\n".join(f"- **{_plain(k)}:** {_plain(v)}" for k, v in block["items"]))
    elif kind == "code":
        where = f"`{block['where']}`\n\n" if block.get("where") else ""
        out.append(where + "```\n" + block["code"].rstrip("\n") + "\n```")
    elif kind == "steps":
        lines = []
        for i, item in enumerate(block["items"], 1):
            line = f"{i}. **{item['title']}**" + (f" — `{item['where']}`" if item.get("where") else "")
            if item.get("text"):
                line += "\n   " + item["text"].replace("\n", "\n   ")
            lines.append(line)
        out.append("\n".join(lines))
    elif kind == "findings":
        order = {s: i for i, s in enumerate(SEVERITIES)}
        for item in sorted(block["items"], key=lambda f: order[f["severity"]]):
            status = item.get("status", "open")
            head = (
                f"**{item['severity'].upper()}" + (f" · {status}" if status != "open" else "") + f" · {item['title']}**"
            )
            if item.get("where"):
                head += f" — `{item['where']}`"
            parts = [head]
            if item.get("evidence"):
                parts.append(item["evidence"])
            if item.get("fix"):
                parts.append(f"*Fix:* {item['fix']}")
            if item.get("reason"):
                parts.append(f"*Declined because:* {item['reason']}")
            out.append("\n\n".join(parts))
    elif kind in ("graph", "flowchart"):
        names = {n["id"]: n["label"] for n in block["nodes"]}
        out.append(f"*{len(block['nodes'])} nodes, {len(block.get('edges', []))} links; the drawing is on the page.*")
        out.append(
            _md_table(
                ["From", "To", "How"],
                [[names[e["from"]], names[e["to"]], e.get("label", "")] for e in block.get("edges", [])],
            )
        )
    elif kind == "decision":
        rows = []
        for opt in block["options"]:
            status = opt.get("status", "viable")
            if status == "eliminated" and opt.get("eliminated_by"):
                status += f" by {opt['eliminated_by']}"
            label = f"**{opt['label']}**" + (f" {opt['why']}" if opt.get("why") else "")
            rows.append([label, *[f"{c['rating']}: {c.get('text', '')}" for c in opt["cells"]], status])
        out.append(_md_table(["Option", *block["factors"], "Status"], rows))
    elif kind in ("architecture", "nested"):
        comps = block.get("components") or block.get("boxes") or []
        zones = {z["id"]: z["label"] for z in block.get("zones", [])}
        names = {c["id"]: c["label"] for c in comps}
        rows = [
            [
                c["label"],
                zones.get(c.get("zone", ""), names.get(c.get("parent", ""), "")),
                KINDS[c.get("kind", "service")],
                c.get("tech", ""),
                c.get("note", ""),
            ]
            for c in comps
        ]
        out.append(f"*The drawing is on the page; {len(comps)} parts, {len(block.get('links', []))} links.*")
        out.append(_md_table(["Part", "In", "Kind", "Technology", "Note"], rows))
        for flow in block.get("flows", []):
            steps = "\n".join(
                f"{i}. {names.get(s['from'], s['from'])} → {names.get(s['to'], s['to'])}: {s.get('text', '')}"
                for i, s in enumerate(flow["steps"], 1)
            )
            out.append(f"**Flow: {flow['title']}**\n\n{steps}")
    elif kind == "model":
        rows = [
            [
                t["label"],
                t.get("kind", "table"),
                t.get("grain", ""),
                ", ".join(c["name"] for c in t.get("columns", []) if c.get("key") == "pk"),
                str(len(t.get("columns", []))),
                str(sum(1 for c in t.get("columns", []) if c.get("personal"))),
            ]
            for t in block["tables"]
        ]
        out.append(_md_table(["Table", "Kind", "Grain", "Primary key", "Columns", "Personal"], rows))
        names = {t["id"]: t["label"] for t in block["tables"]}
        relations = [
            [names[r["from"]], names[r["to"]], r.get("on", ""), r.get("cardinality", "n:1")]
            for r in block.get("relations", [])
        ]
        if relations:
            out.append(_md_table(["From", "To", "On", "Cardinality"], relations))
    elif kind == "chart":
        columns, rows = _chart_rows(block)
        out.append(f"*{block['kind']} chart; the drawing is on the page.*")
        out.append(_md_table(columns, rows))
        if block.get("caption"):
            out.append(block["caption"])
    return "\n\n".join(out)


def render_markdown(page: Json) -> str:
    """The same page as a Markdown note, for a vault, a wiki or a pull request. Drawings become their tables."""
    meta = page.get("meta", {})
    out = [f"# {page['title']}"]
    if page.get("subtitle"):
        out.append(page["subtitle"])
    out.append(" · ".join([f"`{page['skill']}`", *[f"{k} {_plain(v)}" for k, v in meta.items()]]))
    verdict = page.get("verdict")
    if verdict:
        out.append(_md_quote(f"**Verdict ({TONE_LABEL[verdict.get('tone', 'info')]}):** {verdict['text']}"))
    if page.get("stats"):
        out.append(
            _md_table(["", "Value", "Note"], [[s["label"], s["value"], s.get("note", "")] for s in page["stats"]])
        )
    for number, section in enumerate(page["sections"], 1):
        out.append(f"## {number}. {section['title']}")
        if section.get("intro"):
            out.append(section["intro"])
        out.extend(_md_block(b) for b in section.get("blocks", []))
    date = f" · {meta['date']}" if isinstance(meta.get("date"), str) else ""
    out.append(
        f"*Written by the {page['skill']} skill{date} · numbers from the skill's scripts · "
        "claims tagged high (checked), med (likely), guess (not checked)*"
    )
    return "\n\n".join(out) + "\n"


# ---------------------------------------------------------------------------- index


def index_page(root: Path) -> tuple[Json, list[str]]:
    """Every page JSON under root as one page: a table per folder, newest first. Also what was left out."""
    folders: dict[str, list[tuple[str, list[Json]]]] = {}
    problems: list[str] = []
    skills: set[str] = set()
    for source in sorted(root.rglob("*.json")):
        relative = source.relative_to(root)
        if source.name == "site.json" or any(part.startswith(".") for part in relative.parts):
            continue
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not (isinstance(data, dict) and isinstance(data.get("skill"), str) and "sections" in data):
            continue
        errors = validate(data)
        if errors:
            problems.append(f"{source}: {len(errors)} problem(s), left out of the index")
            continue
        meta = data.get("meta", {})
        date = (
            meta["date"]
            if isinstance(meta.get("date"), str)
            else datetime.date.fromtimestamp(source.stat().st_mtime).isoformat()
        )
        folder = relative.parent.as_posix()
        folder = "" if folder == "." else folder
        href = quote(relative.with_suffix(".html").as_posix())
        title = data["title"].replace("[", "(").replace("]", ")")
        verdict = data.get("verdict")
        summary = ""
        if verdict:
            text = re.sub(r"[`*]", "", verdict["text"]).replace("\n", " ")
            summary = f"**{TONE_LABEL[verdict.get('tone', 'info')]}** " + (
                text[:177] + "…" if len(text) > 180 else text
            )
        folders.setdefault(folder, []).append((date, [date, data["skill"], f"[{title}]({href})", summary]))
        skills.add(data["skill"])
    sections = []
    for folder, entries in sorted(folders.items(), key=lambda kv: max(e[0] for e in kv[1]), reverse=True):
        rows = [row for _, row in sorted(entries, key=lambda e: e[0], reverse=True)]
        sections.append(
            {
                "id": _slug(folder or "root"),
                "title": folder or "(the folder itself)",
                "blocks": [{"type": "table", "columns": ["Date", "Skill", "Page", "Verdict"], "rows": rows}],
            }
        )
    count = sum(len(v) for v in folders.values())
    newest = max((e[0] for v in folders.values() for e in v), default="")
    page: Json = {
        "skill": "index",
        "title": root.name or "Pages",
        "subtitle": f"Every page under `{root}`, by folder, newest first. Refresh with `render_page.py --index`.",
        "meta": {"written": datetime.date.today().isoformat()},
        "stats": [
            {"label": "Pages", "value": count},
            {"label": "Folders", "value": len(folders)},
            {"label": "Skills", "value": len(skills)},
            {"label": "Newest", "value": newest or "none"},
        ],
        "sections": sections or [{"title": "No pages yet", "blocks": [{"type": "text", "text": "Nothing to list."}]}],
    }
    return page, problems


def render_index(root: Path, *, check: bool = False) -> int:
    """Write root/index.html, the list of every page under root."""
    if not root.is_dir():
        print(f"{root}: not a folder", file=sys.stderr)
        return 2
    page, problems = index_page(root.resolve())
    for problem in problems:
        print(problem, file=sys.stderr)
    errors = validate(page)
    if errors:
        _print_problems(root, errors)
        return 1
    if check:
        print(f"{root}: {page['stats'][0]['value']} pages")
        return 0
    target = root / "index.html"
    target.write_text(render(page), encoding="utf-8")
    print(target.resolve())
    return 0


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
    parser.add_argument("-o", "--output", type=Path, help="where to write the HTML (or the Markdown, with --md)")
    parser.add_argument("--md", action="store_true", help="write the page as a Markdown note; drawings become tables")
    parser.add_argument("--site", type=Path, help="a site JSON: write all its pages, with a header linking them")
    parser.add_argument("--index", type=Path, help="a folder of pages: write index.html there, listing every page")
    parser.add_argument("--check", action="store_true", help="validate only, write nothing")
    args = parser.parse_args(argv)
    if sum(x is not None for x in (args.page, args.site, args.index)) != 1:
        parser.error("give one of: a page JSON, --site SITE.json, --index FOLDER")
    if args.site is not None or args.index is not None:
        if args.output is not None or args.md:
            parser.error("--output and --md are for one page; --site and --index write where the pages are")
        if args.site is not None:
            return render_site(args.site, check=args.check)
        return render_index(args.index, check=args.check)
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
    output = args.output or args.page.with_suffix(".md" if args.md else ".html")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(page) if args.md else render(page), encoding="utf-8")
    print(output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
