#!/usr/bin/env python3
"""Check a data model for the decisions a modeller must not skip.

Usage: python3 model_check.py MODEL.json

MODEL.json is a `model` block, or a page JSON that holds one or more. Errors are decisions that are
missing: a fact without a grain, a relation that does not resolve, an n:n without a bridge, a personal
column without a masking decision, a dimension without a history decision or a primary key. Warnings
deserve a look. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def blocks_of(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and data.get("type") == "model":
        return [data]
    found: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for section in data.get("sections", []):
            found += [b for b in section.get("blocks", []) if isinstance(b, dict) and b.get("type") == "model"]
    return found


def check_block(block: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    tables = {t["id"]: t for t in block.get("tables", [])}
    relations = block.get("relations", [])
    joined: dict[str, set[str]] = {key: set() for key in tables}
    related: set[str] = set()
    for rel in relations:
        ends = rel.get("from"), rel.get("to")
        name = f"{ends[0]} -> {ends[1]}"
        missing = [e for e in ends if e not in tables]
        if missing:
            errors.append(f"relation {name}: unknown table {', '.join(str(m) for m in missing)}")
            continue
        related.update(ends)
        if rel.get("cardinality", "n:1") == "n:n":
            errors.append(f"relation {name}: n:n needs a bridge table")
        if not rel.get("on"):
            warnings.append(f"relation {name}: no join column given")
            continue
        for pair in str(rel["on"]).split(","):
            left, _, right = pair.strip().partition("=")
            left, right = left.strip(), right.strip() or left.strip()
            for table, column in ((ends[0], left), (ends[1], right)):
                if column not in {c["name"] for c in tables[table].get("columns", [])}:
                    errors.append(f"relation {name}: {table} has no column {column}")
                joined[table].add(column)
    for key, table in tables.items():
        kind = table.get("kind", "table")
        columns = table.get("columns", [])
        has_pk = any(c.get("key") == "pk" for c in columns)
        if kind == "fact":
            if not table.get("grain"):
                errors.append(f"{key}: a fact needs its grain")
            if key not in related:
                warnings.append(f"{key}: a fact that joins to nothing")
            if not has_pk:
                warnings.append(f"{key}: no primary key: how is the grain enforced?")
        if kind == "dimension":
            if not has_pk:
                errors.append(f"{key}: a dimension needs a primary key")
            attributes = [c for c in columns if not c.get("key")]
            if not table.get("history") and not all(c.get("history") for c in attributes):
                errors.append(f"{key}: no history decision (set it on the table or on every attribute)")
        for column in columns:
            if column.get("personal") and not column.get("mask"):
                errors.append(f"{key}.{column['name']}: personal column without a masking decision")
            if column.get("key") == "fk" and column["name"] not in joined[key]:
                warnings.append(f"{key}.{column['name']}: a foreign key no relation uses")
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a data model for the decisions a modeller must not skip.")
    parser.add_argument("model", type=Path, help="a model block or a page JSON")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.model.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {args.model}: {exc}", file=sys.stderr)
        return 2
    blocks = blocks_of(data)
    if not blocks:
        print(f"{args.model}: no model block found", file=sys.stderr)
        return 2
    errors: list[str] = []
    warnings: list[str] = []
    for block in blocks:
        found = check_block(block)
        errors += found[0]
        warnings += found[1]
    tables = [t for block in blocks for t in block.get("tables", [])]
    columns = [c for t in tables for c in t.get("columns", [])]
    json.dump(
        {
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "counts": {
                "tables": len(tables),
                "facts": sum(1 for t in tables if t.get("kind") == "fact"),
                "dimensions": sum(1 for t in tables if t.get("kind") == "dimension"),
                "relations": sum(len(block.get("relations", [])) for block in blocks),
                "columns": len(columns),
                "personal_columns": sum(1 for c in columns if c.get("personal")),
            },
        },
        sys.stdout,
        indent=1,
        ensure_ascii=False,
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
