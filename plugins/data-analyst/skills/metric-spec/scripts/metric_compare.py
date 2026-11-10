#!/usr/bin/env python3
"""Find where a metric is defined, and measure on sample data how far its definitions disagree.

Usage: python3 metric_compare.py find REPO --name NAME[,NAME ...]
       python3 metric_compare.py compare SPEC.json DATA

find reads SQL, dbt and YAML or Markdown, with comments and strings removed before the SQL is read, and prints every
aliased expression whose alias contains NAME, with its statement, its FROM and WHERE, and the lines that mention it.

compare takes SPEC.json with {"definitions": [{"name": ..., "source": "file:line", "measure": MEASURE}, ...]} (MEASURE
is the shape measure.py reads). It prints each definition's number on the same data, then the walk from each
definition to the first: the differences one at a time (date window, each filter changed, dropped or added,
de-duplication, the value formula), each with the amount it moves the number. Each step's effect is the change in the
exact value, so the steps add up to the whole difference; the order changes how much each step gets, so the walk states
its order.

It prints columns and counts only. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure
import sql_inventory

TEXT_SUFFIXES = {".sql", ".hql", ".yml", ".yaml", ".md"}
ALIAS = re.compile(r"(?is)\bas\s+([\"`\[]?)(\w+)[\"`\]]?")
CLAUSE_END = re.compile(r"(?is)\b(group\s+by|order\s+by|having|union|limit|qualify)\b")
FROM_JOIN = re.compile(r"(?is)\b(from|join)\s+([\w.\"`\[\]_]+)")
UNION = re.compile(r"(?is)\bunion(\s+all)?\b")


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def one_line(text: str) -> str:
    return " ".join(text.split())


def statement_bounds(clean: str, offset: int) -> tuple[int, int]:
    start = clean.rfind(";", 0, offset) + 1
    end = clean.find(";", offset)
    return start, len(clean) if end < 0 else end


def branch_bounds(clean: str, offset: int, start: int, end: int) -> tuple[int, int]:
    """The select branch of a UNION that holds the offset, so a branch's WHERE and FROM are not its neighbour's."""
    before = [m.end() for m in UNION.finditer(clean, start, offset)]
    after = UNION.search(clean, offset, end)
    return (before[-1] if before else start), (after.start() if after else end)


def select_item_start(clean: str, alias_start: int, statement_start: int) -> int:
    """Walk back to the comma or SELECT that opens this select item, at the same bracket depth as the alias."""
    depth = 0
    i = alias_start - 1
    while i >= statement_start:
        char = clean[i]
        if char == ")":
            depth += 1
        elif char == "(":
            depth -= 1
            if depth < 0:
                return i + 1
        elif depth == 0 and (char == "," or clean[i - 5 : i + 1].lower() == "select"):
            return i + 1
        i -= 1
    return statement_start


def find(repo: Path, names: list[str]) -> dict[str, Any]:
    if not repo.is_dir():
        raise SystemExit(f"not a folder: {repo}")
    tokens = [n.lower() for n in names]
    definitions: list[dict[str, Any]] = []
    mentions: list[dict[str, Any]] = []
    files = [
        p
        for p in sorted(repo.rglob("*"))
        if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES and not set(p.parts) & sql_inventory.SKIP_DIRS
    ]
    for path in files:
        rel = path.relative_to(repo).as_posix()
        raw = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() in (".sql", ".hql"):
            clean, refs, _ = sql_inventory.clean_sql(raw)
            for match in ALIAS.finditer(clean):
                alias = match.group(2)
                if not any(t in alias.lower() for t in tokens):
                    continue
                start, end = statement_bounds(clean, match.start())
                branch_start, branch_end = branch_bounds(clean, match.start(), start, end)
                item = select_item_start(clean, match.start(), branch_start)
                where = None
                where_at = re.search(r"(?is)\bwhere\b", clean[match.end() : branch_end])
                if where_at:
                    span_start = match.end() + where_at.start()
                    stop = CLAUSE_END.search(clean, span_start, branch_end)
                    span_end = stop.start() if stop else branch_end
                    where = one_line(raw[span_start:span_end])
                tables = []
                for found in FROM_JOIN.finditer(clean, branch_start, branch_end):
                    tables.append(f"{found.group(1).lower()} {refs.get(found.group(2), found.group(2))}")
                definitions.append(
                    {
                        "file": rel,
                        "line": line_of(raw, match.start()),
                        "alias": alias,
                        "expression": one_line(raw[item : match.end()]),
                        "from": tables,
                        "where": where,
                        "statement": f"{rel}:{line_of(raw, branch_start)}-{line_of(raw, branch_end)}",
                    }
                )
        else:
            for number, text in enumerate(raw.splitlines(), start=1):
                if any(t in text.lower() for t in tokens):
                    mentions.append({"file": rel, "line": number, "text": text.strip()[:160]})
    return {"names": names, "definitions": definitions, "mentions": mentions}


def _filters_of(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return list(spec.get("filters", []))


def _same_filter(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (a.get("column"), a.get("op"), a.get("value")) == (b.get("column"), b.get("op"), b.get("value"))


def walk(first: dict[str, Any], second: dict[str, Any], data: dict[str, measure.Table]) -> dict[str, Any]:
    """Step from one definition to another, one difference at a time, in a fixed order, and price each step."""
    a_spec, b_spec = first["measure"], second["measure"]
    if "ratio" in (a_spec.get("value") or {}) or "ratio" in (b_spec.get("value") or {}):
        return {"note": "ratio definitions are compared by value only; no step-by-step walk"}
    if a_spec.get("table") != b_spec.get("table"):
        return {"note": "the two definitions read different tables; no step-by-step walk"}
    current = copy.deepcopy(a_spec)
    previous = Fraction(measure.evaluate(current, data)["exact"])
    start_value = previous
    steps: list[dict[str, Any]] = []

    def step(change: str) -> None:
        nonlocal previous
        result = measure.evaluate(current, data)
        value = Fraction(result["exact"])
        steps.append(
            {
                "change": change,
                "number_after": measure.show(value, 2),
                "effect": measure.show(value - previous, 2),
                "effect_exact": str(value - previous),
                "rows_kept": result["rows_kept"],
            }
        )
        previous = value

    if (a_spec.get("window") or {}) != (b_spec.get("window") or {}):
        current["window"] = copy.deepcopy(b_spec.get("window"))
        if current["window"] is None:
            current.pop("window")
        before = a_spec.get("window") or {}
        after = b_spec.get("window") or {}
        step(
            f"date window: {before.get('column', 'none')} {before.get('from', '')}..{before.get('to', '')} "
            f"to {after.get('column', 'none')} {after.get('from', '')}..{after.get('to', '')}"
        )
    a_filters, b_filters = _filters_of(a_spec), _filters_of(b_spec)
    table = data[a_spec["table"]]
    # A filter on the same column on both sides is one change, not a drop and an add.
    changed = {
        (i, j)
        for i, left in enumerate(a_filters)
        for j, right in enumerate(b_filters)
        if left["column"] == right["column"] and not _same_filter(left, right)
    }
    paired_a = {i for i, _ in changed}
    paired_b = {j for _, j in changed}
    for i, j in sorted(changed):
        left, right = a_filters[i], b_filters[j]
        current["filters"] = [copy.deepcopy(right) if _same_filter(f, left) else f for f in current.get("filters", [])]
        step(f"change filter: {measure.public_filter(left, table)} to {measure.public_filter(right, table)}")
    for i, item in enumerate(a_filters):
        if i not in paired_a and not any(_same_filter(item, other) for other in b_filters):
            current["filters"] = [f for f in current.get("filters", []) if not _same_filter(f, item)]
            step(f"drop filter: {measure.public_filter(item, table)}")
    for j, item in enumerate(b_filters):
        if j not in paired_b and not any(_same_filter(item, other) for other in a_filters):
            current.setdefault("filters", []).append(copy.deepcopy(item))
            step(f"add filter: {measure.public_filter(item, table)}")
    if list(a_spec.get("dedupe", [])) != list(b_spec.get("dedupe", [])):
        current["dedupe"] = list(b_spec.get("dedupe", []))
        step(f"one row per: {', '.join(b_spec.get('dedupe', [])) or 'nothing (all rows)'}")
    if a_spec.get("value") != b_spec.get("value"):
        current["value"] = copy.deepcopy(b_spec["value"])
        step(f"value: {json.dumps(a_spec.get('value'))} to {json.dumps(b_spec.get('value'))}")
    total = Fraction(measure.evaluate(b_spec, data)["exact"]) - start_value
    sum_steps = sum((Fraction(s["effect_exact"]) for s in steps), Fraction(0))
    return {
        "from": first["name"],
        "to": second["name"],
        "order": "date window, filters changed, filters dropped, filters added, de-duplication, value",
        "difference": measure.show(total, 2),
        "steps": steps,
        "steps_sum_minus_difference": str(sum_steps - total),
        "adds_up": sum_steps == total,
    }


def compare(spec_path: Path, data_path: Path) -> dict[str, Any]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    data = measure.tables(data_path)
    definitions = spec["definitions"]
    results = []
    for item in definitions:
        result = measure.evaluate(item["measure"], data)
        results.append(
            {
                "name": item["name"],
                "source": item.get("source"),
                "value": result["value"],
                "exact": result["exact"],
                "rows_kept": result["rows_kept"],
                "filters": result.get("filters", []),
                "duplicates_removed": result.get("duplicates_removed", 0),
            }
        )
    walks = []
    for other in definitions[1:]:
        walks.append(walk(definitions[0], other, data))
    return {"definitions": results, "walks": walks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find a metric's definitions and measure how far they disagree.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    find_cmd = sub.add_parser("find", help="find where a metric is defined")
    find_cmd.add_argument("repo", type=Path)
    find_cmd.add_argument("--name", required=True, help="the metric name; several separated by commas")
    compare_cmd = sub.add_parser("compare", help="measure the definitions on sample data")
    compare_cmd.add_argument("spec", type=Path)
    compare_cmd.add_argument("data", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "find":
        result = find(args.repo, [n.strip() for n in args.name.split(",") if n.strip()])
    else:
        result = compare(args.spec, args.data)
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
