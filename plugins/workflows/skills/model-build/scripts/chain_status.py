#!/usr/bin/env python3
"""Where a chain of skills stands in one pages folder: each step's newest page, date, verdict, findings and open items.

Usage:
    python3 chain_status.py --folder DIR --steps codebase-map,code-audit,... [--since YYYY-MM-DD]

JSON on stdout; read-only; standard library only. A page is <skill>-<YYYY-MM-DD>.json in the folder and the newest
wins. Each page is checked with the render_page.py beside this script, so a page that would not render is reported,
not trusted. A page older than --since is stale, which counts as missing. Exit 2 when the folder does not exist.

Single source: shared/chain_status.py in claude-role-skills. The copies under each skill's scripts/ are written by
tools/sync_shared.py; edit the shared file, never a copy.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

NAME = re.compile(r"^(?P<skill>.+)-(?P<date>\d{4}-\d{2}-\d{2})\.json$")
SEVERITIES = ("high", "medium", "low", "info")


def renderer() -> Any:
    """The render_page.py beside this script, for its validate()."""
    path = Path(__file__).resolve().parent / "render_page.py"
    spec = importlib.util.spec_from_file_location("render_page", path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def newest(folder: Path, skill: str) -> Path | None:
    """The newest page of a skill in the folder, by the date in its name, then by modification time."""
    pages = []
    for path in folder.glob(f"{skill}-????-??-??.json"):
        match = NAME.match(path.name)
        if match and match.group("skill") == skill:
            pages.append((match.group("date"), path.stat().st_mtime, path))
    return max(pages)[2] if pages else None


def findings(page: dict[str, Any]) -> dict[str, int]:
    counts = dict.fromkeys(SEVERITIES, 0)
    counts["open_high"] = 0
    for section in page.get("sections", []):
        for block in section.get("blocks", []):
            if block.get("type") != "findings":
                continue
            for item in block.get("items", []):
                counts[item["severity"]] += 1
                if item["severity"] == "high" and item.get("status", "open") == "open":
                    counts["open_high"] += 1
    return counts


def describe(path: Path, since: str | None, render: Any) -> dict[str, Any]:
    match = NAME.match(path.name)
    out: dict[str, Any] = {
        "page": str(path),
        "file": path.name,
        "date": match.group("date") if match else "",
        "html": path.with_suffix(".html").is_file(),
        "note": path.with_suffix(".md").is_file(),
    }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        out.update(valid=False, problems=[str(exc)], stale=False)
        return out
    problems = render.validate(data)
    out["valid"] = not problems
    out["problems"] = problems[:5]
    if problems:
        out["stale"] = False
        return out
    meta = data.get("meta", {})
    if isinstance(meta.get("date"), str):
        out["date"] = meta["date"]
    out["title"] = data["title"]
    verdict = data.get("verdict")
    out["verdict"] = {"tone": verdict.get("tone", "info"), "text": verdict["text"]} if verdict else None
    out["findings"] = findings(data)
    facts = data.get("facts") if isinstance(data.get("facts"), dict) else {}
    out["open"] = [item for item in facts.get("open", []) if isinstance(item, str)]
    out["stale"] = bool(since and out["date"] < since)
    return out


def status(folder: Path, steps: list[str], since: str | None) -> dict[str, Any]:
    render = renderer()
    result: list[dict[str, Any]] = []
    for skill in steps:
        page = newest(folder, skill)
        entry: dict[str, Any] = {"skill": skill}
        if page is None:
            entry.update(page=None, valid=False, stale=False)
        else:
            entry.update(describe(page, since, render))
        result.append(entry)
    missing = [e["skill"] for e in result if e.get("page") is None or not e["valid"] or e["stale"]]
    bad = [e["skill"] for e in result if e.get("verdict") and e["verdict"]["tone"] == "bad"]
    return {"folder": str(folder), "since": since, "steps": result, "missing": missing, "bad": bad, "done": not missing}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--folder", type=Path, required=True, help="the pages folder of one repository or project")
    parser.add_argument("--steps", required=True, help="the skills of the chain, in order, comma-separated")
    parser.add_argument("--since", help="a page dated before this YYYY-MM-DD is stale")
    args = parser.parse_args(argv)
    if not args.folder.is_dir():
        print(f"{args.folder}: not a folder", file=sys.stderr)
        return 2
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    print(json.dumps(status(args.folder, steps, args.since), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
