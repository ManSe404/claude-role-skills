#!/usr/bin/env python3
"""Check a C4 drawing for the things that make one misleading.

Usage: python3 c4_check.py PAGE_OR_BLOCK.json

The input is a `nested` block, or a page JSON that holds one or more. Errors: a person or an outside system
inside another box, a link with no label, a container with no technology, a level that opens a box with
nothing inside. Warnings: no context level, a box that nothing touches. Read-only, standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PEOPLE = ("user", "human")


def blocks_of(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and data.get("type") == "nested":
        return [data]
    found: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for section in data.get("sections", []):
            found += [b for b in section.get("blocks", []) if isinstance(b, dict) and b.get("type") == "nested"]
    return found


def check_block(block: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    boxes = {b["id"]: b for b in block.get("boxes", [])}
    has_children = {b["parent"] for b in boxes.values() if b.get("parent")}
    tops = {key for key, box in boxes.items() if not box.get("parent")}
    for key, box in boxes.items():
        kind = box.get("kind", "service")
        if box.get("parent"):
            if kind in PEOPLE:
                errors.append(f"{key}: a person cannot be inside {box['parent']}")
            if kind == "system":
                errors.append(f"{key}: an outside system cannot be inside {box['parent']}")
            if box["parent"] in tops and key not in has_children and not box.get("tech"):
                errors.append(f"{key}: a container needs its technology")
    touched = set()
    for link in block.get("links", []):
        if not link.get("label"):
            errors.append(f"link {link.get('from')} -> {link.get('to')}: no label")
        for end in (link.get("from"), link.get("to")):
            at = end
            while at in boxes:
                touched.add(at)
                at = boxes[at].get("parent")
    for level in block.get("levels", []):
        for key in level.get("open", []):
            if key not in has_children:
                errors.append(f"level {level.get('id')}: opens {key}, which has nothing inside")
    if block.get("levels") and not any(not level.get("open") for level in block["levels"]):
        warnings.append("no context level: add one with nothing open")
    for key in boxes:
        if key not in touched:
            warnings.append(f"{key}: nothing links to it")
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a C4 drawing for the things that make one misleading.")
    parser.add_argument("page", type=Path)
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.page.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {args.page}: {exc}", file=sys.stderr)
        return 2
    blocks = blocks_of(data)
    if not blocks:
        print(f"{args.page}: no nested block found", file=sys.stderr)
        return 2
    errors: list[str] = []
    warnings: list[str] = []
    for block in blocks:
        found = check_block(block)
        errors += found[0]
        warnings += found[1]
    boxes = [b for block in blocks for b in block.get("boxes", [])]
    json.dump(
        {
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "counts": {
                "boxes": len(boxes),
                "links": sum(len(block.get("links", [])) for block in blocks),
                "levels": sum(len(block.get("levels", [])) for block in blocks),
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
