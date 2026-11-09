#!/usr/bin/env python3
"""Apply the hard rules of the data platform ladder to the facts of a brief, and size the platform.

Usage: python3 platform_rules.py FACTS.json      (or - for stdin)
       python3 platform_rules.py --facts          (list the facts it reads, with what each one decides)

The ladder, by moving parts: reports on the source or a replica, one database with scheduled SQL, a
managed warehouse, a lakehouse in layers, a lakehouse with a streaming path, a data mesh. Each rule
eliminates options that cannot meet a fact of the brief. The script never chooses: it prints which
options are still open, the lowest open one, and the facts that are unknown but would eliminate
something. Weighing the open options is the architect's job.

The thresholds are judgements, not laws: they are named below and printed, so the page can show them.
A fact that is missing or null decides nothing. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

OPTIONS = [
    ("source_reports", "Reports on the source or a replica"),
    ("single_db", "One database with scheduled SQL"),
    ("warehouse", "A managed warehouse"),
    ("lakehouse", "A lakehouse in layers"),
    ("lakehouse_streaming", "A lakehouse with a streaming path"),
    ("mesh", "A data mesh on a shared platform"),
]
THRESHOLDS = {
    "single_db_limit_gb": 2000,  # after two years; past it one relational database needs real tuning work
    "streaming_below_minutes": 5,  # a scheduled micro-batch can keep up with anything slower
    "mesh_min_domain_teams": 3,  # fewer teams than this do not need federated ownership
}
OPERATED = ["lakehouse", "lakehouse_streaming", "mesh"]
FACTS: dict[str, tuple[str, str]] = {
    "data_gb": ("number", "size of the data today, in GB"),
    "growth_gb_per_month": ("number", "how much it grows per month, in GB"),
    "joins_across_sources": ("bool", "must data from different sources be joined?"),
    "source_keeps_history": ("bool", "does the source keep the history the reports need?"),
    "source_can_take_load": ("bool", "can the source or a replica take the reporting load?"),
    "files_or_images": ("bool", "must files, images or documents that are not tables be stored and processed?"),
    "ml_on_raw": ("bool", "are models trained on raw data?"),
    "freshness_minutes": ("number", "the tightest freshness any use needs, in minutes"),
    "data_engineers": ("int", "data engineers who would run the platform"),
    "domain_teams": ("int", "domain teams that have their own data engineers"),
}
WOULD_DECIDE: dict[str, list[str]] = {
    "data_gb": ["single_db"],
    "growth_gb_per_month": ["single_db"],
    "joins_across_sources": ["source_reports"],
    "source_keeps_history": ["source_reports"],
    "source_can_take_load": ["source_reports"],
    "files_or_images": ["source_reports", "single_db", "warehouse"],
    "ml_on_raw": ["source_reports", "single_db", "warehouse"],
    "freshness_minutes": ["single_db", "warehouse", "lakehouse", "lakehouse_streaming"],
    "data_engineers": OPERATED,
    "domain_teams": ["mesh"],
}


def after_months(facts: dict[str, Any], months: int) -> float | None:
    if facts.get("data_gb") is None:
        return None
    return round(float(facts["data_gb"]) + months * float(facts.get("growth_gb_per_month") or 0), 1)


def _rules(f: dict[str, Any]) -> list[tuple[str, list[str], str]]:
    """Every rule that fires, as (name, options it eliminates, why)."""
    rules: list[tuple[str, list[str], str]] = []
    if f.get("joins_across_sources") is True:
        rules.append(("joins-sources", ["source_reports"], "Data from different sources must be joined."))
    if f.get("source_keeps_history") is False:
        rules.append(("no-history", ["source_reports"], "The source overwrites the history the reports need."))
    if f.get("source_can_take_load") is False:
        rules.append(("source-load", ["source_reports"], "Neither the source nor a replica can take the load."))
    limit = THRESHOLDS["single_db_limit_gb"]
    size = after_months(f, 24)
    if size is not None and size > limit:
        rules.append(("too-big", ["single_db"], f"{size:,.0f} GB after two years is past about {limit:,} GB."))
    if f.get("files_or_images") is True:
        rules.append(
            (
                "needs-file-storage",
                ["source_reports", "single_db", "warehouse"],
                "Files, images or documents must be stored and processed next to the tables.",
            )
        )
    if f.get("ml_on_raw") is True:
        rules.append(
            (
                "ml-on-raw",
                ["source_reports", "single_db", "warehouse"],
                "Models are trained on raw data, which needs open files rather than warehouse tables.",
            )
        )
    minutes = f.get("freshness_minutes")
    fast = THRESHOLDS["streaming_below_minutes"]
    if minutes is not None and minutes < fast:
        rules.append(
            (
                "needs-streaming",
                ["single_db", "warehouse", "lakehouse"],
                f"A use needs data {minutes} minutes fresh, under the {fast} minutes a scheduled load can keep.",
            )
        )
    if minutes is not None and minutes >= fast:
        rules.append(
            (
                "no-streaming-need",
                ["lakehouse_streaming"],
                f"Nothing needs data fresher than {fast} minutes: a streaming path would be cost without a use.",
            )
        )
    if f.get("data_engineers") == 0:
        rules.append(("nobody-to-run-it", OPERATED, "There is no data engineer to operate it."))
    teams = THRESHOLDS["mesh_min_domain_teams"]
    if f.get("domain_teams") is not None and f["domain_teams"] < teams:
        rules.append(
            (
                "too-few-domains",
                ["mesh"],
                f"{f['domain_teams']} domain team(s) with their own engineers: a mesh needs at least {teams}.",
            )
        )
    return rules


def check(facts: Any) -> list[str]:
    if not isinstance(facts, dict):
        return ["facts: must be a JSON object"]
    errs = []
    for key, value in facts.items():
        if key not in FACTS:
            errs.append(f"{key}: unknown fact (known: {', '.join(FACTS)})")
            continue
        if value is None:
            continue
        kind = FACTS[key][0]
        ok = {
            "bool": isinstance(value, bool),
            "int": isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            "number": isinstance(value, int | float) and not isinstance(value, bool) and value >= 0,
        }[kind]
        if not ok:
            errs.append(f"{key}: must be a {kind}")
    return errs


def decide(facts: dict[str, Any]) -> dict[str, Any]:
    by_option: dict[str, list[dict[str, str]]] = {key: [] for key, _ in OPTIONS}
    for name, eliminated, why in _rules(facts):
        for key in eliminated:
            by_option[key].append({"rule": name, "why": why})
    options = [
        {
            "id": key,
            "label": label,
            "rung": rung,
            "status": "eliminated" if by_option[key] else "open",
            "eliminated_by": by_option[key],
        }
        for rung, (key, label) in enumerate(OPTIONS)
    ]
    still_open = [o["id"] for o in options if o["status"] == "open"]
    open_facts = []
    for fact, could in WOULD_DECIDE.items():
        if facts.get(fact) is None:
            affected = [k for k in could if k in still_open]
            if affected:
                open_facts.append({"fact": fact, "means": FACTS[fact][1], "could_eliminate": affected})
    growth = facts.get("growth_gb_per_month")
    return {
        "options": options,
        "open": still_open,
        "lowest_open": still_open[0] if still_open else None,
        "open_facts": open_facts,
        "sizing": {
            "today_gb": facts.get("data_gb"),
            "after_1_year_gb": after_months(facts, 12),
            "after_2_years_gb": after_months(facts, 24),
            "daily_ingest_gb": round(float(growth) / 30, 2) if growth is not None else None,
        },
        "thresholds": THRESHOLDS,
        "facts": {k: facts.get(k) for k in FACTS},
        "note": "Hard rules only. An open option is not a choice: weigh the open ones by whether this team can run "
        "it, freshness, cost of wrong data, governance and cost, and climb above the lowest only for a named reason.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the hard rules of the data platform ladder to a brief's facts.")
    parser.add_argument("facts", nargs="?", help="a JSON file of facts, or - for stdin")
    parser.add_argument("--facts", dest="list_facts", action="store_true", help="list the facts and exit")
    args = parser.parse_args(argv)
    if args.list_facts or not args.facts:
        json.dump({k: {"type": t, "means": m} for k, (t, m) in FACTS.items()}, sys.stdout, indent=1, ensure_ascii=False)
        print()
        return 0
    try:
        raw = sys.stdin.read() if args.facts == "-" else Path(args.facts).read_text(encoding="utf-8")
        facts = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read the facts: {exc}", file=sys.stderr)
        return 2
    errors = check(facts)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    json.dump(decide(facts), sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
